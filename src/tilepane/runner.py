"""Runs inside every terminal window: executes the pane's commands.

Standard library only and no imports from the rest of the package, so it can be
started as a plain script (`python runner.py '<json spec>'`) from any install.
It handles command lists, working directory, environment, `on_exit` and
restarts, so tilepane itself does not have to stay running.

The spec is a JSON object: commands (list of shell command strings), cwd, env,
title, on_exit ("keep" | "close" | "restart"), restart_delay, max_restarts,
stop_on_error, and lifetime (seconds; when set, the pane is stopped and the
window closes when it runs out, whatever on_exit says).
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from typing import Any, Callable, Optional, TextIO


def _expand(value: str) -> str:
    return os.path.expandvars(os.path.expanduser(value))


class _TimeUp(Exception):
    """The pane's lifetime ran out."""


def _stop_group(proc: subprocess.Popen) -> None:
    """Stop the command and everything it started.

    They share the runner's process group (the terminal's foreground group), so
    the whole group is signalled while the runner itself ignores the signal.
    """
    old = signal.signal(signal.SIGTERM, signal.SIG_IGN)
    try:
        os.killpg(0, signal.SIGTERM)
    except OSError:
        proc.terminate()
    finally:
        signal.signal(signal.SIGTERM, old)
    # An interactive shell moves to its own group and ignores SIGTERM; hang it up.
    try:
        group = os.getpgid(proc.pid)
        if group != os.getpgid(0):
            os.killpg(group, signal.SIGHUP)
    except OSError:
        pass
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _wait(argv: list[str], env: Optional[dict], deadline: Optional[float],
          stop: Callable[[subprocess.Popen], None]) -> int:
    proc = subprocess.Popen(argv, env=env)
    if deadline is None:
        return proc.wait()
    try:
        return proc.wait(timeout=max(0.0, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        stop(proc)
        raise _TimeUp from None


def _run_commands(commands: list[str], shell: str, env: dict, stop_on_error: bool,
                  deadline: Optional[float], stop: Callable) -> int:
    status = 0
    for command in commands:
        status = _wait([shell, "-lc", command], env, deadline, stop)
        if status != 0 and stop_on_error:
            break
    return status


def run(spec: dict[str, Any], *, execvp: Callable = os.execvp, sleep: Callable = time.sleep,
        out: Optional[TextIO] = None, stop: Callable = _stop_group) -> int:
    """Run the pane described by `spec`.

    Does not return when it ends in a shell, unless the spec has a lifetime:
    then the shell is a child and the runner returns when time is up.
    """
    out = out or sys.stderr
    shell = os.environ.get("SHELL") or "/bin/sh"
    commands = [c for c in spec.get("commands") or [] if c]
    on_exit = spec.get("on_exit", "keep")
    delay = float(spec.get("restart_delay", 1))
    max_restarts = int(spec.get("max_restarts", 0))
    stop_on_error = bool(spec.get("stop_on_error", False))
    lifetime = spec.get("lifetime")
    deadline = time.monotonic() + float(lifetime) if lifetime else None

    env = os.environ.copy()
    for key, value in (spec.get("env") or {}).items():
        env[key] = _expand(value)

    if spec.get("title"):
        out.write(f"\033]0;{spec['title']}\007")
        out.flush()

    problem = None
    cwd = spec.get("cwd")
    if cwd:
        try:
            os.chdir(_expand(cwd))
        except OSError as exc:
            problem = f"cannot use working directory {cwd!r}: {exc.strerror or exc}"
    if problem:
        print(f"[tilepane] error: {problem}", file=out)
        commands = []

    # A handler (not SIG_IGN) so the commands we start still get default SIGINT.
    signal.signal(signal.SIGINT, lambda *_: None)

    status = 0
    try:
        if commands:
            restarts = 0
            while True:
                status = _run_commands(commands, shell, env, stop_on_error, deadline, stop)
                if on_exit == "close":
                    return status
                if on_exit == "restart":
                    restarts += 1
                    if not max_restarts or restarts <= max_restarts:
                        print(f"[tilepane] exited with status {status}; restarting in "
                              f"{delay:g}s", file=out)
                        if deadline is not None and time.monotonic() + delay >= deadline:
                            raise _TimeUp
                        sleep(delay)
                        continue
                    print(f"[tilepane] reached max_restarts ({max_restarts})", file=out)
                break
            print(f"[tilepane] finished with exit status {status}; starting a shell", file=out)

        signal.signal(signal.SIGINT, signal.SIG_DFL)
        out.flush()
        if deadline is not None:
            return _wait([shell], None, deadline, stop)
        execvp(shell, [shell])
    except _TimeUp:
        return 0
    return status  # only reached when execvp is replaced in tests


def main(argv: Optional[list[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: runner.py '<json spec>'", file=sys.stderr)
        return 2
    try:
        spec = json.loads(argv[0])
    except json.JSONDecodeError as exc:
        print(f"[tilepane] bad runner spec: {exc}", file=sys.stderr)
        return 2
    return run(spec)


if __name__ == "__main__":
    sys.exit(main())
