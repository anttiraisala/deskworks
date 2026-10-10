"""Opening, re-placing and closing layouts, with the state file as memory.

A layout instance is identified by its key: (config path, layout name, monitor
connector). Opening a layout that is already open reconciles it: windows are
matched to panes by leaf id and moved to the computed rectangles, missing panes
are opened, and windows whose pane is gone are closed only with `prune`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from .backends import Backend, BackendError, Placement
from .geometry import LeafRect
from .opener import Opener, PaneResult
from .state import Record, StateStore
from .terminals import WINDOW_CLASS

Key = tuple[str, str, str]


def source_path(source: Optional[str], default: str) -> str:
    return os.path.abspath(source or default)


@dataclass
class UnitReport:
    results: list[PaneResult] = field(default_factory=list)
    replaced: int = 0
    opened: int = 0
    pruned: int = 0
    extra: list[str] = field(default_factory=list)   # leaf ids with a window but no pane

    @property
    def failed(self) -> list[PaneResult]:
        return [r for r in self.results if not r.ok]


class Manager:
    def __init__(self, backend: Backend, store: StateStore, opener: Opener):
        self.backend, self.store, self.opener = backend, store, opener

    def _alive(self) -> set[int]:
        return {w.id for w in self.backend.find(WINDOW_CLASS)}

    def _drop_dead(self, records: list[Record]) -> None:
        alive = self._alive()
        records[:] = [r for r in records if r.xid in alive]

    def is_open(self, key: Key) -> bool:
        with self.store.transaction() as records:
            self._drop_dead(records)
            return any(r.key == key for r in records)

    def open_unit(self, key: Key, leaves: list[LeafRect], *, prune: bool = False) -> UnitReport:
        report = UnitReport()
        with self.store.transaction() as records:
            self._drop_dead(records)
            mine = {r.leaf: r for r in records if r.key == key}
            wanted = {lr.leaf.get("id", lr.id) for lr in leaves if not lr.leaf.get("empty")}

            for lr in leaves:
                leaf = lr.leaf
                if leaf.get("empty"):
                    continue
                leaf_id = leaf.get("id", lr.id)
                existing = mine.get(leaf_id)
                if existing is not None:
                    result = self._replace(existing, lr)
                    if result.ok:
                        report.replaced += 1
                else:
                    result = self.opener.open_pane(lr)
                    if result.ok and result.window_id is not None:
                        records.append(Record(result.window_id, *key, leaf_id,
                                              pid=result.pid))
                        report.opened += 1
                report.results.append(result)

            for leaf_id, rec in mine.items():
                if leaf_id in wanted:
                    continue
                if prune:
                    self._close(rec.xid)
                    records.remove(rec)
                    report.pruned += 1
                else:
                    report.extra.append(leaf_id)
        return report

    def _replace(self, rec: Record, lr: LeafRect) -> PaneResult:
        leaf_id = lr.leaf.get("id", lr.id)
        result = PaneResult(leaf_id, ok=False, window_id=rec.xid, action="replaced")
        try:
            placement: Placement = self.backend.place(
                rec.xid, lr.rect, lr.leaf.get("snap", "cell"), lr.leaf.get("decorations", True))
        except Exception as exc:  # noqa: BLE001 - report and carry on with other panes
            result.error = f"window {rec.xid:#x} could not be re-placed: {exc}"
            return result
        result.placement = placement
        result.warnings += placement.notes
        result.ok = True
        return result

    def _close(self, xid: int) -> None:
        try:
            self.backend.close(xid)
        except BackendError:
            pass

    def close(self, *, source: Optional[str] = None, layout: Optional[str] = None,
              monitor: Optional[str] = None) -> int:
        """Close the windows that match; None matches anything. Returns how many."""
        count = 0
        with self.store.transaction() as records:
            self._drop_dead(records)
            keep = []
            for r in records:
                if ((source is None or r.source == source)
                        and (layout is None or r.layout == layout)
                        and (monitor is None or r.monitor == monitor)):
                    self._close(r.xid)
                    count += 1
                else:
                    keep.append(r)
            records[:] = keep
        return count
