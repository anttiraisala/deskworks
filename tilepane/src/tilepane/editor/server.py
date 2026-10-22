"""Local server for `tilepane --edit` (SPEC.md section 5, server security).

Any web page the user visits can send requests to localhost, including through
DNS rebinding, and this server writes a file and can open windows that run the
file's commands. So:

* it listens on 127.0.0.1 only, on a random port;
* every request needs the random per-session token (in the URL of the page,
  then in a header);
* the Host header must name 127.0.0.1 or localhost with this port, and an
  Origin header, when sent, must be this server;
* it writes only files whose name ends in .json, and only after the editor has
  asked for that path (Save as, Open); it refuses to replace an existing file
  without an explicit confirmation. Where it may write is decided by the
  operating system's permissions of the user running it, not by the server. No
  request carries a command. "Open on screen" opens a layout of the current
  file by name on a monitor by number, both checked against what exists;
* it stops when the editor tab is closed (or stops sending heartbeats), and
  after a long idle time.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional
from urllib.parse import parse_qs, urlsplit

from .. import config, docgen, state

MAX_BODY = 2 * 1024 * 1024
IDLE_TIMEOUT = 30 * 60      # no request at all for this long: stop
GONE_TIMEOUT = 150          # no heartbeat for this long (browsers slow hidden tabs to 1/min)
BYE_GRACE = 4               # after the tab says goodbye, wait this long for a reload
RECENT_FILES = 10           # how many recently used files the file dialog remembers


class PathError(ValueError):
    """A path the editor may not use, with a message for the person."""


def target_path(raw: object) -> str:
    """The absolute path of a layout file named by the editor (`~` is the home directory)."""
    if not isinstance(raw, str) or not raw.strip():
        raise PathError("no file name")
    path = os.path.abspath(os.path.expanduser(raw.strip()))
    if not path.lower().endswith(".json"):
        raise PathError("the file name must end in .json")
    if os.path.isdir(path):
        raise PathError(f"{path} is a directory")
    return path


def looks_like_layout(text: str) -> bool:
    """Does this text look like a tilepane file (an object with layouts or a split)?"""
    try:
        data = json.loads(text)
    except ValueError:
        return False
    return isinstance(data, dict) and ("layouts" in data or "split" in data)


def run_cli(args: list[str]) -> tuple[int, str]:
    """Run tilepane with these arguments; (exit code, combined output)."""
    try:
        proc = subprocess.run([sys.executable, "-m", "tilepane.cli", *args], capture_output=True,
                              text=True, timeout=120, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return 1, "tilepane did not finish within 120 s"
    return proc.returncode, (proc.stdout + proc.stderr)


@dataclass
class EditorServer:
    path: str                                   # the file the editor is editing now (changes with Save as and Open)
    monitors: Callable[[], list[dict]]          # [{number, name, x, y, width, height, work?}]
    cli: Callable[[list[str]], tuple[int, str]] = run_cli
    workspaces: Callable[[], Optional[int]] = lambda: None   # how many workspaces, if known
    port: int = 0
    prefs_path: Optional[str] = None            # where the last folder and recent files are kept
    idle_timeout: float = IDLE_TIMEOUT
    gone_timeout: float = GONE_TIMEOUT
    bye_grace: float = BYE_GRACE
    token: str = field(default_factory=lambda: secrets.token_urlsafe(24))

    def __post_init__(self) -> None:
        self.path = os.path.abspath(self.path)
        self._httpd = ThreadingHTTPServer(("127.0.0.1", self.port), self._handler())
        self._httpd.daemon_threads = True
        self.port = self._httpd.server_address[1]
        self._last_request = time.monotonic()
        self._last_ping: Optional[float] = None
        self._bye_at: Optional[float] = None
        self._lock = threading.Lock()
        self.stop_reason = ""

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/?t={self.token}"

    # --- lifecycle ---------------------------------------------------------

    def serve(self) -> str:
        """Serve until the tab is closed, the idle timeout passes or stop() is called."""
        watcher = threading.Thread(target=self._watch, daemon=True)
        watcher.start()
        try:
            self._httpd.serve_forever(poll_interval=0.2)
        finally:
            self._httpd.server_close()
        return self.stop_reason

    def stop(self, reason: str = "stopped") -> None:
        with self._lock:
            if self.stop_reason:
                return
            self.stop_reason = reason
        threading.Thread(target=self._httpd.shutdown, daemon=True).start()

    def _watch(self) -> None:
        while not self.stop_reason:
            time.sleep(0.2)
            now = time.monotonic()
            if now - self._last_request > self.idle_timeout:
                self.stop("idle timeout")
            elif self._bye_at is not None and now - self._bye_at > self.bye_grace:
                self.stop("the editor tab was closed")
            elif self._last_ping is not None and now - self._last_ping > self.gone_timeout:
                self.stop("the editor tab stopped answering")

    # --- file and actions -----------------------------------------------------

    def read_file(self) -> Optional[str]:
        try:
            with open(self.path, encoding="utf-8") as fh:
                return fh.read()
        except FileNotFoundError:
            return None

    def save(self, text: str, path: Optional[str] = None) -> tuple[bool, list[str], list[str]]:
        """Validate and write to `path` (default: the current file); (ok, errors, warnings)."""
        path = path or self.path
        try:
            cfg = config.load_text(text, path)
        except config.ConfigError as exc:
            return False, exc.errors, []
        directory = os.path.dirname(path)
        os.makedirs(directory, exist_ok=True)
        mode = None
        if os.path.exists(path):
            mode = os.stat(path).st_mode & 0o777
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tilepane-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            if mode is not None:
                os.chmod(tmp, mode)
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        return True, [], cfg.warnings

    # ---- files chosen in the editor (Save as, Open)

    def _prefs(self) -> dict:
        try:
            with open(self.prefs_path or os.path.join(state.state_dir(), "editor.json"), encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _remember(self, path: str) -> None:
        """Keep the folder and the file for the next time; a failure to write them is not an error."""
        prefs = self._prefs()
        recent = [p for p in prefs.get("recent", []) if isinstance(p, str) and p != path]
        prefs["recent"] = [path] + recent[:RECENT_FILES - 1]
        prefs["last_dir"] = os.path.dirname(path)
        target = self.prefs_path or os.path.join(state.state_dir(), "editor.json")
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as fh:
                json.dump(prefs, fh, indent=2)
        except OSError:
            pass

    def list_dir(self, raw: object) -> dict:
        """The folders and .json files of a folder, for the file dialog. A path that is
        not a folder gives its nearest existing parent."""
        prefs = self._prefs()
        if not isinstance(raw, str) or not raw.strip():
            raw = prefs.get("last_dir") if isinstance(prefs.get("last_dir"), str) else os.path.dirname(self.path)
        directory = os.path.abspath(os.path.expanduser(raw))
        while directory and not os.path.isdir(directory):
            parent = os.path.dirname(directory)
            if parent == directory:
                break
            directory = parent
        entries = []
        error = None
        try:
            for entry in sorted(os.scandir(directory), key=lambda e: (not e.is_dir(), e.name.lower())):
                if entry.name.startswith("."):
                    continue
                if entry.is_dir():
                    entries.append({"name": entry.name, "kind": "dir"})
                elif entry.name.lower().endswith(".json"):
                    entries.append({"name": entry.name, "kind": "file"})
        except OSError as exc:
            error = str(exc)
        recent = [p for p in prefs.get("recent", []) if isinstance(p, str) and os.path.isfile(p)]
        return {"dir": directory, "parent": os.path.dirname(directory), "entries": entries,
                "home": os.path.expanduser("~"), "config_dir": os.path.dirname(config.default_config_path()),
                "recent": recent, "error": error}

    def save_as(self, text: str, raw: object, overwrite: bool) -> tuple[int, dict]:
        """Save to another file. 409 when it exists and `overwrite` is not set."""
        try:
            path = target_path(raw)
        except PathError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": str(exc)}
        directory = os.path.dirname(path)
        if not os.path.isdir(directory) and directory != os.path.dirname(config.default_config_path()):
            return HTTPStatus.BAD_REQUEST, {"error": f"the folder {directory} does not exist"}
        if os.path.exists(path) and path != self.path and not overwrite:
            try:
                with open(path, encoding="utf-8") as fh:
                    other = not looks_like_layout(fh.read())
            except (OSError, UnicodeDecodeError):
                other = True
            return HTTPStatus.CONFLICT, {"error": "the file exists", "exists": True,
                                         "not_a_layout": other, "path": path}
        try:
            ok, errors, warnings = self.save(text, path)
        except OSError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": f"cannot write {path}: {exc.strerror or exc}"}
        if not ok:
            return HTTPStatus.UNPROCESSABLE_ENTITY, {"error": "the layout has problems", "errors": errors}
        self.path = path
        self._remember(path)
        return 200, {"ok": True, "warnings": warnings, "path": path, "name": os.path.basename(path)}

    def open_file(self, raw: object) -> tuple[int, dict]:
        """Read a layout file for the editor; it becomes the current file."""
        try:
            path = target_path(raw)
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except PathError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": str(exc)}
        except FileNotFoundError:
            return HTTPStatus.NOT_FOUND, {"error": "the file does not exist"}
        except (OSError, UnicodeDecodeError) as exc:
            return HTTPStatus.BAD_REQUEST, {"error": f"cannot read the file: {exc}"}
        self.path = path
        self._remember(path)
        return 200, {"ok": True, "path": path, "name": os.path.basename(path), "text": text}

    def on_screen(self, action: str, layout: object, monitor: object) -> tuple[int, dict]:
        """Open or close a layout of the saved file on a monitor."""
        text = self.read_file()
        if text is None:
            return 409, {"error": "save the file first"}
        try:
            cfg = config.load_text(text, self.path)
        except config.ConfigError as exc:
            return 409, {"error": "the saved file has problems", "errors": exc.errors}
        names = [str(n) for n in cfg.names()]
        if not isinstance(layout, (str, int)) or str(layout) not in names:
            return 400, {"error": f"no layout {layout!r} in the saved file"}
        numbers = [m["number"] for m in self.monitors()]
        if isinstance(monitor, bool) or not isinstance(monitor, int) or monitor not in numbers:
            return 400, {"error": f"no monitor {monitor!r}"}
        args = ["--json", self.path, "--layout", str(layout), "--monitor", str(monitor)]
        if action == "close":
            args = ["--close"] + args
        code, output = self.cli(args)
        return 200, {"code": code, "output": output}

    # --- HTTP ------------------------------------------------------------------

    def _handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "tilepane-editor"
            sys_version = ""

            def log_message(self, fmt, *args):  # noqa: D401 - quiet unless something fails
                pass

            def _send(self, status: int, body: bytes, ctype: str, extra: Optional[dict] = None) -> None:
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("X-Frame-Options", "DENY")
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)

            def _json(self, status: int, data: dict) -> None:
                self._send(status, json.dumps(data).encode(), "application/json; charset=utf-8")

            def _deny(self, why: str) -> None:
                self._json(HTTPStatus.FORBIDDEN, {"error": why})

            def _allowed(self) -> bool:
                host = self.headers.get("Host", "")
                hosts = {f"127.0.0.1:{server.port}", f"localhost:{server.port}"}
                if host not in hosts:
                    self._deny("wrong host")
                    return False
                origin = self.headers.get("Origin")
                if origin is not None and origin not in {f"http://{h}" for h in hosts}:
                    self._deny("wrong origin")
                    return False
                site = self.headers.get("Sec-Fetch-Site")
                if site is not None and site not in ("same-origin", "none"):
                    self._deny("cross-site request")
                    return False
                query = parse_qs(urlsplit(self.path).query)
                token = self.headers.get("X-Tilepane-Token") or (query.get("t") or [""])[0]
                if not hmac.compare_digest(token.encode(), server.token.encode()):
                    self._deny("missing or wrong token; open the address tilepane printed")
                    return False
                server._last_request = time.monotonic()
                return True

            def _body(self) -> Optional[dict]:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    length = -1
                if length < 0 or length > MAX_BODY:
                    self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "request too large"})
                    return None
                raw = self.rfile.read(length) if length else b""
                ctype = self.headers.get("Content-Type", "").split(";")[0].strip()
                if ctype != "application/json":
                    self._json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "expected JSON"})
                    return None
                try:
                    data = json.loads(raw or b"{}")
                except ValueError:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid JSON"})
                    return None
                if not isinstance(data, dict):
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "expected a JSON object"})
                    return None
                return data

            def do_GET(self):  # noqa: N802
                route = urlsplit(self.path).path
                if not self._allowed():
                    return
                if route in ("/", "/index.html"):
                    boot = json.dumps({"server": True, "token": server.token}).replace("</", "<\\/")
                    html = docgen.editor_html().replace(
                        '<script id="boot" type="application/json">{}</script>',
                        f'<script id="boot" type="application/json">{boot}</script>', 1)
                    csp = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                           "connect-src 'self'; img-src 'self' data: blob:; base-uri 'none'; "
                           "form-action 'none'; frame-ancestors 'none'")
                    self._send(200, html.encode(), "text/html; charset=utf-8",
                               {"Content-Security-Policy": csp})
                elif route == "/api/state":
                    server._last_ping = time.monotonic()
                    server._bye_at = None
                    self._json(200, {"name": os.path.basename(server.path), "path": server.path,
                                     "home": os.path.expanduser("~"),
                                     "workspaces": server.workspaces(),
                                     "text": server.read_file(), "monitors": server.monitors()})
                else:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

            def do_POST(self):  # noqa: N802
                route = urlsplit(self.path).path
                if not self._allowed():
                    return
                if route == "/api/bye":
                    server._bye_at = time.monotonic()
                    self._json(200, {"ok": True})
                    return
                data = self._body()
                if data is None:
                    return
                if route == "/api/ping":
                    server._last_ping = time.monotonic()
                    server._bye_at = None
                    self._json(200, {"ok": True})
                elif route == "/api/save":
                    text = data.get("text")
                    if not isinstance(text, str):
                        self._json(HTTPStatus.BAD_REQUEST, {"error": "expected 'text'"})
                        return
                    if data.get("path") is not None:
                        status, body = server.save_as(text, data.get("path"), data.get("overwrite") is True)
                        self._json(status, body)
                        return
                    ok, errors, warnings = server.save(text)
                    if ok:
                        self._json(200, {"ok": True, "warnings": warnings})
                    else:
                        self._json(HTTPStatus.UNPROCESSABLE_ENTITY,
                                   {"error": "the layout has problems", "errors": errors})
                elif route == "/api/list":
                    self._json(200, server.list_dir(data.get("dir")))
                elif route == "/api/read":
                    status, body = server.open_file(data.get("path"))
                    self._json(status, body)
                elif route in ("/api/open", "/api/close"):
                    status, body = server.on_screen(route[5:], data.get("layout"), data.get("monitor"))
                    self._json(status, body)
                else:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        return Handler


def monitor_list(detected, work: dict) -> list[dict]:
    """Monitors as the editor wants them: numbers, names, geometry, work area."""
    out = []
    for m in detected:
        d = {"number": m.number, "name": m.name, "x": m.x, "y": m.y,
             "width": m.width, "height": m.height}
        area = work.get(m.number)
        if area is not None:
            d["work"] = {"x": area.x, "y": area.y, "width": area.width, "height": area.height}
        out.append(d)
    return out
