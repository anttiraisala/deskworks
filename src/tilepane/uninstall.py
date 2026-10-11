"""--uninstall: remove tilepane (and with --purge, its layouts).

`--uninstall` closes the windows tilepane opened, deletes its state directory
and removes the program with the tool it was installed with (pipx or pip,
editable installs included). The layouts in tilepane's config directory are
kept. `--purge` also deletes that directory. Layout files elsewhere and the
cloned repository are not touched; the summary says so. Nothing happens
before the user confirms (or gave --yes).
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Callable, Optional

from . import config, state


@dataclass
class Plan:
    state_dir: str
    config_dir: str
    config_files: list[str] = field(default_factory=list)
    command: Optional[list[str]] = None     # removes the program; None: nothing installed
    how: str = ""                           # pipx, pip, pip (editable), or why nothing


def installed_how(prefix: Optional[str] = None, dist_lookup: Callable = importlib.metadata.distribution,
                  which: Callable = shutil.which) -> tuple[Optional[list[str]], str]:
    """The command that removes the installed program, and how it was installed."""
    prefix = sys.prefix if prefix is None else prefix
    try:
        dist = dist_lookup("tilepane")
    except importlib.metadata.PackageNotFoundError:
        return None, "tilepane is not installed as a package (it runs from the source folder)"
    editable = False
    try:
        direct = dist.read_text("direct_url.json")
        editable = bool(direct and json.loads(direct).get("dir_info", {}).get("editable"))
    except (OSError, ValueError):
        pass
    if os.path.exists(os.path.join(prefix, "pipx_metadata.json")):
        # pipx keeps its own records; only pipx itself removes the app cleanly.
        pipx = which("pipx")
        if pipx is None:
            return None, "tilepane was installed with pipx, but pipx is not on PATH; run: pipx uninstall tilepane"
        return [pipx, "uninstall", "tilepane"], "pipx" + (" (editable)" if editable else "")
    return [sys.executable, "-m", "pip", "uninstall", "-y", "tilepane"], "pip" + (" (editable)" if editable else "")


def make_plan(purge: bool, how: Optional[Callable] = None) -> Plan:
    config_dir = os.path.dirname(config.default_config_path())
    plan = Plan(state.state_dir(), config_dir)
    if os.path.isdir(config_dir):
        for root, _dirs, files in os.walk(config_dir):
            plan.config_files += [os.path.join(root, f) for f in sorted(files)]
    plan.command, plan.how = (how or installed_how)()
    return plan


def describe(plan: Plan, purge: bool, windows: Optional[int]) -> list[str]:
    lines = ["This removes tilepane:"]
    if windows is None:
        lines.append("  - (the window system cannot be reached, so open tilepane windows stay open)")
    elif windows:
        lines.append(f"  - closes the {windows} window(s) tilepane opened (on every workspace)")
    if os.path.exists(plan.state_dir):
        lines.append(f"  - deletes {plan.state_dir}/")
    if plan.command:
        lines.append(f"  - removes the program ({plan.how}): {' '.join(plan.command)}")
    else:
        lines.append(f"  - {plan.how}; no program to remove")
    if purge:
        if plan.config_files:
            lines.append(f"  - deletes your layouts in {plan.config_dir}/:")
            lines += [f"      {f}" for f in plan.config_files]
        else:
            lines.append(f"  - {plan.config_dir}/ holds no layouts")
    elif plan.config_files:
        lines.append(f"Your layouts are kept: {plan.config_dir}/ ({len(plan.config_files)} file(s)); "
                     "--purge deletes them too.")
    return lines


def remove_dir(path: str) -> None:
    if os.path.isdir(path):
        shutil.rmtree(path)


def run_command(cmd: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    except OSError as exc:
        return 1, str(exc)
    return proc.returncode, (proc.stdout + proc.stderr).strip()
