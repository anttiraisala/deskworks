"""Terminal adapters: how to start each terminal with a title, a class and a size.

An adapter turns a `LaunchRequest` into a command line. Window placement itself
is done by the backend after the window appears; the geometry given here only
makes the window start close to where it will end up.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Callable, Optional, Union

WINDOW_CLASS = "tilepane"


class TerminalError(ValueError):
    """No usable terminal for a request."""


@dataclass(frozen=True)
class Geometry:
    cols: int
    rows: int
    x: int
    y: int


@dataclass(frozen=True)
class LaunchRequest:
    title: str
    argv: list[str]                       # the program to run inside the terminal
    geometry: Optional[Geometry] = None
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0


class Terminal:
    name = ""
    binary = ""
    window_class: Optional[str] = WINDOW_CLASS
    unsupported: tuple[str, ...] = ()     # leaf keys this terminal cannot honor

    def available(self, which: Callable[[str], Optional[str]] = shutil.which) -> bool:
        return which(self.binary) is not None

    def command(self, req: LaunchRequest) -> list[str]:
        raise NotImplementedError

    def matches(self, wm_class: tuple[str, str]) -> bool:
        """Is a new window with this (instance, class) one of ours?"""
        return self.window_class is None or wm_class[1] == self.window_class


class GnomeTerminal(Terminal):
    name = "gnome-terminal"
    binary = "gnome-terminal"
    # --class starts a dedicated server whose windows get WM_CLASS class "tilepane".
    unsupported = ("profile", "font_size")

    def command(self, req: LaunchRequest) -> list[str]:
        cmd = [self.binary, f"--class={WINDOW_CLASS}", f"--title={req.title}"]
        if req.geometry:
            g = req.geometry
            cmd.append(f"--geometry={g.cols}x{g.rows}+{g.x}+{g.y}")
        return cmd + ["--"] + req.argv


class Xterm(Terminal):
    name = "xterm"
    binary = "xterm"
    unsupported = ("profile", "font_size")

    def command(self, req: LaunchRequest) -> list[str]:
        cmd = [self.binary, "-class", WINDOW_CLASS, "-name", WINDOW_CLASS, "-T", req.title]
        if req.geometry:
            g = req.geometry
            cmd += ["-geometry", f"{g.cols}x{g.rows}+{g.x}+{g.y}"]
        return cmd + ["-e"] + req.argv


class CustomTerminal(Terminal):
    """A terminal defined by a command template in the configuration.

    The element "{command}" expands to the program and its arguments. In every
    other element {title}, {x}, {y}, {width}, {height}, {cols}, {rows} and
    {class} are replaced. The window is recognised as the first new one.
    """

    window_class = None
    unsupported = ("profile", "font_size")

    def __init__(self, cmd: list[str]):
        self.cmd = cmd
        self.binary = cmd[0]
        self.name = cmd[0]

    def command(self, req: LaunchRequest) -> list[str]:
        g = req.geometry
        values = {
            "title": req.title, "x": req.x, "y": req.y, "width": req.width,
            "height": req.height, "cols": g.cols if g else "", "rows": g.rows if g else "",
            "class": WINDOW_CLASS,
        }
        out: list[str] = []
        for part in self.cmd:
            if part == "{command}":
                out += req.argv
                continue
            for key, value in values.items():
                part = part.replace("{" + key + "}", str(value))
            out.append(part)
        return out


# Terminals with an adapter, in the order "auto" tries them. kitty and alacritty
# (SPEC.md section 4) come first once they have adapters.
IMPLEMENTED: dict[str, Terminal] = {t.name: t for t in (GnomeTerminal(), Xterm())}
AUTO_ORDER = ["kitty", "alacritty", "gnome-terminal", "xterm"]


def resolve(setting: Union[str, dict], *,
            which: Callable[[str], Optional[str]] = shutil.which) -> Terminal:
    """Pick the terminal for a leaf's `terminal` setting."""
    if isinstance(setting, dict):
        return CustomTerminal(setting["cmd"])
    if setting == "auto":
        for name in AUTO_ORDER:
            term = IMPLEMENTED.get(name)
            if term is not None and term.available(which):
                return term
        raise TerminalError("no supported terminal found (looked for "
                            + ", ".join(n for n in AUTO_ORDER if n in IMPLEMENTED) + ")")
    term = IMPLEMENTED.get(setting)
    if term is None:
        known = ", ".join(sorted(IMPLEMENTED))
        raise TerminalError(f"terminal '{setting}' is not supported yet (supported: {known}); "
                            "or define it with {\"cmd\": [...]}")
    if not term.available(which):
        raise TerminalError(f"terminal '{setting}' is not installed")
    return term
