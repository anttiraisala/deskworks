"""Window placement backends (SPEC.md section 4).

A backend finds the windows that terminals open, moves and sizes them, and
closes them. Only the X11 backend exists so far; `choose` explains why when no
backend is usable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol

from ..geometry import Rect


class BackendError(RuntimeError):
    """A window operation failed."""


@dataclass(frozen=True)
class WindowInfo:
    id: int
    wm_class: tuple[str, str]     # (instance, class)
    pid: Optional[int]
    title: str


@dataclass
class Placement:
    wanted: Rect                  # the layout rectangle
    planned: Rect                 # what the plan should produce (after cell snapping)
    actual: Rect                  # what the window manager gave
    cols: Optional[int] = None
    rows: Optional[int] = None
    notes: list[str] = field(default_factory=list)

    @property
    def exact(self) -> bool:
        return self.actual == self.planned


class Backend(Protocol):
    name: str

    def windows(self) -> set[int]: ...

    def wait_new_window(self, before: set[int], match: Callable[[WindowInfo], bool],
                        timeout: float) -> Optional[WindowInfo]: ...

    def place(self, window_id: int, target: Rect, snap: str) -> Placement: ...

    def metrics(self, window_id: int) -> Optional[tuple]: ...

    def find(self, wm_class: str) -> list[WindowInfo]: ...

    def close(self, window_id: int) -> None: ...

    def disconnect(self) -> None: ...


def choose() -> tuple[Optional[Backend], str]:
    """Return (backend, "") or (None, reason)."""
    from .. import doctor

    session = doctor.session_type()
    if session != "x11":
        return None, (f"no backend for a {session} session yet; only X11 is implemented "
                      "(run tilepane --doctor)")
    from . import x11

    ok, reason = x11.available()
    if not ok:
        return None, reason
    return x11.X11Backend(), ""
