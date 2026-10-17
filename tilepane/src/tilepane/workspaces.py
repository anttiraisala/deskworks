"""Workspace numbers, and `--workspaces`, which shows them.

EWMH lists workspaces (desktops) as a plain sequence. A pager may publish
their arrangement as a grid in `_NET_DESKTOP_LAYOUT` (orientation, columns,
rows, starting corner); without it they form one row. Compiz/Unity instead has
one large desktop shown one screen at a time: its viewports form the grid.

Inside tilepane (backends, manager, state) a workspace is its index in the
window manager's order: the desktop number, or for viewports the cell counted
from the top left along the rows. The number a person uses (`--workspace N`,
the layout key `workspace`, messages, the editor) counts from 0 in the bottom
left corner, along each row, then the rows upward. `Numbering` converts.
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


def user_numbers(cells: list[list[Optional[int]]]) -> dict[int, int]:
    """Index -> the number people use: 0 bottom left, along each row, rows upward."""
    out: dict[int, int] = {}
    n = 0
    for row in reversed(cells):
        for idx in row:
            if idx is not None:
                out[idx] = n
                n += 1
    return out


def arrangement(d: Desktops) -> tuple[list[list[Optional[int]]], str, Optional[int]]:
    """Rows (top first) of workspace indexes, a description, and the current index.

    Viewports (Compiz) are numbered from the top left along the rows, the same
    way the X11 backend numbers them.
    """
    vp = viewport_grid(d) if d.count <= 1 else None
    if vp is not None:
        cols, rows, cell = vp
        cells: list[list[Optional[int]]] = [[r * cols + c for c in range(cols)] for r in range(rows)]
        sw, sh = d.screen
        how = (f"viewports of one large desktop, {cols} x {rows}, each {sw}x{sh} "
               f"(all monitors in each)")
        return cells, how, (cell[1] * cols + cell[0]) if cell is not None else None
    cells, how = grid(d.count, d.layout)
    return cells, how, d.current


@dataclass
class Numbering:
    """The workspaces of this machine, by the numbers people use."""
    count: int
    current: Optional[int]                 # index of the current workspace
    to_user: dict[int, int]                # index -> number
    cells: list[list[Optional[int]]]
    how: str

    @classmethod
    def of(cls, d: Optional[Desktops]) -> "Numbering":
        if d is None:
            return cls(0, None, {}, [], "no workspaces")
        cells, how, current = arrangement(d)
        nums = user_numbers(cells)
        return cls(len(nums), current, nums, cells, how)

    def index(self, number: int) -> Optional[int]:
        """The index of workspace `number`, or None when there is no such workspace."""
        for idx, n in self.to_user.items():
            if n == number:
                return idx
        return None

    def number(self, index: Optional[int]) -> Optional[int]:
        return None if index is None else self.to_user.get(index, index)


def render(d: Desktops, verbose: bool = False) -> str:
    num = Numbering.of(d)
    cells = num.cells
    lines = []
    cur = f" (current: {num.number(num.current)})" if num.current is not None else ""
    lines.append(f"{num.count} workspace(s){cur}: {num.how}")
    width = max(len(str(num.count - 1)), 1) + 2

    def draw(label) -> None:
        for row in cells:
            out = []
            for idx in row:
                if idx is None:
                    out.append(" " * width)
                    continue
                text = str(label(idx))
                out.append((f"[{text}]" if idx == num.current else f" {text} ").rjust(width))
            lines.append("  " + " ".join(out).rstrip())

    lines.append("")
    lines.append("Numbers for --workspace N and \"workspace\" (0 bottom left, along the rows, rows upward):")
    draw(num.number)
    names = [n for n in d.names[:d.count]] if d.count > 1 else []
    defaults = lambda i: {f"workspace {i + 1}", f"desktop {i + 1}", str(i + 1), ""}
    if any(n.strip().lower() not in defaults(i) for i, n in enumerate(names)):
        lines.append("")
        lines.append("Names given by the window manager:")
        for i, n in sorted(enumerate(names), key=lambda e: num.number(e[0])):
            lines.append(f"  {num.number(i)}: {n}")
    if verbose:
        lines.append("")
        lines.append("The window manager's own order (1 = first):")
        draw(lambda i: i + 1)
        lines += _raw(d)
    return "\n".join(lines)


def _raw(d: Desktops) -> list[str]:
    return ["", f"_NET_NUMBER_OF_DESKTOPS: {d.count}",
            f"_NET_DESKTOP_LAYOUT: {d.layout if d.layout else 'not set'}",
            f"_NET_DESKTOP_GEOMETRY: {d.geometry if d.geometry else 'not set'}",
            f"_NET_DESKTOP_VIEWPORT (current): {list(d.viewport) if d.viewport is not None else 'not set'}",
            f"screen: {d.screen[0]}x{d.screen[1]}" if d.screen else "screen: unknown"]
