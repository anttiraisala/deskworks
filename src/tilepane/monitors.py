"""Monitor detection and numbering.

Monitors are numbered by position, left to right and then top to bottom
(primarily by x, secondarily by y). Number 0 is the leftmost monitor.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class Monitor:
    number: int
    name: str
    x: int
    y: int
    width: int
    height: int
    primary: bool = False


# " 0: +*eDP-1 2048/344x1152/215+4480+1200  eDP-1"
_XRANDR_LINE = re.compile(
    r"^\s*\d+:\s+[+*]*(?P<name>[^\s+*]\S*)\s+"
    r"(?P<w>\d+)/\d+x(?P<h>\d+)/\d+(?P<x>[+-]\d+)(?P<y>[+-]\d+)"
)


def number_monitors(raw: list[Monitor]) -> list[Monitor]:
    """Sort by (x, y) and assign numbers 0..n-1."""
    ordered = sorted(raw, key=lambda m: (m.x, m.y, m.name))
    return [
        Monitor(i, m.name, m.x, m.y, m.width, m.height, m.primary)
        for i, m in enumerate(ordered)
    ]


def parse_xrandr_listmonitors(text: str) -> list[Monitor]:
    monitors = []
    for line in text.splitlines():
        m = _XRANDR_LINE.match(line)
        if not m:
            continue
        flags = line.split(":", 1)[1].split()[0]
        monitors.append(
            Monitor(
                0,
                m["name"],
                int(m["x"]),
                int(m["y"]),
                int(m["w"]),
                int(m["h"]),
                primary="*" in flags,
            )
        )
    return number_monitors(monitors)


def parse_sway_outputs(text: str) -> list[Monitor]:
    monitors = []
    for out in json.loads(text):
        if not out.get("active", True):
            continue
        r = out["rect"]
        monitors.append(
            Monitor(0, out["name"], r["x"], r["y"], r["width"], r["height"],
                    bool(out.get("primary", False)))
        )
    return number_monitors(monitors)


def parse_hyprland_monitors(text: str) -> list[Monitor]:
    monitors = []
    for out in json.loads(text):
        scale = out.get("scale") or 1.0
        monitors.append(
            Monitor(
                0,
                out["name"],
                int(out["x"]),
                int(out["y"]),
                round(out["width"] / scale),
                round(out["height"] / scale),
                bool(out.get("focused", False)),
            )
        )
    return number_monitors(monitors)


def _run(cmd: list[str]) -> str:
    return subprocess.run(
        cmd, capture_output=True, text=True, check=True, timeout=5
    ).stdout


def _source(
    binary: str, cmd: list[str], parse: Callable[[str], list[Monitor]]
) -> Optional[Callable[[], list[Monitor]]]:
    if not shutil.which(binary):
        return None
    return lambda: parse(_run(cmd))


def detect() -> tuple[list[Monitor], str, list[str]]:
    """Return (monitors, source name, error messages).

    Compositor-native sources come first on Wayland. xrandr works on X11 and,
    through XWayland, on most Wayland compositors.
    """
    candidates: list[tuple[str, Optional[Callable[[], list[Monitor]]]]] = []
    if os.environ.get("WAYLAND_DISPLAY"):
        candidates.append(
            ("swaymsg", _source("swaymsg", ["swaymsg", "-t", "get_outputs", "-r"],
                                parse_sway_outputs))
        )
        candidates.append(
            ("hyprctl", _source("hyprctl", ["hyprctl", "monitors", "-j"],
                                parse_hyprland_monitors))
        )
    candidates.append(
        ("xrandr", _source("xrandr", ["xrandr", "--listmonitors"],
                           parse_xrandr_listmonitors))
    )

    errors: list[str] = []
    for name, fn in candidates:
        if fn is None:
            continue
        try:
            monitors = fn()
        except (subprocess.SubprocessError, OSError, ValueError, KeyError) as exc:
            errors.append(f"{name}: {exc}")
            continue
        if monitors:
            return monitors, name, errors
        errors.append(f"{name}: no monitors reported")
    return [], "", errors


def format_table(monitors: list[Monitor]) -> str:
    lines = [f"{'#':<3} {'name':<14} {'size':<11} {'position':<10} flags"]
    for m in monitors:
        lines.append(
            f"{m.number:<3} {m.name:<14} {f'{m.width}x{m.height}':<11} "
            f"{f'+{m.x}+{m.y}':<10} {'primary' if m.primary else ''}".rstrip()
        )
    return "\n".join(lines)
