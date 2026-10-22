import http.client
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path

from tilepane import docgen, geometry
from tilepane.editor import server as editor_server
from tilepane.geometry import Rect
from tilepane.invocation import UsageError, parse

ROOT = Path(__file__).resolve().parent.parent
VECTORS = ROOT / "tests" / "vectors" / "geometry.json"
MONITORS = [{"number": 0, "name": "DP-1", "x": 0, "y": 0, "width": 1920, "height": 1080},
            {"number": 1, "name": "HDMI-1", "x": 1920, "y": 0, "width": 2560, "height": 1440,
             "work": {"x": 1920, "y": 30, "width": 2560, "height": 1410}}]
LAYOUT = {"name": "two", "split": {"dir": "columns", "a": {"run": "htop"}, "b": {}}}


class GeometryVectorTest(unittest.TestCase):
    def test_python_still_gives_the_recorded_rectangles(self):
        cases = json.loads(VECTORS.read_text())
        self.assertGreater(len(cases), 300)
        for c in cases:
            try:
                got = [[lr.id, lr.rect.x, lr.rect.y, lr.rect.width, lr.rect.height,
                        lr.outer.x, lr.outer.y, lr.outer.width, lr.outer.height]
                       for lr in geometry.compute(c["layout"], Rect(*c["area"]))]
            except geometry.GeometryError:
                got = None
            self.assertEqual(got, c["expected"], c["name"])

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_javascript_gives_the_same_rectangles(self):
        proc = subprocess.run(["node", str(ROOT / "tests" / "js" / "geometry.test.mjs")],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class EditorFileTest(unittest.TestCase):
    def test_embedded_schema_is_current(self):
        self.assertEqual(docgen.EDITOR_PATH.read_text(encoding="utf-8"), docgen.editor_html(),
                         "run: python -m tilepane.docgen")

    def test_page_is_self_contained(self):
        html = docgen.EDITOR_PATH.read_text(encoding="utf-8")
        for needle in ("<script src", "<link rel=\"stylesheet", "@import", "http://", "url("):
            self.assertNotIn(needle, html.replace("http://json-schema.org", ""), needle)


class EditParseTest(unittest.TestCase):
    def test_edit_options(self):
        inv = parse(["--edit", "a.json", "--no-browser"])
        self.assertEqual((inv.action, inv.tasks[0].source, inv.no_browser), ("edit", "a.json", True))
        self.assertEqual(parse(["--edit"]).action, "edit")
        for argv in (["--edit", "a.json", "b.json"], ["--edit", "a.json", "three"]):
            with self.subTest(argv=argv), self.assertRaises(UsageError):
                parse(argv)


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "layout.json")
        with open(self.path, "w") as fh:
            json.dump(LAYOUT, fh)
        self.calls = []
        self.prefs = os.path.join(self.tmp.name, "prefs", "editor.json")
        self.srv = editor_server.EditorServer(self.path, lambda: MONITORS, cli=self.fake_cli,
                                              workspaces=lambda: 4, prefs_path=self.prefs)
        self.thread = threading.Thread(target=self.srv.serve, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.srv.stop()
        self.thread.join(5)

    def fake_cli(self, args):
        self.calls.append(args)
        return 0, "opened"

    def request(self, method, path, body=None, headers=None, token=True, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.srv.port, timeout=5)
        h = {"Host": host or f"127.0.0.1:{self.srv.port}"}
        if token:
            h["X-Tilepane-Token"] = self.srv.token
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        h.update(headers or {})
        conn.request(method, path, body=data, headers=h)
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        try:
            return resp.status, json.loads(raw), resp
        except ValueError:
            return resp.status, raw.decode(), resp

    def test_page_needs_the_token_and_gets_it_injected(self):
        status, _, _ = self.request("GET", "/", token=False)
        self.assertEqual(status, 403)
        status, html, resp = self.request("GET", f"/?t={self.srv.token}", token=False)
        self.assertEqual(status, 200)
        self.assertIn(f'"token": "{self.srv.token}"', html)
        self.assertIn("frame-ancestors 'none'", resp.getheader("Content-Security-Policy"))
        self.assertEqual(resp.getheader("Referrer-Policy"), "no-referrer")

    def test_wrong_token_host_or_origin_is_refused(self):
        self.assertEqual(self.request("GET", "/api/state", headers={"X-Tilepane-Token": "nope"})[0], 403)
        self.assertEqual(self.request("GET", "/api/state", host="evil.example:80")[0], 403)
        self.assertEqual(self.request("GET", "/api/state", host=f"attacker.test:{self.srv.port}")[0], 403)
        self.assertEqual(self.request("POST", "/api/ping", {}, headers={"Origin": "http://evil.example"})[0], 403)
        self.assertEqual(self.request("POST", "/api/ping", {}, headers={"Sec-Fetch-Site": "cross-site"})[0], 403)
        self.assertEqual(self.request("GET", "/api/state", host=f"localhost:{self.srv.port}")[0], 200)
        ok = self.request("POST", "/api/ping", {}, headers={"Origin": f"http://127.0.0.1:{self.srv.port}"})
        self.assertEqual(ok[0], 200)

    def test_state_has_the_file_and_monitors(self):
        status, data, _ = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data["text"]), LAYOUT)
        self.assertEqual((data["name"], data["monitors"], data["workspaces"]), ("layout.json", MONITORS, 4))

    def test_save_without_a_path_writes_the_current_file(self):
        text = json.dumps({"name": "new", "split": {}}, indent=2) + "\n"
        status, data, _ = self.request("POST", "/api/save", {"text": text})
        self.assertEqual(status, 200, data)
        self.assertEqual(Path(self.path).read_text(), text)
        self.assertEqual(sorted(os.listdir(self.tmp.name)), ["layout.json"])

    def test_save_as_writes_the_new_file_and_makes_it_current(self):
        text = json.dumps({"name": "new", "split": {}}, indent=2) + "\n"
        other = os.path.join(self.tmp.name, "other.json")
        before = Path(self.path).read_text()
        status, data, _ = self.request("POST", "/api/save", {"text": text, "path": other})
        self.assertEqual((status, data["path"], data["name"]), (200, other, "other.json"), data)
        self.assertEqual(Path(other).read_text(), text)
        self.assertEqual(Path(self.path).read_text(), before)      # the old file is left alone
        status, data, _ = self.request("GET", "/api/state")
        self.assertEqual(data["path"], other)
        remembered = json.loads(Path(self.prefs).read_text())
        self.assertEqual((remembered["last_dir"], remembered["recent"][0]), (self.tmp.name, other))

    def test_save_as_anywhere_the_system_allows_but_only_json(self):
        text = json.dumps({"name": "new", "split": {}})
        for bad in ("notes.txt", "", "~/.bashrc", self.tmp.name + "/"):
            with self.subTest(bad=bad):
                status, data, _ = self.request("POST", "/api/save", {"text": text, "path": bad})
                self.assertEqual(status, 400, data)
        status, data, _ = self.request("POST", "/api/save", {"text": text, "path": "/nonexistent-dir/x.json"})
        self.assertEqual(status, 400)
        self.assertIn("does not exist", data["error"])

    def test_save_as_asks_before_replacing_a_file(self):
        text = json.dumps({"name": "new", "split": {}})
        other = os.path.join(self.tmp.name, "other.json")
        Path(other).write_text('{"hello": 1}')
        status, data, _ = self.request("POST", "/api/save", {"text": text, "path": other})
        self.assertEqual((status, data["exists"], data["not_a_layout"]), (409, True, True))
        self.assertEqual(Path(other).read_text(), '{"hello": 1}')
        Path(other).write_text(json.dumps(LAYOUT))
        status, data, _ = self.request("POST", "/api/save", {"text": text, "path": other})
        self.assertEqual((status, data["not_a_layout"]), (409, False))
        status, data, _ = self.request("POST", "/api/save", {"text": text, "path": other, "overwrite": True})
        self.assertEqual(status, 200, data)
        self.assertEqual(Path(other).read_text(), text)

    def test_save_as_the_current_file_needs_no_confirmation(self):
        text = json.dumps({"name": "new", "split": {}})
        status, data, _ = self.request("POST", "/api/save", {"text": text, "path": self.path})
        self.assertEqual(status, 200, data)

    def test_save_as_validates_the_layout(self):
        other = os.path.join(self.tmp.name, "other.json")
        status, data, _ = self.request("POST", "/api/save", {"text": '{"split": {"run": 3}}', "path": other})
        self.assertEqual(status, 422)
        self.assertFalse(os.path.exists(other))

    def test_list_shows_folders_and_json_files_and_remembers_the_last_folder(self):
        os.mkdir(os.path.join(self.tmp.name, "sub"))
        Path(self.tmp.name, "notes.txt").write_text("x")
        Path(self.tmp.name, ".hidden.json").write_text("{}")
        status, data, _ = self.request("POST", "/api/list", {"dir": self.tmp.name})
        self.assertEqual(status, 200)
        self.assertEqual(data["dir"], self.tmp.name)
        self.assertEqual(data["entries"], [{"name": "sub", "kind": "dir"}, {"name": "layout.json", "kind": "file"}])
        status, data, _ = self.request("POST", "/api/list", {"dir": self.tmp.name + "/missing/deeper"})
        self.assertEqual(data["dir"], self.tmp.name)                  # the nearest folder that exists
        other = os.path.join(self.tmp.name, "sub", "o.json")
        self.request("POST", "/api/save", {"text": json.dumps({"split": {}}), "path": other})
        status, data, _ = self.request("POST", "/api/list", {})
        self.assertEqual((data["dir"], data["recent"]), (os.path.join(self.tmp.name, "sub"), [other]))

    def test_read_opens_a_file_and_makes_it_current(self):
        other = os.path.join(self.tmp.name, "other.json")
        Path(other).write_text('{"split": {}}')
        status, data, _ = self.request("POST", "/api/read", {"path": other})
        self.assertEqual((status, data["text"], data["name"]), (200, '{"split": {}}', "other.json"))
        self.assertEqual(self.request("GET", "/api/state")[1]["path"], other)
        for bad, code in ((os.path.join(self.tmp.name, "none.json"), 404), ("x.txt", 400)):
            self.assertEqual(self.request("POST", "/api/read", {"path": bad})[0], code)

    def test_the_new_routes_need_the_token(self):
        for route in ("/api/list", "/api/read"):
            self.assertEqual(self.request("POST", route, {"path": self.path}, token=False)[0], 403)

    def test_invalid_layout_is_not_saved(self):
        before = Path(self.path).read_text()
        status, data, _ = self.request("POST", "/api/save", {"text": '{"name": "x", "split": {"run": 3}}'})
        self.assertEqual(status, 422)
        self.assertTrue(any("run" in e for e in data["errors"]))
        status, data, _ = self.request("POST", "/api/save", {"text": "{ not json"})
        self.assertEqual(status, 422)
        self.assertEqual(Path(self.path).read_text(), before)

    def test_post_needs_json(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.srv.port, timeout=5)
        conn.request("POST", "/api/save", body="text=x", headers={
            "Host": f"127.0.0.1:{self.srv.port}", "X-Tilepane-Token": self.srv.token,
            "Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(conn.getresponse().status, 415)
        conn.close()

    def test_open_on_screen_checks_layout_and_monitor(self):
        status, data, _ = self.request("POST", "/api/open", {"layout": "two", "monitor": 1})
        self.assertEqual((status, data["code"]), (200, 0))
        self.assertEqual(self.calls[-1], ["--json", self.path, "--layout", "two", "--monitor", "1"])
        status, _, _ = self.request("POST", "/api/close", {"layout": "two", "monitor": 0})
        self.assertEqual(self.calls[-1][0], "--close")
        for body in ({"layout": "nope", "monitor": 0}, {"layout": "two", "monitor": 9},
                     {"layout": "two", "monitor": "0; rm -rf /"}, {"layout": ["two"], "monitor": 0}):
            with self.subTest(body=body):
                self.assertEqual(self.request("POST", "/api/open", body)[0], 400)
        self.assertEqual(len(self.calls), 2)

    def test_goodbye_stops_the_server(self):
        self.srv.bye_grace = 0.1
        self.request("POST", f"/api/bye?t={self.srv.token}", token=False)
        self.thread.join(3)
        self.assertFalse(self.thread.is_alive())
        self.assertEqual(self.srv.stop_reason, "the editor tab was closed")

    def test_reload_after_goodbye_keeps_it_running(self):
        self.srv.bye_grace = 0.5
        self.request("POST", "/api/bye")
        self.request("GET", "/api/state")
        time.sleep(0.8)
        self.assertTrue(self.thread.is_alive())

    def test_idle_timeout(self):
        self.srv.idle_timeout = 0.2
        self.thread.join(3)
        self.assertEqual(self.srv.stop_reason, "idle timeout")


class NewFileServerTest(unittest.TestCase):
    def test_missing_file_is_created_on_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sub", "config.json")
            srv = editor_server.EditorServer(path, lambda: [])
            self.assertIsNone(srv.read_file())
            ok, errors, _ = srv.save(json.dumps({"name": "a", "split": {}}))
            self.assertTrue(ok, errors)
            self.assertTrue(os.path.exists(path))
            srv._httpd.server_close()


def _playwright_dir():
    for d in (os.environ.get("PLAYWRIGHT_DIR"), "/opt/node-tools/node_modules"):
        if d and os.path.isdir(os.path.join(d, "playwright")):
            return d
    return None


@unittest.skipUnless(shutil.which("node") and _playwright_dir(), "node and playwright are not installed")
class BrowserTest(unittest.TestCase):
    """Drives the editor in Chromium: tests/js/editor.features.mjs (page opened as a file) and
    tests/js/editor.e2e.mjs (served by the editor server: split, drag, edit, validate, save)."""

    def test_editor_features(self):
        env = dict(os.environ, PLAYWRIGHT_DIR=_playwright_dir() + "/")
        proc = subprocess.run(["node", str(ROOT / "tests" / "js" / "editor.features.mjs")],
                              capture_output=True, text=True, timeout=120, env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_editor_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "e2e.json")
            with open(path, "w") as fh:
                json.dump({"name": "e2e", "margin": 8, "split": {
                    "dir": "columns", "at": "60%", "a": {"run": "top", "title": "top"}, "b": {}},
                    "my_note": "kept"}, fh, indent=2)
            srv = editor_server.EditorServer(path, lambda: MONITORS[:1])
            thread = threading.Thread(target=srv.serve, daemon=True)
            thread.start()
            try:
                env = dict(os.environ, PLAYWRIGHT_DIR=_playwright_dir() + "/")
                proc = subprocess.run(["node", str(ROOT / "tests" / "js" / "editor.e2e.mjs"), srv.url],
                                      capture_output=True, text=True, timeout=120, env=env)
            finally:
                srv.stop()
                thread.join(5)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            saved = json.loads(Path(path).read_text())
            self.assertEqual(saved["my_note"], "kept")
            self.assertEqual(list(saved), ["name", "margin", "split", "my_note"])
            self.assertEqual(saved["split"]["b"]["b"]["run"], ["date", "whoami", "ls"])
            self.assertRegex(saved["split"]["at"], r"^[23]\d(\.\d)?%$")
