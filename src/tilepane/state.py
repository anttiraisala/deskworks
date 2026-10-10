"""State file: which windows tilepane opened (SPEC.md section 4, state management).

One JSON file in `$XDG_STATE_HOME/tilepane/` (default ~/.local/state/tilepane/).
A record ties a window to the key (config path, layout name, monitor connector)
and the pane (leaf id) it belongs to. Updates are done under a file lock and
written atomically, so two tilepane runs cannot corrupt each other.
"""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from typing import Iterator, Optional

VERSION = 1


@dataclass
class Record:
    xid: int
    source: str          # absolute path of the config file
    layout: str
    monitor: str         # connector name
    leaf: str            # leaf id
    pid: Optional[int] = None
    opened: float = field(default_factory=time.time)

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.source, self.layout, self.monitor)


def state_dir() -> str:
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(base, "tilepane")


class StateStore:
    def __init__(self, directory: Optional[str] = None):
        self.dir = directory or state_dir()
        self.path = os.path.join(self.dir, "state.json")
        self._lock_path = os.path.join(self.dir, "state.lock")

    def _read(self) -> list[Record]:
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return []
        out = []
        for raw in data.get("windows", []) if isinstance(data, dict) else []:
            try:
                out.append(Record(**raw))
            except TypeError:
                continue    # a record from an incompatible version: drop it
        return out

    def _write(self, records: list[Record]) -> None:
        fd, tmp = tempfile.mkstemp(dir=self.dir, prefix="state.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"version": VERSION, "windows": [asdict(r) for r in records]}, fh,
                          indent=2)
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def load(self) -> list[Record]:
        return self._read()

    @contextmanager
    def transaction(self) -> Iterator[list[Record]]:
        """Read the records, let the caller change the list, write it back."""
        os.makedirs(self.dir, exist_ok=True)
        with open(self._lock_path, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            records = self._read()
            yield records
            self._write(records)
