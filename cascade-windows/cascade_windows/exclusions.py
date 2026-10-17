"""Excluding monitors and workspaces from the cascade. Pure logic, no window system access.

A rule names monitors and/or workspaces. A monitor is given by its name or its index, a workspace by its
number or its grid position "x,y". Workspaces are numbered like in every deskworks tool: from the bottom
left corner, left to right along each row and then row by row upwards, starting from 0, so ``0,0`` is the
bottom-left workspace. A rule with only ``monitor`` excludes
those monitors on every workspace, a rule with only ``workspace`` excludes every monitor of those
workspaces, and a rule with both excludes only that combination.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, Tuple, Union

from deskmap.workspaces import user_numbers

from .model import Monitor

MonitorRef = Union[int, str]  # an index or a name
WorkspaceRef = Union[int, Tuple[int, int]]  # an index or an (x, y) position

_POSITION = re.compile(r"^\s*(\d+)\s*,\s*(\d+)\s*$")


class RuleError(ValueError):
    """An exclusion rule in the configuration cannot be understood."""


@dataclass(frozen=True)
class ExcludeRule:
    monitors: Optional[Tuple[MonitorRef, ...]] = None  # None: any monitor
    workspaces: Optional[Tuple[WorkspaceRef, ...]] = None  # None: any workspace


@dataclass(frozen=True)
class WorkspaceGrid:
    """The workspaces in the order the backend lists them (reading order, top left first), laid out
    ``columns`` per row. People number them from the bottom left, row by row upwards (``number``)."""

    keys: Tuple[str, ...]
    columns: int

    @staticmethod
    def create(keys: Sequence[str], columns: int = 0) -> "WorkspaceGrid":
        """``columns`` of 0 (unknown) means all workspaces are in one row."""
        keys = tuple(keys)
        width = columns if columns and columns > 0 else max(1, len(keys))
        return WorkspaceGrid(keys, width)

    @property
    def rows(self) -> int:
        return max(1, -(-len(self.keys) // self.columns))

    def _cells(self) -> List[List[Optional[int]]]:
        """Rows from the top; each cell holds the backend index of its workspace or None."""
        total = len(self.keys)
        return [
            [r * self.columns + c if r * self.columns + c < total else None for c in range(self.columns)]
            for r in range(self.rows)
        ]

    def index_of(self, key: str) -> Optional[int]:
        try:
            return self.keys.index(key)
        except ValueError:
            return None

    def number(self, index: int) -> int:
        """The number people use for the workspace at this backend index."""
        return user_numbers(self._cells())[index]

    def index_of_number(self, number: int) -> Optional[int]:
        for index, value in user_numbers(self._cells()).items():
            if value == number:
                return index
        return None

    def position(self, index: int) -> Tuple[int, int]:
        """(column from the left, row from the bottom) of the workspace at this backend index."""
        return index % self.columns, self.rows - 1 - index // self.columns

    def index_at(self, x: int, y: int) -> Optional[int]:
        if not 0 <= x < self.columns or not 0 <= y < self.rows:
            return None
        index = (self.rows - 1 - y) * self.columns + x
        return index if index < len(self.keys) else None

    def label(self, index: int) -> str:
        x, y = self.position(index)
        return "%d (%d,%d)" % (self.number(index), x, y)


# ---------------------------------------------------------------------------------- parsing


def _as_list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, list) else [value]


def _monitor_ref(value: Any, where: str) -> MonitorRef:
    if isinstance(value, bool):
        raise RuleError("%s: a monitor must be a name or a number" % where)
    if isinstance(value, int):
        if value < 0:
            raise RuleError("%s: a monitor number cannot be negative" % where)
        return value
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise RuleError("%s: a monitor must be a name or a number, not %r" % (where, value))


def _workspace_ref(value: Any, where: str) -> WorkspaceRef:
    if isinstance(value, bool):
        raise RuleError("%s: a workspace must be a number or a position like \"1,0\"" % where)
    if isinstance(value, int):
        if value < 0:
            raise RuleError("%s: a workspace number cannot be negative" % where)
        return value
    if isinstance(value, str):
        match = _POSITION.match(value)
        if match:
            return int(match.group(1)), int(match.group(2))
    raise RuleError("%s: a workspace must be a number or a position like \"1,0\", not %r" % (where, value))


def parse_rules(raw: Any, is_comment=lambda key: False) -> Tuple[ExcludeRule, ...]:
    """Turn the ``exclude`` list of the configuration file into rules."""
    if not isinstance(raw, list):
        raise RuleError("'exclude' must be a list of rules")
    rules = []
    for number, item in enumerate(raw):
        where = "exclude[%d]" % number
        if not isinstance(item, dict):
            raise RuleError("%s must be an object with 'monitor' and/or 'workspace'" % where)
        keys = {str(key) for key in item if not is_comment(str(key))}
        unknown = keys - {"monitor", "workspace"}
        if unknown:
            raise RuleError(
                "%s has unknown key(s): %s (use 'monitor' and/or 'workspace')" % (where, ", ".join(sorted(unknown)))
            )
        if not keys:
            raise RuleError("%s must name a 'monitor' and/or a 'workspace'; an empty rule would exclude everything" % where)
        monitors = workspaces = None
        if "monitor" in item:
            values = _as_list(item["monitor"])
            if not values:
                raise RuleError("%s: 'monitor' is an empty list" % where)
            monitors = tuple(_monitor_ref(v, where) for v in values)
        if "workspace" in item:
            values = _as_list(item["workspace"])
            if not values:
                raise RuleError("%s: 'workspace' is an empty list" % where)
            workspaces = tuple(_workspace_ref(v, where) for v in values)
        rules.append(ExcludeRule(monitors, workspaces))
    return tuple(rules)


def rule_to_dict(rule: ExcludeRule) -> dict:
    result: dict = {}
    if rule.monitors is not None:
        result["monitor"] = rule.monitors[0] if len(rule.monitors) == 1 else list(rule.monitors)
    if rule.workspaces is not None:
        refs = [("%d,%d" % ref) if isinstance(ref, tuple) else ref for ref in rule.workspaces]
        result["workspace"] = refs[0] if len(refs) == 1 else refs
    return result


# ---------------------------------------------------------------------------------- matching


def _monitor_matches(ref: MonitorRef, monitor: Monitor) -> bool:
    if isinstance(ref, int):
        return monitor.index == ref
    return monitor.name.casefold() == ref.casefold()


def _workspace_matches(ref: WorkspaceRef, index: int, grid: WorkspaceGrid) -> bool:
    if isinstance(ref, int):
        return grid.number(index) == ref
    return grid.position(index) == ref


def is_excluded(rules: Sequence[ExcludeRule], monitor: Monitor, workspace: str, grid: WorkspaceGrid) -> bool:
    """True when any rule excludes this monitor on this workspace."""
    index = grid.index_of(workspace)
    for rule in rules:
        if rule.monitors is not None and not any(_monitor_matches(r, monitor) for r in rule.monitors):
            continue
        if rule.workspaces is not None:
            if index is None or not any(_workspace_matches(r, index, grid) for r in rule.workspaces):
                continue
        return True
    return False


# ---------------------------------------------------------------------------------- reporting


def describe_targets(monitors: Sequence[Monitor], grid: WorkspaceGrid, current: str) -> List[str]:
    """The numbers and names to use in 'exclude' rules, one per line."""
    lines = ["workspaces (%d column(s), %d row(s)); use the number or the position x,y:" % (grid.columns, grid.rows)]
    ordered = sorted(range(len(grid.keys)), key=grid.number)
    for index in ordered:
        x, y = grid.position(index)
        lines.append("  %d  %d,%d%s" % (grid.number(index), x, y, "  (current)" if grid.keys[index] == current else ""))
    lines.append("monitors; use the number or the name:")
    for monitor in monitors:
        lines.append("  %d  %s  %s" % (monitor.index, monitor.name, monitor.rect))
    return lines


def unmatched_references(rules: Sequence[ExcludeRule], monitors: Sequence[Monitor], grid: WorkspaceGrid) -> List[str]:
    """Warnings for rule parts that match nothing right now (a monitor may simply be unplugged)."""
    messages = []
    for number, rule in enumerate(rules):
        for ref in rule.monitors or ():
            if not any(_monitor_matches(ref, m) for m in monitors):
                messages.append("exclude[%d]: no monitor matches %r at the moment" % (number, ref))
        for ref in rule.workspaces or ():
            index = grid.index_of_number(ref) if isinstance(ref, int) else grid.index_at(*ref)
            if index is None:
                shown = ref if isinstance(ref, int) else "%d,%d" % ref
                messages.append("exclude[%d]: no workspace matches %s at the moment" % (number, shown))
    return messages
