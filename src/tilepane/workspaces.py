"""--workspaces: how the window manager arranges the workspaces.

EWMH lists workspaces (desktops) as a plain sequence. A pager may publish
their arrangement as a grid in `_NET_DESKTOP_LAYOUT` (orientation, columns,
rows, starting corner); without it they form one row. This module turns that
into rows of desktop indexes, top row first, for display. tilepane's
`--workspace N` and the layout key `workspace` use the sequence, 1 = first.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

CORNERS = ("top left", "top right", "bottom right", "bottom left")


@dataclass
class Desktops:
    count: int
    current: Optional[int]                   # 0-based index in the sequence
    names: list[str] = field(default_factory=list)
    layout: Optional[list[int]] = None       # raw _NET_DESKTOP_LAYOUT
    geometry: Optional[list[int]] = None     # _NET_DESKTOP_GEOMETRY (Compiz viewports)
    screen: Optional[tuple[int, int]] = None


def grid(count: int, layout: Optional[list[int]]) -> tuple[list[list[Optional[int]]], str]:
    """Rows (top first) of desktop indexes (None: empty cell), and a description."""
    if count <= 0:
        return [], "no workspaces"
    if not layout or len(layout) < 3:
        return [list(range(count))], "one row (the window manager does not publish a grid)"
    orientation, cols, rows = layout[0], layout[1], layout[2]
    corner = layout[3] if len(layout) > 3 else 0
    if cols <= 0 and rows <= 0:
        return [list(range(count))], "one row"
    if cols <= 0:
        cols = math.ceil(count / rows)
    if rows <= 0:
        rows = math.ceil(count / cols)
    cells: list[list[Optional[int]]] = [[None] * cols for _ in range(rows)]
    for i in range(min(count, rows * cols)):
        if orientation == 1:            # vertical: fill columns first
            r, c = i % rows, i // rows
        else:
            r, c = i // cols, i % cols
        if corner in (1, 2):
            c = cols - 1 - c
        if corner in (2, 3):
            r = rows - 1 - r
        cells[r][c] = i
    how = (f"{cols} x {rows} grid, numbered {'down the columns' if orientation == 1 else 'along the rows'} "
           f"from the {CORNERS[corner] if 0 <= corner < 4 else 'top left'} corner")
    return cells, how


def proposed_numbers(cells: list[list[Optional[int]]]) -> dict[int, int]:
    """The numbering under discussion: 0 bottom left, along each row, rows upward."""
    out: dict[int, int] = {}
    n = 0
    for row in reversed(cells):
        for idx in row:
            if idx is not None:
                out[idx] = n
                n += 1
    return out


def render(d: Desktops, verbose: bool = False) -> str:
    cells, how = grid(d.count, d.layout)
    lines = []
    cur = f" (current: {d.current + 1})" if d.current is not None else ""
    lines.append(f"{d.count} workspace(s){cur}: {how}")
    if d.count == 1 and d.geometry and d.screen and (d.geometry[0] > d.screen[0] or d.geometry[1] > d.screen[1]):
        lines.append("  note: one large desktop with viewports (Compiz style); tilepane does not tell viewports apart yet")
    width = max(len(str(d.count)), 1) + 2

    def draw(label) -> None:
        for row in cells:
            out = []
            for idx in row:
                if idx is None:
                    out.append(" " * width)
                    continue
                text = str(label(idx))
                out.append((f"[{text}]" if idx == d.current else f" {text} ").rjust(width))
            lines.append("  " + " ".join(out).rstrip())

    lines.append("")
    lines.append("As --workspace N uses them now (1 = first):")
    draw(lambda i: i + 1)
    names = [n for n in d.names[:d.count]]
    defaults = lambda i: {f"workspace {i + 1}", f"desktop {i + 1}", str(i + 1), ""}
    if any(n.strip().lower() not in defaults(i) for i, n in enumerate(names)):
        lines.append("")
        lines.append("Names:")
        for i, n in enumerate(names):
            lines.append(f"  {i + 1}: {n}")
    lines.append("")
    lines.append("Proposed numbering (0 bottom left, along the rows, rows upward):")
    nums = proposed_numbers(cells)
    draw(lambda i: nums[i])
    if verbose:
        lines.append("")
        lines.append(f"_NET_DESKTOP_LAYOUT: {d.layout if d.layout else 'not set'}")
        lines.append(f"_NET_DESKTOP_GEOMETRY: {d.geometry if d.geometry else 'not set'}")
    return "\n".join(lines)
