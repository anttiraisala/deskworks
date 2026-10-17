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
    viewport: Optional[tuple[int, int]] = None   # _NET_DESKTOP_VIEWPORT of the current desktop


def viewport_grid(d: Desktops) -> Optional[tuple[int, int, Optional[tuple[int, int]]]]:
    """(columns, rows, current cell as (column, row from the top)) when the
    desktop is a large area shown one screen at a time (Compiz), else None."""
    if not d.geometry or not d.screen or len(d.geometry) < 2:
        return None
    sw, sh = d.screen
    if sw <= 0 or sh <= 0:
        return None
    cols, rows = round(d.geometry[0] / sw), round(d.geometry[1] / sh)
    if cols * rows <= 1:
        return None
    cell = None
    if d.viewport is not None:
        cell = (min(cols - 1, max(0, d.viewport[0] // sw)), min(rows - 1, max(0, d.viewport[1] // sh)))
    return cols, rows, cell


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
    vp = viewport_grid(d) if d.count <= 1 else None
    if vp is not None:
        return _render_viewports(d, vp, verbose)
    cells, how = grid(d.count, d.layout)
    lines = []
    cur = f" (current: {d.current + 1})" if d.current is not None else ""
    lines.append(f"{d.count} workspace(s){cur}: {how}")
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
        lines += _raw(d)
    return "\n".join(lines)


def _raw(d: Desktops) -> list[str]:
    return ["", f"_NET_NUMBER_OF_DESKTOPS: {d.count}",
            f"_NET_DESKTOP_LAYOUT: {d.layout if d.layout else 'not set'}",
            f"_NET_DESKTOP_GEOMETRY: {d.geometry if d.geometry else 'not set'}",
            f"_NET_DESKTOP_VIEWPORT (current): {list(d.viewport) if d.viewport is not None else 'not set'}",
            f"screen: {d.screen[0]}x{d.screen[1]}" if d.screen else "screen: unknown"]


def _render_viewports(d: Desktops, vp: tuple, verbose: bool) -> str:
    """Compiz: one desktop, several screen-sized viewports in a grid."""
    cols, rows, cell = vp
    sw, sh = d.screen
    lines = [f"{cols * rows} workspaces as viewports of one large desktop ({cols} x {rows}, "
             f"each {sw}x{sh}, all monitors in each)" + (f"; you are in column {cell[0] + 1}, "
             f"row {cell[1] + 1} from the top" if cell else "")]
    lines.append("  note: tilepane cannot open on or close per viewport yet; --workspace and the")
    lines.append("  layout's \"workspace\" treat them all as one workspace")

    def draw(label) -> None:
        width = len(str(cols * rows)) + 2
        for r in range(rows):
            out = []
            for c in range(cols):
                text = str(label(c, r))
                out.append((f"[{text}]" if cell == (c, r) else f" {text} ").rjust(width))
            lines.append("  " + " ".join(out).rstrip())

    lines.append("")
    lines.append("In the window manager's order (1 = top left, along the rows):")
    draw(lambda c, r: r * cols + c + 1)
    lines.append("")
    lines.append("Proposed numbering (0 bottom left, along the rows, rows upward):")
    draw(lambda c, r: (rows - 1 - r) * cols + c)
    if verbose:
        lines += _raw(d)
    return "\n".join(lines)
