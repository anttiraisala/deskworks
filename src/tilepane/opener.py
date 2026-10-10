"""Opens the windows of a resolved layout: terminal, window, placement.

Panes are opened one after another. For each pane the terminal is started, the
new window is found by comparing the window list before and after (the class
"tilepane" narrows it down), and the backend moves and sizes it. After the first
window of a terminal is placed, its frame and cell size are known, so later
windows start with an exact `--geometry` and appear in place.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import terminals
from .backends import Backend, BackendError, Placement
from .geometry import LeafRect
from .placement import PlacementError, plan

WINDOW_TIMEOUT = 5.0
_RUNNER = str(Path(__file__).with_name("runner.py"))


@dataclass
class PaneResult:
    id: str
    ok: bool
    terminal: str = ""
    window_id: Optional[int] = None
    pid: Optional[int] = None
    action: str = "opened"          # "opened" or "replaced" (an existing window was moved)
    placement: Optional[Placement] = None
    warnings: list[str] = field(default_factory=list)
    error: Optional[str] = None


class ShellError(ValueError):
    """The pane's shell cannot be used."""


def resolve_shell(setting: Optional[str], *, env: Optional[dict] = None,
                  which: Callable[[str], Optional[str]] = shutil.which) -> str:
    """The shell program for a pane's `shell` setting, as a path."""
    env = os.environ if env is None else env
    if setting in (None, "auto"):
        return env.get("SHELL") or "/bin/sh"
    if "/" in setting:
        path = os.path.expanduser(setting)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
        raise ShellError(f"shell '{setting}' is not an executable file")
    found = which(setting)
    if found is None:
        raise ShellError(f"shell '{setting}' is not installed")
    return found


def runner_spec(leaf: dict, lifetime: Optional[float] = None,
                shell: Optional[str] = None) -> dict:
    run = leaf.get("run")
    spec = {
        "commands": [] if run is None else [run] if isinstance(run, str) else list(run),
        "cwd": leaf.get("cwd"),
        "env": leaf.get("env") or {},
        "title": leaf.get("title"),
        "on_exit": leaf.get("on_exit", "keep"),
        "restart_delay": leaf.get("restart_delay", 1),
        "max_restarts": leaf.get("max_restarts", 0),
        "stop_on_error": leaf.get("stop_on_error", False),
    }
    if lifetime:
        spec["lifetime"] = lifetime
    if shell:
        spec["shell"] = shell
    return spec


def requested_extras(leaf: dict) -> list[str]:
    """Leaf settings that only some terminals can honor, as far as the leaf asks for them."""
    asked = []
    if leaf.get("decorations") is False:
        asked.append("decorations")
    if leaf.get("profile"):
        asked.append("profile")
    if leaf.get("font_size"):
        asked.append("font_size")
    return asked


def default_title(leaf: dict) -> str:
    if leaf.get("title"):
        return leaf["title"]
    run = leaf.get("run")
    first = run if isinstance(run, str) else (run[0] if run else "")
    return (first[:40] or "tilepane")


class Opener:
    def __init__(self, backend: Backend, *,
                 popen: Callable = subprocess.Popen,
                 resolve_terminal: Callable = terminals.resolve,
                 timeout: float = WINDOW_TIMEOUT,
                 lifetime: Optional[float] = None):
        self.backend = backend
        self.lifetime = lifetime        # --for: seconds before every new window closes
        self.popen = popen
        self.resolve_terminal = resolve_terminal
        self.timeout = timeout
        self._metrics: dict[str, tuple] = {}

    def open_layout(self, leaves: list[LeafRect],
                    on_result: Optional[Callable[[PaneResult], None]] = None) -> list[PaneResult]:
        results = []
        for lr in leaves:
            if lr.leaf.get("empty"):
                continue
            result = self.open_pane(lr)
            results.append(result)
            if on_result:
                on_result(result)
        return results

    def _geometry(self, term: terminals.Terminal, lr: LeafRect):
        """An exact --geometry from metrics learned on an earlier window, if any."""
        known = self._metrics.get(term.name)
        if known is None:
            return None
        frame, gtk, hints = known
        if hints is None:
            return None
        try:
            p = plan(lr.rect, frame, gtk, hints, lr.leaf.get("snap", "cell"))
        except PlacementError:
            return None
        if p.cols is None or p.rows is None:
            return None
        return terminals.Geometry(p.cols, p.rows, p.x, p.y)

    def open_pane(self, lr: LeafRect) -> PaneResult:
        leaf = lr.leaf
        pane_id = leaf.get("id", lr.id)
        result = PaneResult(pane_id, ok=False)
        try:
            term = self.resolve_terminal(leaf.get("terminal", "auto"))
        except terminals.TerminalError as exc:
            result.error = str(exc)
            return result
        result.terminal = term.name

        for key in requested_extras(leaf):
            if key in term.unsupported:
                result.warnings.append(f"{term.name} cannot honor '{key}' yet; ignored")
        if leaf.get("mode", "sequence") != "sequence":
            result.warnings.append(f"mode '{leaf['mode']}' is not implemented yet; "
                                   "the commands run in sequence")

        try:
            shell = resolve_shell(leaf.get("shell", "auto"))
        except ShellError as exc:
            result.error = str(exc)
            return result

        argv = [sys.executable, _RUNNER, json.dumps(runner_spec(leaf, self.lifetime, shell))]
        req = terminals.LaunchRequest(
            title=default_title(leaf), argv=argv, geometry=self._geometry(term, lr),
            x=lr.rect.x, y=lr.rect.y, width=lr.rect.width, height=lr.rect.height)
        command = term.command(req)

        before = self.backend.windows()
        try:
            self.popen(command, start_new_session=True, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            result.error = f"cannot start {term.name}: {exc}"
            return result

        win = self.backend.wait_new_window(
            before, lambda info: term.matches(info.wm_class), self.timeout)
        if win is None:
            result.error = f"no {term.name} window appeared within {self.timeout:g} s"
            return result
        result.window_id = win.id
        result.pid = win.pid

        try:
            placement = self.backend.place(win.id, lr.rect, leaf.get("snap", "cell"),
                                           leaf.get("decorations", True))
        except (BackendError, PlacementError) as exc:
            result.error = f"window opened but could not be placed: {exc}"
            return result
        result.placement = placement
        result.warnings += placement.notes
        if term.name not in self._metrics:
            got = self.backend.metrics(win.id)
            if got is not None:
                self._metrics[term.name] = got
        result.ok = True
        return result
