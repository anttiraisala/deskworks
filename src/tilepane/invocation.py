"""Command line parsing: options and tasks, in order (SPEC.md sections 1 and 14)."""

from __future__ import annotations

import difflib
import os
from dataclasses import dataclass, field
from typing import Optional

from .demo import DemoError, parse_duration

HELP = """\
usage: tilepane [options] [FILE.json | LAYOUT ...]

Open terminal windows at precisely defined screen positions.

  tilepane meters.json [NAME]            open a layout file (NAME if it has several)
  tilepane 3 5                           layouts 3 and 5 from the default config
  tilepane --json a.json --monitor 0 --json b.json --monitor 1
                                         several tasks; --monitor and --layout
                                         belong to the task before them
  tilepane --dry-run FILE [NAME]         print the computed rectangles only
  tilepane --close 3                     close the windows of layout 3 on this workspace
                                         (--close all: everything; --workspace all: everywhere)
  tilepane --toggle 3                    open if closed, close if open
  tilepane --demo [N]                    random layout with N fun commands (3-6 by default)
  tilepane --list [FILE]                 list layouts
  tilepane --explain KEY                 describe a configuration key
  tilepane --monitors                    list monitors (numbers, names, sizes)
  tilepane --doctor                      print environment info

options:
  --json FILE, --config FILE   start a task with this layout file
  --layout NAME                select a layout in the current task
  --monitor SPEC               number, connector, alias, primary, all; comma-separated
  --workspace SPEC             current (default), a workspace number (1 = first),
                               or with --close: all
  --dry-run                    compute and print, open nothing
  --eval-when                  with --dry-run: evaluate 'when' conditions
  --prune                      when re-opening, close windows whose pane no longer exists
  --for DURATION               close the new windows after this long (30s, 5m, 1h)
  --seed S                     with --demo: repeat an earlier demo
  --save FILE                  with --demo: also write the layout to FILE
  --strict                     unknown configuration keys are errors
  --wait-monitors SECONDS      retry monitor detection for up to this long
  -v, --verbose                print more detail
  --version, -h, --help

Default config: $XDG_CONFIG_HOME/tilepane/config.json (~/.config/tilepane/config.json).
Key reference: docs/CONFIG.md, or tilepane --explain KEY.
"""

VALUE_OPTIONS = {"--json", "--config", "--layout", "--monitor", "--explain", "--wait-monitors",
                 "--for", "--seed", "--save", "--workspace"}
FLAG_OPTIONS = {"--dry-run", "--eval-when", "--strict", "--verbose", "-v", "--doctor",
                "--close", "--toggle", "--prune", "--demo",
                "--monitors", "--list", "--version", "--help", "-h"}
# Options from SPEC.md that exist but are built in a later step.
NOT_YET = {"--edit": 8, "--watch": 9}
ALL_OPTIONS = VALUE_OPTIONS | FLAG_OPTIONS | set(NOT_YET)


class UsageError(Exception):
    """The command line is wrong."""


@dataclass
class Task:
    source: Optional[str] = None          # layout file; None means the default config
    layouts: list[str] = field(default_factory=list)
    monitor: Optional[str] = None         # raw --monitor value; None means unset


@dataclass
class Invocation:
    action: str = "run"                   # run, help, version, doctor, monitors, list, explain, close, toggle, demo
    tasks: list[Task] = field(default_factory=list)
    dry_run: bool = False
    eval_when: bool = False
    prune: bool = False
    strict: bool = False
    verbose: bool = False
    wait_monitors: float = 0.0
    explain: Optional[str] = None
    default_monitor: Optional[str] = None
    demo_panes: Optional[int] = None      # --demo N; None means a random count
    seed: Optional[str] = None
    save: Optional[str] = None
    lifetime: Optional[float] = None      # --for, in seconds
    workspace: str = "current"            # "current", "all" or a 1-based number


def is_file_argument(arg: str) -> bool:
    return os.path.isfile(arg) or arg.lower().endswith(".json")


