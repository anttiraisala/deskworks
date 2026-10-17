"""--exit-shell: close the terminal tilepane was started from.

After everything opened (or closed) without errors, tilepane hangs up the
interactive shell it was typed into. The shell exits and its terminal closes
that tab or window by itself, whatever the terminal is. Nothing happens when
tilepane was not started from an interactive shell on a terminal (a keyboard
shortcut, autostart, a script), so it never closes something unexpected. The
windows tilepane opened run in their own sessions and are not affected.
"""

from __future__ import annotations

import os
import signal
import sys
from typing import Callable, Optional

SHELLS = {"bash", "zsh", "fish", "sh", "dash", "ksh", "mksh", "tcsh", "csh", "yash", "nu", "elvish", "xonsh"}


def parent_shell(ppid: Optional[int] = None,
                 read: Callable[[str], str] = lambda p: open(p, encoding="utf-8").read(),
                 isatty: Callable[[int], bool] = os.isatty) -> tuple[Optional[int], str]:
    """(pid of the interactive shell that started us, "") or (None, why not)."""
    ppid = os.getppid() if ppid is None else ppid
    if ppid <= 1:
        return None, "tilepane has no parent shell"
    if not isatty(0):
        return None, "tilepane was not started from a terminal"
    try:
        name = read(f"/proc/{ppid}/comm").strip()
    except OSError:
        return None, "the parent process cannot be read"
    name = name.lstrip("-")
    if name not in SHELLS:
        return None, f"tilepane was started by '{name}', not by a shell"
    return ppid, ""


def exit_shell(out=None, *, find: Callable = parent_shell, kill: Callable = os.kill) -> bool:
    """Hang up the launching shell; returns True when it was told to exit."""
    out = out or sys.stderr
    pid, why = find()
    if pid is None:
        print(f"note: --exit-shell: {why}; nothing was closed", file=out)
        return False
    out.flush()
    try:
        kill(pid, signal.SIGHUP)
    except OSError as exc:
        print(f"note: --exit-shell: cannot close the shell: {exc}", file=out)
        return False
    return True
