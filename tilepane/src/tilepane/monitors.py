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


class MonitorError(ValueError):
    """A --monitor value does not match any connected monitor."""


def _describe(monitors: list[Monitor]) -> str:
    return ", ".join(f"{m.number} {m.name}" for m in monitors) or "none"


def resolve(spec: str, monitors: list[Monitor],
            aliases: Optional[dict] = None) -> list[Monitor]:
    """Resolve one --monitor value to monitors.

    A value is `all`, `primary`, a config alias, a number or a connector name,
    checked in that order. An alias maps to a number or a connector name.
    """
    spec = spec.strip()
    if not monitors:
        raise MonitorError("no monitors found")
    if spec == "all":
        return list(monitors)
    if spec == "primary":
        primary = [m for m in monitors if m.primary]
        if not primary:
            raise MonitorError("no primary monitor is set; use a number or a connector name")
        return primary[:1]
    target = str((aliases or {}).get(spec, spec)).strip()
    if target.isdigit():
        number = int(target)
        if number >= len(monitors):
            raise MonitorError(f"no monitor {number} (monitors: {_describe(monitors)})")
        return [monitors[number]]
    for m in monitors:
        if m.name.lower() == target.lower():
            return [m]
    via = f" (alias '{spec}')" if spec != target else ""
    raise MonitorError(f"unknown monitor '{target}'{via} (monitors: {_describe(monitors)})")


def resolve_many(value: str, monitors: list[Monitor],
                 aliases: Optional[dict] = None) -> list[Monitor]:
    """Resolve a comma-separated --monitor value; duplicates are dropped."""
    out: list[Monitor] = []
    for part in value.split(","):
        if not part.strip():
            raise MonitorError(f"empty entry in monitor list '{value}'")
        for m in resolve(part, monitors, aliases):
            if m not in out:
                out.append(m)
    return out


def wait_for_monitors(timeout: float = 0.0, interval: float = 0.5):
    """detect(), retried for up to `timeout` seconds while no monitor is found."""
    import time

    deadline = time.monotonic() + timeout
    while True:
        result = detect()
        if result[0] or time.monotonic() >= deadline:
            return result
        time.sleep(interval)
