"""Environment report (`tilepane --doctor`) and backend recommendation."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

from . import monitors as mon

TERMINALS = [
    "kitty", "alacritty", "gnome-terminal", "xterm", "konsole",
    "xfce4-terminal", "tilix", "wezterm", "foot", "x-terminal-emulator",
]
SHELLS = ["bash", "zsh", "fish", "dash", "ksh", "tcsh"]
X11_TOOLS = ["xrandr", "xprop", "xwininfo", "xdotool", "wmctrl"]
WAYLAND_TOOLS = ["swaymsg", "hyprctl", "wlr-randr", "gdbus", "busctl"]
DEMO_TOOLS = [
    "htop", "top", "watch", "sensors", "nvidia-smi", "figlet", "cowsay",
    "cmatrix", "sl", "fortune", "tmux", "zellij",
]
# Tiling window managers place windows themselves; floating rules are needed.
TILING_WMS = {
    "i3", "bspwm", "awesome", "dwm", "xmonad", "qtile", "herbstluftwm",
    "spectrwm", "stumpwm", "leftwm", "sway", "hyprland",
}


@dataclass
class Recommendation:
    backend: str
    ready: bool
    notes: list[str] = field(default_factory=list)


def session_type() -> str:
    value = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if value in ("x11", "wayland"):
        return value
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    return "unknown"


def desktops() -> list[str]:
    raw = os.environ.get("XDG_CURRENT_DESKTOP", "")
    return [d.lower() for d in raw.split(":") if d]


def _xprop(args: list[str]) -> str:
    try:
        return subprocess.run(
            ["xprop", *args], capture_output=True, text=True, timeout=5
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def x11_window_manager() -> str:
    """Name of the running EWMH window manager, or '' if unknown."""
    if not shutil.which("xprop"):
        return ""
    match = re.search(r"window id # (0x[0-9a-f]+)",
                      _xprop(["-root", "_NET_SUPPORTING_WM_CHECK"]))
    if not match:
        return ""
    name = re.search(r'"(.*)"', _xprop(["-id", match[1], "_NET_WM_NAME"]))
    return name[1] if name else ""


def xlib_version() -> str:
    if importlib.util.find_spec("Xlib") is None:
        return ""
    try:
        return importlib.metadata.version("python-xlib")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def recommend(session: str, desk: list[str], wm: str, tools: set[str],
              xlib: str) -> Recommendation:
    """Pick a placement backend for the detected environment."""
    if session == "x11":
        if xlib:
            rec = Recommendation("x11-xlib", True)
        elif "xdotool" in tools or "wmctrl" in tools:
            rec = Recommendation("x11-cli (xdotool/wmctrl)", True)
        else:
            return Recommendation(
                "x11-xlib", False,
                ["Install python-xlib (pip install python-xlib) or xdotool."])
        if wm.lower() in TILING_WMS:
            rec.notes.append(
                f"{wm} is a tiling window manager: add a floating rule for "
                "windows with class 'tilepane' or placement will be overridden.")
        return rec

    if session == "wayland":
        if "sway" in desk or wm.lower() == "sway":
            return Recommendation(
                "wayland-sway-ipc", "swaymsg" in tools,
                ["Planned: swaymsg for placement and floating rules."])
        if "hyprland" in desk:
            return Recommendation(
                "wayland-hyprland-ipc", "hyprctl" in tools,
                ["Planned: hyprctl dispatch for placement."])
        if "kde" in desk:
            return Recommendation(
                "wayland-kwin-script", False,
                ["Planned: KWin script loaded over D-Bus.",
                 "Alternative: log in to a Plasma X11 session."])
        if "gnome" in desk or "ubuntu" in desk:
            return Recommendation(
                "wayland-gnome-extension", False,
                ["Planned: small GNOME Shell extension driven over D-Bus.",
                 "Alternative: log in to an X11 session."])
        return Recommendation(
            "none", False,
            ["Wayland compositor not recognised: no supported placement "
             "backend. Log in to an X11 session."])

    return Recommendation("none", False,
                          ["No X11 or Wayland session detected."])


def collect() -> dict:
    session = session_type()
    desk = desktops()
    wm = x11_window_manager() if session == "x11" or os.environ.get("DISPLAY") else ""
    found = {n: bool(shutil.which(n)) for n in
             X11_TOOLS + WAYLAND_TOOLS + TERMINALS + SHELLS + DEMO_TOOLS}
    xlib = xlib_version()
    monitors, source, errors = mon.detect()
    return {
        "os": platform.platform(),
        "python": sys.version.split()[0],
        "session": session,
        "desktop": desk,
        "window_manager": wm,
        "display": os.environ.get("DISPLAY", ""),
        "wayland_display": os.environ.get("WAYLAND_DISPLAY", ""),
        "xlib": xlib,
        "tools": found,
        "monitors": monitors,
        "monitor_source": source,
        "monitor_errors": errors,
        "recommendation": recommend(
            session, desk, wm, {n for n, ok in found.items() if ok}, xlib),
    }


def _names(found: dict, names: list[str]) -> tuple[str, str]:
    have = ", ".join(n for n in names if found[n]) or "-"
    missing = ", ".join(n for n in names if not found[n]) or "-"
    return have, missing


def render(info: dict) -> str:
    out = []
    add = out.append
    add("tilepane doctor")
    add("")
    add(f"OS               {info['os']}")
    add(f"Python           {info['python']}")
    add(f"Session          {info['session']}"
        f"  (DISPLAY={info['display'] or '-'}, "
        f"WAYLAND_DISPLAY={info['wayland_display'] or '-'})")
    add(f"Desktop          {':'.join(info['desktop']) or '-'}")
    add(f"Window manager   {info['window_manager'] or '-'}")
    add(f"python-xlib      {info['xlib'] or 'not installed'}")
    add("")
    add(f"Monitors         via {info['monitor_source'] or 'none'}")
    if info["monitors"]:
        add(mon.format_table(info["monitors"]))
    for err in info["monitor_errors"]:
        add(f"  warning: {err}")
    add("")
    for title, names in (("X11 tools", X11_TOOLS), ("Wayland tools", WAYLAND_TOOLS),
                         ("Terminals", TERMINALS), ("Shells", SHELLS),
                         ("Demo commands", DEMO_TOOLS)):
        have, missing = _names(info["tools"], names)
        add(f"{title:<16} found: {have}")
        add(f"{'':<16} missing: {missing}")
    add("")
    rec: Recommendation = info["recommendation"]
    add(f"Backend          {rec.backend} ({'ready' if rec.ready else 'not ready'})")
    for note in rec.notes:
        add(f"  - {note}")
    return "\n".join(out)
