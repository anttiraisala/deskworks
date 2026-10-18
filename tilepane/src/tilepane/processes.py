"""What runs in a terminal window: the command a pane should start, read from /proc.

A terminal window has a process (for xterm the terminal itself, for gnome-terminal a server shared by all its
windows). The shells below it are not interesting; the deepest process that is not a shell is what runs there.
Windows that tilepane opened run its `runner.py`; its settings are read back from the command line, so such
a window gives its own pane again (commands, directory, title, what to do at the end).
"""

from __future__ import annotations

import json
import os
import shlex
from typing import Optional

SHELLS = {"sh", "bash", "dash", "zsh", "fish", "ksh", "tcsh", "csh", "ash"}


def _children(proc: str) -> dict[int, list[int]]:
    kids: dict[int, list[int]] = {}
    try:
        names = os.listdir(proc)
    except OSError:
        return kids
    for name in names:
        if not name.isdigit():
            continue
        try:
            with open(os.path.join(proc, name, "stat"), "rb") as fh:
                text = fh.read().decode(errors="replace")
            ppid = int(text[text.rindex(")") + 1:].split()[1])
        except (OSError, ValueError, IndexError):
            continue
        kids.setdefault(ppid, []).append(int(name))
    return kids


def _cmdline(proc: str, pid: int) -> list[str]:
    try:
        with open(os.path.join(proc, str(pid), "cmdline"), "rb") as fh:
            return [a.decode(errors="replace") for a in fh.read().split(b"\0") if a]
    except OSError:
        return []


def _cwd(proc: str, pid: int) -> Optional[str]:
    try:
        return os.readlink(os.path.join(proc, str(pid), "cwd"))
    except OSError:
        return None


def _tilde(path: str, home: Optional[str]) -> str:
    home = (home or "").rstrip("/")
    if home and (path == home or path.startswith(home + "/")):
        return "~" + path[len(home):]
    return path


def pane_from_runner(argv: list[str]) -> Optional[dict]:
    """The pane settings in the command line of tilepane's runner, or None when it is not one."""
    for i, arg in enumerate(argv[:-1]):
        if os.path.basename(arg) == "runner.py":
            try:
                spec = json.loads(argv[i + 1])
            except ValueError:
                return None
            if not isinstance(spec, dict):
                return None
            pane: dict = {}
            commands = spec.get("commands")
            if isinstance(commands, list) and commands:
                pane["run"] = commands[0] if len(commands) == 1 else commands
            for key in ("cwd", "title", "on_exit"):
                if isinstance(spec.get(key), str) and spec[key]:
                    pane[key] = spec[key]
            return pane
    return None


def terminal_pane(pid: Optional[int], *, proc: str = "/proc", home: Optional[str] = None) -> Optional[dict]:
    """The settings (`run`, `cwd`) of the pane that a terminal with this process shows, or None when the
    terminal runs only a shell or the process cannot be read."""
    if pid is None:
        return None
    kids = _children(proc)
    best: Optional[tuple[int, int]] = None      # (depth, pid)
    stack = [(pid, 0)]
    seen = set()
    while stack:
        cur, depth = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        for child in sorted(kids.get(cur, []), reverse=True):
            stack.append((child, depth + 1))
        if cur == pid:
            continue
        argv = _cmdline(proc, cur)
        from_runner = pane_from_runner(argv)
        if from_runner is not None:
            return from_runner                  # a window tilepane opened: its own settings
        if not argv or os.path.basename(argv[0]).lstrip("-") in SHELLS:
            continue
        if best is None or (depth, -cur) > (best[0], -best[1]):
            best = (depth, cur)
    if best is None:
        return None
    argv = _cmdline(proc, best[1])
    pane = {"run": shlex.join(argv)}
    cwd = _cwd(proc, best[1])
    if cwd:
        pane["cwd"] = _tilde(cwd, home or os.path.expanduser("~"))
    return pane
