"""Opening, re-placing and closing layouts, with the state file as memory.

A layout instance is identified by its key: (config path, layout name, monitor
connector). Opening a layout that is already open reconciles it: windows are
matched to panes by leaf id and moved to the computed rectangles, missing panes
are opened, and windows whose pane is gone are closed only with `prune`.

Workspaces keep instances apart: a layout opened on workspace 1 and again on
workspace 2 has two sets of windows. `workspace` arguments are 0-based EWMH
desktop numbers; None matches every workspace (and is what a window manager
without workspaces gives). A window on all workspaces matches any of them.
"""

from __future__ import annotations

import os
import time
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
    close_timeout = 2.0     # seconds to wait for a window to go after asking it to close

    def __init__(self, backend: Backend, store: StateStore, opener: Opener):
        self.backend, self.store, self.opener = backend, store, opener
        self.refused: list[int] = []      # windows the last close() could not close

    def _drop_dead(self, records: list[Record]) -> None:
        """Forget windows that are gone, and note which workspace the others are on now."""
        alive = {w.id: w for w in self.backend.find(WINDOW_CLASS)}
        records[:] = [r for r in records if r.xid in alive]
        for r in records:
            r.workspace = alive[r.xid].desktop

    @staticmethod
    def _on(rec: Record, workspace: Optional[int]) -> bool:
        return workspace is None or rec.workspace is None or rec.workspace == workspace

    def is_open(self, key: Key, workspace: Optional[int] = None) -> bool:
        with self.store.transaction() as records:
            self._drop_dead(records)
            return any(r.key == key and self._on(r, workspace) for r in records)

    def open_unit(self, key: Key, leaves: list[LeafRect], *, prune: bool = False,
                  workspace: Optional[int] = None) -> UnitReport:
        report = UnitReport()
        # New windows appear on the current workspace; move them when another was asked for.
        move = workspace is not None and self.backend.current_desktop() != workspace
        with self.store.transaction() as records:
            self._drop_dead(records)
            mine = {r.leaf: r for r in records if r.key == key and self._on(r, workspace)}
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
                        if move:
                            try:
                                self.backend.move_to_desktop(result.window_id, workspace)
                            except BackendError as exc:
                                result.warnings.append(str(exc))
                        records.append(Record(result.window_id, *key, leaf_id,
                                              pid=result.pid, workspace=workspace))
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
              monitor: Optional[str] = None, workspace: Optional[int] = None) -> int:
        """Close the windows that match; None matches anything. Returns how many closed.

        A close request can be lost, so the windows are checked afterwards and
        asked once more. Windows that still stay open are listed in `refused`
        and kept in the state, so the next close tries them again.
        """
        self.refused = []
        with self.store.transaction() as records:
            self._drop_dead(records)
            chosen = [r for r in records
                      if (source is None or r.source == source)
                      and (layout is None or r.layout == layout)
                      and (monitor is None or r.monitor == monitor)
                      and self._on(r, workspace)]
            if not chosen:
                return 0
            pending = {r.xid for r in chosen}
            for attempt in range(2):
                for xid in sorted(pending):
                    self._close(xid)
                pending = self._wait_gone(pending, self.close_timeout)
                if not pending:
                    break
            self.refused = sorted(pending)
            records[:] = [r for r in records if r not in chosen or r.xid in pending]
        return len(chosen) - len(pending)

    def _wait_gone(self, xids: set[int], timeout: float) -> set[int]:
        """The windows of `xids` that are still open after waiting up to `timeout`."""
        deadline = time.monotonic() + timeout
        while True:
            left = xids & self.backend.windows()
            if not left or time.monotonic() >= deadline:
                return left
            time.sleep(0.05)
