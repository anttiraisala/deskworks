"""Analysing a screen: the layout that the open windows of a monitor make.

This is the opposite of opening a layout. `derive` takes the rectangles of the windows that are on a monitor
(inside its work area) and finds a tree of splits that gives every window a rectangle of its own, so that no
two panes overlap. Windows that do not touch each other are separated by the splits as they are; windows that
overlap are separated by cutting between their centres, and each window then keeps only the part on its side
of the cut. So where windows lie on top of each other the layout cannot match the screen exactly; the largest
difference is reported.

Rules:

* Every cut is a straight line across the whole region it cuts (guillotine cuts), like the splits of a layout.
* The window gap becomes `margin` (the median gap between neighbouring windows), the distance of the outer
  windows from the edge of the work area becomes `outer_margin` when it is not the margin's half.
* A region that no window reaches becomes an empty pane. Gaps up to GAP_TOL pixels are noise: terminals are
  placed at whole character cells, so neighbours are not always exactly one margin apart.
* A cut is chosen by what it crosses: cuts that cross no window come first, then the cut that takes the least
  area from the windows it crosses. Windows are given to the side where their centre is.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Callable, Optional

from deskmap.rect import Rect

from . import geometry

GAP_TOL = 12          # pixels; smaller gaps are placement noise, larger ones become empty panes
NOISE = 6             # pixels; windows that overlap by no more than this are neighbours
MAX_MARGIN = 64       # a larger distance between windows is not a margin
MIN_SIDE = 8          # a window overlaps another by at least this much to count as neighbour


@dataclass
class Item:
    """A window to give a place in the layout."""
    rect: Rect              # where it is now
    pane: dict              # the settings of its pane (run, title, ...)
    stack: int = 0          # 0 is the bottom of the stacking order


@dataclass
class Analysis:
    layout: dict
    windows: int            # panes with a window
    empty: int              # empty panes made for the screen no window covers
    margin: int
    outer_margin: Optional[int]
    deviation: int          # largest difference, in pixels, between a window and its pane
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- margins

def _gap(a: Rect, b: Rect, vertical: bool) -> Optional[int]:
    """The distance between two windows that stand side by side (vertical: one beside the other)."""
    if vertical:
        if min(a.bottom, b.bottom) - max(a.y, b.y) < MIN_SIDE:
            return None
        return max(a.x, b.x) - min(a.right, b.right)
    if min(a.right, b.right) - max(a.x, b.x) < MIN_SIDE:
        return None
    return max(a.y, b.y) - min(a.bottom, b.bottom)


def estimate_margins(area: Rect, rects: list[Rect]) -> tuple[int, Optional[int]]:
    """(margin, outer_margin or None) that explain the gaps between the windows and to the edge of the area."""
    gaps = []
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            for vertical in (True, False):
                g = _gap(a, b, vertical)
                if g is not None and 0 <= g <= MAX_MARGIN:
                    gaps.append(g)
    margin = int(round(statistics.median(gaps))) if gaps else 0
    lo, hi = margin // 2, margin - margin // 2
    sides = []     # (distance of the nearest window to this edge, the inset a layout without outer_margin gives)
    for dist, expected in (
        (min((r.x - area.x for r in rects), default=None), lo),
        (min((r.y - area.y for r in rects), default=None), lo),
        (min((area.right - r.right for r in rects), default=None), hi),
        (min((area.bottom - r.bottom for r in rects), default=None), hi),
    ):
        if dist is not None and 0 <= dist <= MAX_MARGIN:
            sides.append((dist, expected))
    if not sides or all(abs(d - e) <= 1 for d, e in sides):
        return margin, None
    return margin, int(round(statistics.median(d for d, _ in sides)))


# --------------------------------------------------------------------------- cutting

@dataclass
class _Cell:
    rect: Rect
    pane: dict
    stack: int


@dataclass
class _Node:
    """Leaf (pane set, or None for an empty pane) or a cut."""
    pane: Optional[dict] = None
    vertical: bool = False       # a cut by a vertical line: panes side by side
    offset: int = 0              # where the cut is, from the start of the region
    extent: int = 0              # the size of the region along the cut
    a: Optional["_Node"] = None
    b: Optional["_Node"] = None
    leaf: bool = True


def _clip(r: Rect, region: Rect) -> Optional[Rect]:
    x0, y0 = max(r.x, region.x), max(r.y, region.y)
    x1, y1 = min(r.right, region.right), min(r.bottom, region.bottom)
    return Rect(x0, y0, x1 - x0, y1 - y0) if x1 > x0 and y1 > y0 else None


def _axis(vertical: bool):
    if vertical:
        return (lambda r: r.x), (lambda r: r.right), (lambda r: r.height)
    return (lambda r: r.y), (lambda r: r.bottom), (lambda r: r.width)


def _candidates(region: Rect, cells: list[_Cell], vertical: bool) -> list[tuple]:
    """(key, position, vertical, left cells, right cells) of every usable cut along one axis."""
    lo, hi, across = _axis(vertical)
    a0, a1 = (region.x, region.right) if vertical else (region.y, region.bottom)
    mid = (a0 + a1) / 2
    cuts: list[int] = []
    first, last = min(lo(c.rect) for c in cells), max(hi(c.rect) for c in cells)
    if first - a0 > GAP_TOL:
        cuts.append(first)
    if a1 - last > GAP_TOL:
        cuts.append(last)
    end = None
    for c in sorted(cells, key=lambda c: lo(c.rect)):
        if end is not None and lo(c.rect) >= end - NOISE:
            gap = lo(c.rect) - end
            cuts.append(end if gap > GAP_TOL else (end + lo(c.rect)) // 2)
        end = hi(c.rect) if end is None else max(end, hi(c.rect))
    centres = sorted({(lo(c.rect) + hi(c.rect)) / 2 for c in cells})
    free = set(cuts)          # cuts along the free space between windows come before cuts between centres
    for boundary in ((p + q) / 2 for p, q in zip(centres, centres[1:])):
        # Between the windows left of the boundary and those right of it: in the middle of the gap, or
        # of the overlap, so that the windows lose as little as possible.
        left_hi = max(hi(c.rect) for c in cells if (lo(c.rect) + hi(c.rect)) / 2 < boundary)
        right_lo = min(lo(c.rect) for c in cells if (lo(c.rect) + hi(c.rect)) / 2 >= boundary)
        cuts.append((left_hi + right_lo) // 2)

    out = []
    for pos in sorted(set(cuts)):
        if not a0 < pos < a1:
            continue
        left = [c for c in cells if (lo(c.rect) + hi(c.rect)) / 2 < pos]
        right = [c for c in cells if (lo(c.rect) + hi(c.rect)) / 2 >= pos]
        cost = sum(min(pos - lo(c.rect), hi(c.rect) - pos) * across(c.rect)
                   for c in cells if lo(c.rect) < pos < hi(c.rect) and min(pos - lo(c.rect), hi(c.rect) - pos) > NOISE)
        two_sided = bool(left) and bool(right)
        if not two_sided and cost:
            continue
        out.append(((cost, 0 if pos in free else 1, 0 if two_sided else 1, abs(pos - mid), 0 if vertical else 1),
                    pos, vertical, left, right))
    return out


def _strips(region: Rect, cells: list[_Cell], notes: list[str]) -> _Node:
    """Windows on top of each other with the same centre: give them equal strips, the topmost first."""
    notes.append(f"{len(cells)} windows on top of each other were put side by side")
    cells = sorted(cells, key=lambda c: -c.stack)
    vertical = region.width >= region.height

    def chain(rest: list[_Cell], remaining: int) -> _Node:
        if len(rest) == 1:
            return _Node(pane=rest[0].pane)
        size = round(remaining / len(rest))
        return _Node(leaf=False, vertical=vertical, offset=size, extent=remaining,
                     a=_Node(pane=rest[0].pane), b=chain(rest[1:], remaining - size))

    return chain(cells, region.width if vertical else region.height)


def _build(region: Rect, cells: list[_Cell], notes: list[str]) -> _Node:
    cells = [_Cell(r, c.pane, c.stack) for c in cells if (r := _clip(c.rect, region)) is not None]
    if not cells:
        return _Node(pane=None)
    options = _candidates(region, cells, True) + _candidates(region, cells, False)
    if not options:
        return _Node(pane=cells[0].pane) if len(cells) == 1 else _strips(region, cells, notes)
    _key, pos, vertical, left, right = min(options, key=lambda o: o[0])
    if vertical:
        ra = Rect(region.x, region.y, pos - region.x, region.height)
        rb = Rect(pos, region.y, region.right - pos, region.height)
        offset, extent = pos - region.x, region.width
    else:
        ra = Rect(region.x, region.y, region.width, pos - region.y)
        rb = Rect(region.x, pos, region.width, region.bottom - pos)
        offset, extent = pos - region.y, region.height
    return _Node(leaf=False, vertical=vertical, offset=offset, extent=extent,
                 a=_build(ra, left, notes), b=_build(rb, right, notes))


def _render(node: _Node, percent: bool) -> dict:
    if node.leaf:
        return dict(node.pane) if node.pane is not None else {}
    if percent:
        text = f"{node.offset / node.extent * 100:.3f}".rstrip("0").rstrip(".") + "%"
    else:
        text = f"{node.offset}px"
    return {"dir": "columns" if node.vertical else "rows", "at": text,
            "a": _render(node.a, percent), "b": _render(node.b, percent)}


def _count(node: _Node) -> tuple[int, int]:
    if node.leaf:
        return (1, 0) if node.pane is not None else (0, 1)
    wa, ea = _count(node.a)
    wb, eb = _count(node.b)
    return wa + wb, ea + eb


# --------------------------------------------------------------------------- the whole analysis

def derive(area: Rect, items: list[Item], *, name: str = "analyzed") -> Analysis:
    """The layout of `items` (windows with their panes) in `area`, the work area of their monitor."""
    notes: list[str] = []
    rects = [it.rect for it in items]
    if _overlap(rects):
        # Windows on top of each other say nothing about margins.
        margin, outer = 0, None
    else:
        margin, outer = estimate_margins(area, rects)
    lo, hi = margin // 2, margin - margin // 2
    region = area if outer is None else Rect(area.x + outer, area.y + outer,
                                             area.width - 2 * outer, area.height - 2 * outer)
    cells = [_Cell(Rect(it.rect.x - lo, it.rect.y - lo, it.rect.width + lo + hi, it.rect.height + lo + hi),
                   it.pane, it.stack) for it in items]
    tree = _build(region, cells, notes)
    base: dict = {"name": name, "margin": margin}
    if outer is not None:
        base["outer_margin"] = outer
    best: Optional[tuple[int, dict]] = None
    for percent in (True, False):
        layout = {**base, "split": _render(tree, percent)}
        dev = _deviation(layout, area, items)
        if best is None or dev < best[0]:
            best = (dev, layout)
    deviation, layout = best
    windows, empty = _count(tree)
    if deviation > 1:
        notes.append(f"the panes differ from the windows by up to {deviation} px "
                     "(windows that overlap cannot all keep their rectangles)")
    return Analysis(layout, windows, empty, margin, outer, deviation, notes)


def _overlap(rects: list[Rect]) -> bool:
    """True when two windows cover a common area (more than the noise of a few pixels)."""
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            if min(a.right, b.right) - max(a.x, b.x) > 4 and min(a.bottom, b.bottom) - max(a.y, b.y) > 4:
                return True
    return False


def _deviation(layout: dict, area: Rect, items: list[Item]) -> int:
    """The largest difference between a window and the pane it got, in pixels."""
    try:
        leaves = geometry.compute(layout, area)
    except geometry.GeometryError:
        return 10 ** 6
    panes = [lf for lf in leaves if lf.leaf != {}]
    worst = 0
    for it in items:
        # The pane whose rectangle is nearest to the window is the one it was given.
        near = min((max(abs(lf.rect.x - it.rect.x), abs(lf.rect.y - it.rect.y),
                        abs(lf.rect.right - it.rect.right), abs(lf.rect.bottom - it.rect.bottom))
                    for lf in panes), default=10 ** 6)
        worst = max(worst, near)
    return worst


# --------------------------------------------------------------------------- windows to panes

TERMINALS = {"gnome-terminal", "gnome-terminal-server", "xterm", "uxterm", "konsole", "kitty", "alacritty",
             "xfce4-terminal", "tilix", "terminator", "wezterm", "wezterm-gui", "foot", "urxvt", "rxvt", "st",
             "st-256color", "lxterminal", "mate-terminal", "qterminal", "terminology", "x-terminal-emulator",
             "tilepane"}


def is_terminal(wm_class: tuple[str, str]) -> bool:
    return any(part.lower() in TERMINALS for part in wm_class)


def pane_for(wm_class: tuple[str, str], title: str, pid: Optional[int],
             terminal_pane: Callable[[Optional[int]], Optional[dict]], *, shared: bool = False) -> dict:
    """The pane a window becomes. A terminal gets the command that runs in it (when that can be found), any
    other window a shell with the name of the program as its title, so that its place stays in the layout."""
    if is_terminal(wm_class):
        found = None if shared else terminal_pane(pid)
        return found if found else {"empty": False}
    name = wm_class[1] or wm_class[0] or "window"
    title = " ".join(title.split())
    text = f"{name}: {title[:40]}" if title and title.lower() != name.lower() else name
    return {"empty": False, "title": text}