def parse(argv: list[str]) -> Invocation:
    inv = Invocation()
    current: Optional[Task] = None
    actions: list[str] = []

    def new_task(source: Optional[str]) -> Task:
        task = Task(source=source)
        inv.tasks.append(task)
        return task

    i = 0
    only_positional = False
    while i < len(argv):
        arg = argv[i]
        i += 1
        if only_positional or not arg.startswith("-") or arg == "-":
            if is_file_argument(arg):
                current = new_task(arg)
            else:
                current = current or new_task(None)
                current.layouts.append(arg)
            continue
        if arg == "--":
            only_positional = True
            continue

        opt, has_value, inline = arg.partition("=") if arg.startswith("--") else (arg, "", "")
        if opt in NOT_YET:
            raise UsageError(f"{opt} is not implemented yet (planned for step {NOT_YET[opt]} "
                             "of SPEC.md section 7)")
        if opt not in ALL_OPTIONS:
            hint = difflib.get_close_matches(opt, sorted(ALL_OPTIONS), n=1, cutoff=0.6)
            raise UsageError(f"unknown option '{opt}'" + (f" (did you mean '{hint[0]}'?)" if hint else ""))

        value = ""
        if opt in VALUE_OPTIONS:
            if has_value:
                value = inline
            elif i < len(argv) and not (argv[i].startswith("-") and len(argv[i]) > 1):
                value, i = argv[i], i + 1
            else:
                raise UsageError(f"{opt} needs a value")
            if value == "":
                raise UsageError(f"{opt} needs a value")
        elif opt == "--demo":
            # The pane count is optional: --demo, --demo 4, --demo=4.
            count = inline if has_value else (argv[i] if i < len(argv) and argv[i].isdigit() else None)
            if count is not None and not has_value:
                i += 1
            if count is not None:
                if not count.isdigit() or int(count) < 1:
                    raise UsageError(f"--demo takes a number of panes, got '{count}'")
                inv.demo_panes = int(count)
        elif has_value:
            raise UsageError(f"{opt} does not take a value")

        if opt in ("--json", "--config"):
            current = new_task(value)
        elif opt == "--layout":
            current = current or new_task(None)
            current.layouts.append(value)
        elif opt == "--monitor":
            if current is None:
                if inv.default_monitor is not None:
                    raise UsageError("--monitor given twice before the first task")
                inv.default_monitor = value
            elif current.monitor is not None:
                raise UsageError("--monitor given twice for the same task "
                                 "(use a comma-separated list for several monitors)")
            else:
                current.monitor = value
        elif opt == "--explain":
            inv.explain = value
            actions.append("explain")
        elif opt == "--wait-monitors":
            try:
                inv.wait_monitors = float(value)
            except ValueError:
                raise UsageError(f"--wait-monitors needs a number of seconds, got '{value}'") from None
            if inv.wait_monitors < 0:
                raise UsageError("--wait-monitors must not be negative")
        elif opt == "--for":
            try:
                inv.lifetime = parse_duration(value)
            except DemoError as exc:
                raise UsageError(str(exc)) from None
        elif opt == "--workspace":
            if value not in ("current", "all") and not (value.isdigit() and int(value) >= 1):
                raise UsageError(f"--workspace takes current, all or a workspace number "
                                 f"(1 = first), got '{value}'")
            inv.workspace = value
        elif opt == "--seed":
            inv.seed = value
        elif opt == "--save":
            inv.save = value
        elif opt == "--demo":
            actions.append("demo")
        elif opt == "--dry-run":
            inv.dry_run = True
        elif opt == "--eval-when":
            inv.eval_when = True
        elif opt == "--prune":
            inv.prune = True
        elif opt in ("--close", "--toggle"):
            actions.append(opt[2:])
        elif opt == "--strict":
            inv.strict = True
        elif opt in ("--verbose", "-v"):
            inv.verbose = True
        elif opt in ("--help", "-h"):
            actions.append("help")
        elif opt == "--version":
            actions.append("version")
        elif opt == "--doctor":
            actions.append("doctor")
        elif opt == "--monitors":
            actions.append("monitors")
        elif opt == "--list":
            actions.append("list")

    if "close" in actions and "toggle" in actions:
        raise UsageError("--close and --toggle cannot be combined")
    if "demo" in actions:
        if inv.tasks:
            raise UsageError("--demo makes its own layout; it cannot be combined with files or layout names")
        if "close" in actions or "toggle" in actions:
            raise UsageError("--demo cannot be combined with --close or --toggle (use --close all)")
    elif inv.seed is not None or inv.save is not None:
        raise UsageError(f"{'--seed' if inv.seed is not None else '--save'} only works with --demo")
    for action in ("help", "version", "doctor", "monitors", "explain", "list", "close", "toggle",
                   "demo"):
        if action in actions:
            inv.action = action
            break
    else:
        if not argv:
            inv.action = "help"
    if inv.workspace == "all" and inv.action != "close":
        raise UsageError("--workspace all only works with --close")
    if inv.action in ("close", "toggle") and not inv.tasks:
        raise UsageError(f"--{inv.action} needs a layout name or a file"
                         + (" (or 'all')" if inv.action == "close" else ""))
    return inv
