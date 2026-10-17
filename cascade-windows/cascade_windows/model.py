"""Backend independent data types.

All coordinates are in pixels and are relative to the top-left corner of one workspace "cell",
that is, the area of one screen. Backends translate to and from the coordinates used by the
window system (for example viewport offsets on Compiz).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from deskmap.rect import Rect  # shared with the other tools; re-exported for the modules of this package

# Window kinds. Only "normal" windows are cascaded; dialogs are left where they are.
KIND_NORMAL = "normal"
KIND_DIALOG = "dialog"
KIND_OTHER = "other"


@dataclass(frozen=True)
class Monitor:
    index: int
    name: str
    rect: Rect
    workarea: Rect  # monitor rectangle minus panels, docks and launchers


@dataclass(frozen=True)
class WindowInfo:
    id: int
    title: str
    wm_class: str
    workspace: str  # opaque workspace key, see Backend.workspaces()
    rect: Rect  # visible window rectangle including decorations
    kind: str = KIND_NORMAL
    minimized: bool = False
    fullscreen: bool = False
    sticky: bool = False
    maximized: bool = False
    resizable: bool = True
    stack_index: int = 0  # position in the stacking order, 0 = bottom
    open_index: int = 0  # position in the opening order, 0 = oldest

    def describe(self) -> str:
        flags = [
            name
            for name, value in (
                ("minimized", self.minimized),
                ("fullscreen", self.fullscreen),
                ("sticky", self.sticky),
                ("maximized", self.maximized),
                ("fixed-size", not self.resizable),
            )
            if value
        ]
        return "0x%x %-6s ws=%s %s %r [%s]%s" % (
            self.id,
            self.kind,
            self.workspace,
            self.rect,
            self.title[:40],
            self.wm_class,
            (" (" + ", ".join(flags) + ")") if flags else "",
        )
