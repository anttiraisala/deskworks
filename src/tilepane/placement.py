"""Window placement arithmetic: pure functions, no X connection needed.

A window on X11 has a client area, a frame the window manager draws around it
(`_NET_FRAME_EXTENTS`), and for GTK client-side decorations an invisible shadow
inside the client area (`_GTK_FRAME_EXTENTS`). The layout rectangle is the
*visible* window, so the client size is derived from it. Terminals advertise
their character cell through size hints (base size plus resize increments), so
`snap: "cell"` needs no measuring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .geometry import Rect


class PlacementError(ValueError):
    """The target rectangle cannot hold a window."""


@dataclass(frozen=True)
class Extents:
    left: int = 0
    right: int = 0
    top: int = 0
    bottom: int = 0


@dataclass(frozen=True)
class SizeHints:
    base_w: int = 0
    base_h: int = 0
    inc_w: int = 1
    inc_h: int = 1
    min_w: int = 0
    min_h: int = 0


@dataclass(frozen=True)
class Plan:
    x: int                 # where the frame (or shadow) starts: the move target
    y: int
    width: int             # client size to request
    height: int
    cols: Optional[int]    # character cells, when snapped to cells
    rows: Optional[int]
    clamped: bool          # the pane is smaller than the terminal's minimum size
    visible: Rect          # the visible window this plan should produce
    notes: list[str] = field(default_factory=list)


def _snap(size: int, base: int, inc: int, minimum: int) -> tuple[int, int, bool]:
    """Round `size` down to base + n*inc. Returns (n, size, clamped)."""
    inc = max(inc, 1)
    floor = max(minimum, base + inc)
    if size < floor:
        return (floor - base) // inc, base + ((floor - base) // inc) * inc, True
    n = (size - base) // inc
    return n, base + n * inc, False


def plan(target: Rect, frame: Extents, gtk: Extents, hints: Optional[SizeHints],
         snap: str) -> Plan:
    """Work out the client rectangle that makes the visible window match `target`.

    With `snap == "cell"` and size hints, the size is rounded down to whole
    character cells; the position stays at the target's top-left corner.
    """
    cw = target.width - frame.left - frame.right + gtk.left + gtk.right
    ch = target.height - frame.top - frame.bottom + gtk.top + gtk.bottom
    if cw <= 0 or ch <= 0:
        raise PlacementError(
            f"target {target.width}x{target.height} is smaller than the window frame")
    cols = rows = None
    clamped = False
    notes: list[str] = []
    if hints is not None and snap == "cell":
        cols, cw, c1 = _snap(cw, hints.base_w, hints.inc_w, hints.min_w)
        rows, ch, c2 = _snap(ch, hints.base_h, hints.inc_h, hints.min_h)
        clamped = c1 or c2
        if clamped:
            notes.append("pane is smaller than the terminal's minimum size; using the minimum")
    elif hints is not None:
        cw, ch = max(cw, hints.min_w), max(ch, hints.min_h)
    elif snap == "cell":
        notes.append("the terminal gave no size hints; the size is not snapped to cells")
    x, y = target.x - gtk.left, target.y - gtk.top
    visible = Rect(target.x, target.y,
                   cw + frame.left + frame.right - gtk.left - gtk.right,
                   ch + frame.top + frame.bottom - gtk.top - gtk.bottom)
    return Plan(x, y, cw, ch, cols, rows, clamped, visible, notes)


def visible_rect(client_x: int, client_y: int, client_w: int, client_h: int,
                 frame: Extents, gtk: Extents) -> Rect:
    """The visible window, from the client area's position and size on the root window."""
    return Rect(client_x - frame.left + gtk.left, client_y - frame.top + gtk.top,
                client_w + frame.left + frame.right - gtk.left - gtk.right,
                client_h + frame.top + frame.bottom - gtk.top - gtk.bottom)


def hints_from_wm(flags: int, base: tuple[int, int], inc: tuple[int, int],
                  minimum: tuple[int, int]) -> Optional[SizeHints]:
    """Build SizeHints from WM_NORMAL_HINTS fields (ICCCM flag bits).

    Without a base size the minimum size is the base for the increments.
    Returns None when the window sets no resize increments.
    """
    p_min, p_inc, p_base = 16, 64, 256
    if not flags & p_inc or inc[0] <= 0 or inc[1] <= 0:
        return None
    if flags & p_base:
        b = base
    elif flags & p_min:
        b = minimum
    else:
        b = (0, 0)
    m = minimum if flags & p_min else (0, 0)
    return SizeHints(b[0], b[1], inc[0], inc[1], m[0], m[1])
