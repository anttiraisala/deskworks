"""Layout geometry: a pure function with no windowing dependencies.

    compute(layout, area) -> list[LeafRect]

`layout` is the parsed JSON layout (a dict with `split`, optional `margin`,
`outer_margin`, `at_basis`). `area` is the work area of the target monitor.

Rules (SPEC.md section 3):

* A split is always made from the rectangle outside the margin. The margin is
  applied only at leaf level: window = leaf rectangle minus its insets.
* `margin` is the total gap between two windows, so each side of a leaf gets
  half of it. An odd margin is split floor/ceil (start side gets the floor),
  so the gap between neighbours is always exactly `margin` pixels.
* `outer_margin`, when set, is subtracted from the whole area first, and
  leaves at the outer edge get no extra inset there. The edge gap is then
  exactly `outer_margin`; it is not counted twice.
* All split boundaries are rounded to integers once, and adjacent panes share
  the same boundary value, so there are no gaps and no overlaps.
* Sizes: `N%` of the area being split, `Npx`, `Nfrac` (share of the space left
  over, `sizes` only). A bare number means pixels. If `sizes` has no `frac`
  entry, the last child absorbs the leftover space.
* `at_basis: "visible"` makes a pixel size the size of the visible window
  instead of the pre-margin rectangle. It uses the margin of the split node,
  and ignores a different margin set on a descendant.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from typing import Any, Optional

from deskmap.rect import Rect


class GeometryError(ValueError):
    """The layout cannot be laid out in the given area."""


@dataclass(frozen=True)
class LeafRect:
    id: str          # path of child indices, e.g. "1.0"; "root" for a lone leaf
    rect: Rect       # the window rectangle (after margins)
    outer: Rect      # the pane rectangle before margins
    leaf: dict       # the leaf node (run, cwd, title, ...)


@dataclass(frozen=True)
class _Size:
    kind: str        # "px" | "%" | "frac"
    value: float


@dataclass(frozen=True)
class _Ctx:
    margin: int
    at_basis: str
    outer: bool      # outer_margin is set


_SIZE_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*(px|%|frac)?\s*$")
_COLUMNS = {"columns", "v", "vertical"}
_ROWS = {"rows", "h", "horizontal"}
_SPLIT_KEYS = {"dir", "a", "b", "at", "children", "sizes"}


def _round(x: float) -> int:
    return math.floor(x + 0.5)


def _pid(path: tuple[int, ...]) -> str:
    return ".".join(map(str, path)) if path else "root"


def _margin(value: Any, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise GeometryError(f"{what} must be a non-negative number, got {value!r}")
    return _round(value)


def parse_size(value: Any, what: str, *, allow_negative: bool = False,
                allow_frac: bool = True) -> _Size:
    if isinstance(value, bool):
        raise GeometryError(f"{what}: invalid size {value!r}")
    if isinstance(value, (int, float)):
        text = f"{value}px"
    else:
        text = str(value)
    m = _SIZE_RE.match(text)
    if not m:
        raise GeometryError(f"{what}: invalid size {value!r} (use 60%, 300px, 1frac)")
    number, kind = float(m[1]), m[2] or "px"
    if kind == "frac" and not allow_frac:
        raise GeometryError(f"{what}: 'frac' is only allowed in 'sizes', got {value!r}")
    if number == 0 or (number < 0 and not (allow_negative and kind != "frac")):
        raise GeometryError(f"{what}: size must be positive, got {value!r}")
    return _Size(kind, number)


def compute(layout: dict, area: Rect) -> list[LeafRect]:
    """Compute the window rectangle of every leaf in `layout` within `area`."""
    if not isinstance(layout, dict) or "split" not in layout:
        raise GeometryError("layout needs a 'split' node")
    margin = _margin(layout.get("margin", 0), "margin")
    basis = layout.get("at_basis", "outer")
    if basis not in ("outer", "visible"):
        raise GeometryError(f"at_basis must be 'outer' or 'visible', got {basis!r}")

    outer = layout.get("outer_margin")
    if outer is not None:
        o = _margin(outer, "outer_margin")
        area = Rect(area.x + o, area.y + o, area.width - 2 * o, area.height - 2 * o)
    if area.width <= 0 or area.height <= 0:
        raise GeometryError("outer_margin leaves no room in the work area")

    out: list[LeafRect] = []
    _walk(layout["split"], area, (), _Ctx(margin, basis, outer is not None),
          (True, True, True, True), out)
    return out


def _walk(node: Any, rect: Rect, path: tuple[int, ...], ctx: _Ctx,
          edges: tuple[bool, bool, bool, bool], out: list[LeafRect]) -> None:
    where = f"node '{_pid(path)}'"
    if not isinstance(node, dict):
        raise GeometryError(f"{where} must be an object")
    if "margin" in node:
        ctx = replace(ctx, margin=_margin(node["margin"], f"{where} margin"))
    if "at_basis" in node:
        if node["at_basis"] not in ("outer", "visible"):
            raise GeometryError(f"{where}: at_basis must be 'outer' or 'visible'")
        ctx = replace(ctx, at_basis=node["at_basis"])

    if not (_SPLIT_KEYS & node.keys()):
        out.append(_leaf(node, rect, path, ctx, edges))
        return

    vertical = _direction(node, where)
    children, sizes = _children_and_sizes(node, where)
    n = len(children)
    extent = rect.width if vertical else rect.height
    origin = rect.x if vertical else rect.y
    at_start, at_end = (edges[0], edges[2]) if vertical else (edges[1], edges[3])

    half_lo = ctx.margin // 2
    half_hi = ctx.margin - half_lo
    insets = [
        (0 if ctx.outer and i == 0 and at_start else half_lo,
         0 if ctx.outer and i == n - 1 and at_end else half_hi)
        for i in range(n)
    ]
    sizes_px = _distribute(sizes, extent, insets, ctx.at_basis, where)

    bounds = [origin]
    acc = 0.0
    for s in sizes_px[:-1]:
        acc += s
        bounds.append(_round(origin + acc))
    bounds.append(origin + extent)

    for i, child in enumerate(children):
        if vertical:
            sub = Rect(bounds[i], rect.y, bounds[i + 1] - bounds[i], rect.height)
            sub_edges = (edges[0] and i == 0, edges[1], edges[2] and i == n - 1, edges[3])
        else:
            sub = Rect(rect.x, bounds[i], rect.width, bounds[i + 1] - bounds[i])
            sub_edges = (edges[0], edges[1] and i == 0, edges[2], edges[3] and i == n - 1)
        _walk(child, sub, path + (i,), ctx, sub_edges, out)


def _leaf(node: dict, rect: Rect, path: tuple[int, ...], ctx: _Ctx,
          edges: tuple[bool, bool, bool, bool]) -> LeafRect:
    lo = ctx.margin // 2
    hi = ctx.margin - lo
    left = 0 if ctx.outer and edges[0] else lo
    top = 0 if ctx.outer and edges[1] else lo
    right = 0 if ctx.outer and edges[2] else hi
    bottom = 0 if ctx.outer and edges[3] else hi
    window = Rect(rect.x + left, rect.y + top,
                  rect.width - left - right, rect.height - top - bottom)
    if window.width <= 0 or window.height <= 0:
        raise GeometryError(
            f"pane '{_pid(path)}' is too small: {rect.width}x{rect.height} "
            f"with margin {ctx.margin}")
    return LeafRect(_pid(path), window, rect, node)


def _direction(node: dict, where: str) -> bool:
    """True for columns (children side by side), False for rows (stacked)."""
    d = node.get("dir")
    if d in _COLUMNS:
        return True
    if d in _ROWS:
        return False
    raise GeometryError(f"{where}: 'dir' must be 'columns' or 'rows', got {d!r}")


def _children_and_sizes(node: dict, where: str) -> tuple[list, list[_Size]]:
    if "children" in node:
        if _SPLIT_KEYS & {"a", "b", "at"} & node.keys():
            raise GeometryError(f"{where}: 'children' cannot be combined with a/b/at")
        children = node["children"]
        if not isinstance(children, list) or not children:
            raise GeometryError(f"{where}: 'children' must be a non-empty list")
        raw = node.get("sizes")
        if raw is None:
            return children, [_Size("frac", 1.0)] * len(children)
        if not isinstance(raw, list) or len(raw) != len(children):
            raise GeometryError(
                f"{where}: 'sizes' must be a list with one entry per child")
        return children, [parse_size(s, f"{where} sizes[{i}]")
                          for i, s in enumerate(raw)]

    if "sizes" in node:
        raise GeometryError(f"{where}: 'sizes' needs 'children'")
    if "a" not in node or "b" not in node:
        raise GeometryError(f"{where}: a split needs both 'a' and 'b' (or 'children')")
    at = parse_size(node.get("at", "50%"), f"{where} at",
                     allow_negative=True, allow_frac=False)
    rest = _Size("frac", 1.0)
    if at.value > 0:
        sizes = [at, rest]
    else:
        sizes = [rest, _Size(at.kind, -at.value)]
    return [node["a"], node["b"]], sizes


def _distribute(sizes: list[_Size], extent: int, insets: list[tuple[int, int]],
                basis: str, where: str) -> list[float]:
    out: list[Optional[float]] = [None] * len(sizes)
    fixed = 0.0
    frac_total = 0.0
    for i, s in enumerate(sizes):
        if s.kind == "frac":
            frac_total += s.value
            continue
        if s.kind == "px":
            e = s.value + (sum(insets[i]) if basis == "visible" else 0)
        else:
            e = extent * s.value / 100
        out[i] = e
        fixed += e
    remaining = extent - fixed
    if remaining < -1e-9:
        raise GeometryError(f"{where}: sizes exceed the available {extent}px")
    if frac_total > 0:
        for i, s in enumerate(sizes):
            if s.kind == "frac":
                out[i] = remaining * s.value / frac_total
    else:
        out[-1] = (out[-1] or 0.0) + remaining
    return [float(v) for v in out]  # type: ignore[arg-type]
