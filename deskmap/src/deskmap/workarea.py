"""Per-monitor work area on X11: the monitor minus panels and docks.

`_NET_WORKAREA` is one rectangle for the whole desktop, which says nothing about
which monitor has a panel. Sources, best first:

1. `_GTK_WORKAREAS_D<desktop>` on the root window: one rectangle per monitor
   (set by Mutter, Compiz/Unity and others).
2. Struts (`_NET_WM_STRUT_PARTIAL`, `_NET_WM_STRUT`) of panel windows, applied
   to every monitor they touch.
3. `_NET_WORKAREA` clipped to the monitor.
4. The whole monitor.

The window manager keeps windows inside this area, so a layout that uses the
full monitor would be pushed in by the panels.
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from typing import Optional

from .rect import Rect
from .monitors import Monitor


@dataclass(frozen=True)
class Strut:
    left: int = 0
    right: int = 0
    top: int = 0
    bottom: int = 0
    left_range: tuple[int, int] = (0, 0)     # start, end along the edge (inclusive)
    right_range: tuple[int, int] = (0, 0)
    top_range: tuple[int, int] = (0, 0)
    bottom_range: tuple[int, int] = (0, 0)


def monitor_rect(m: Monitor) -> Rect:
    return Rect(m.x, m.y, m.width, m.height)


def intersect(a: Rect, b: Rect) -> Optional[Rect]:
    x1, y1 = max(a.x, b.x), max(a.y, b.y)
    x2, y2 = min(a.right, b.right), min(a.bottom, b.bottom)
    return Rect(x1, y1, x2 - x1, y2 - y1) if x2 > x1 and y2 > y1 else None


def from_gtk_workareas(values: list[int], monitor: Monitor) -> Optional[Rect]:
    """Pick the rectangle of `_GTK_WORKAREAS` that belongs to `monitor`."""
    mon = monitor_rect(monitor)
    best: Optional[Rect] = None
    best_area = 0
    for i in range(0, len(values) - len(values) % 4, 4):
        rect = Rect(*values[i:i + 4])
        hit = intersect(rect, mon)
        if hit and hit.width * hit.height > best_area:
            best, best_area = hit, hit.width * hit.height
    return best


def from_struts(monitor: Monitor, struts: list[Strut], screen: tuple[int, int]) -> Rect:
    """The monitor minus the area struts reserve on it."""
    sw, sh = screen
    mon = monitor_rect(monitor)
    left, top, right, bottom = mon.x, mon.y, mon.right, mon.bottom
    for s in struts:
        reserved = []
        if s.left:
            reserved.append(("left", Rect(0, s.left_range[0], s.left, s.left_range[1] - s.left_range[0] + 1)))
        if s.right:
            reserved.append(("right", Rect(sw - s.right, s.right_range[0], s.right,
                                           s.right_range[1] - s.right_range[0] + 1)))
        if s.top:
            reserved.append(("top", Rect(s.top_range[0], 0, s.top_range[1] - s.top_range[0] + 1, s.top)))
        if s.bottom:
            reserved.append(("bottom", Rect(s.bottom_range[0], sh - s.bottom,
                                            s.bottom_range[1] - s.bottom_range[0] + 1, s.bottom)))
        for side, rect in reserved:
            hit = intersect(rect, mon)
            if hit is None:
                continue
            if side == "left":
                left = max(left, hit.right)
            elif side == "top":
                top = max(top, hit.bottom)
            elif side == "right":
                right = min(right, hit.x)
            else:
                bottom = min(bottom, hit.y)
    if right <= left or bottom <= top:
        return mon
    return Rect(left, top, right - left, bottom - top)


def strut_from_property(values: list[int], screen: tuple[int, int]) -> Optional[Strut]:
    """Build a Strut from `_NET_WM_STRUT_PARTIAL` (12 values) or `_NET_WM_STRUT` (4)."""
    if len(values) < 4 or not any(values[:4]):
        return None
    sw, sh = screen
    if len(values) >= 12:
        v = values
        return Strut(v[0], v[1], v[2], v[3], (v[4], v[5]), (v[6], v[7]), (v[8], v[9]), (v[10], v[11]))
    return Strut(values[0], values[1], values[2], values[3],
                 (0, sh - 1), (0, sh - 1), (0, sw - 1), (0, sw - 1))


def available() -> bool:
    return bool(os.environ.get("DISPLAY")) and importlib.util.find_spec("Xlib") is not None


def detect(monitors: list[Monitor]) -> tuple[dict[int, Rect], str]:
    """Work area for every monitor (by number) and the source that was used.

    Falls back to the whole monitor when X cannot be queried; the source then
    says "none".
    """
    full = {m.number: monitor_rect(m) for m in monitors}
    if not available():
        return full, "none"
    try:
        from Xlib import X, display
        d = display.Display()
    except Exception:  # noqa: BLE001 - no X connection: use whole monitors
        return full, "none"
    try:
        root = d.screen().root

        def cardinals(win, name):
            prop = win.get_full_property(d.intern_atom(name), X.AnyPropertyType)
            return None if prop is None else [int(v) for v in prop.value]

        desktop = (cardinals(root, "_NET_CURRENT_DESKTOP") or [0])[0]
        gtk = cardinals(root, f"_GTK_WORKAREAS_D{desktop}")
        if gtk:
            areas = {m.number: from_gtk_workareas(gtk, m) for m in monitors}
            if all(areas.values()):
                return areas, "_GTK_WORKAREAS"  # type: ignore[return-value]

        geo = root.get_geometry()
        screen = (geo.width, geo.height)
        struts = []
        seen: set[int] = set()

        def scan(win, depth):
            try:
                kids = win.query_tree().children
            except Exception:  # noqa: BLE001
                return
            for kid in kids:
                if kid.id in seen:
                    continue
                seen.add(kid.id)
                for name in ("_NET_WM_STRUT_PARTIAL", "_NET_WM_STRUT"):
                    try:
                        s = strut_from_property(cardinals(kid, name) or [], screen)
                    except Exception:  # noqa: BLE001
                        s = None
                    if s:
                        struts.append(s)
                        break
                if depth < 1:
                    scan(kid, depth + 1)

        scan(root, 0)
        if struts:
            return {m.number: from_struts(m, struts, screen) for m in monitors}, "struts"

        wa = cardinals(root, "_NET_WORKAREA")
        if wa and len(wa) >= 4:
            clipped = {m.number: intersect(Rect(*wa[:4]), monitor_rect(m)) for m in monitors}
            if all(clipped.values()):
                return clipped, "_NET_WORKAREA"  # type: ignore[return-value]
        return full, "none"
    finally:
        d.close()
