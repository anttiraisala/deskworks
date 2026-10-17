"""The interface of window system backends.

A backend finds new windows, moves and sizes them, and closes them. Only the
X11 backend exists so far (`deskmap.backends.x11`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol

from ..rect import Rect


class BackendError(RuntimeError):
    """A window operation failed."""


@dataclass(frozen=True)
class WindowInfo:
    id: int
    wm_class: tuple[str, str]     # (instance, class)
    pid: Optional[int]
    title: str
    desktop: Optional[int] = None   # workspace index (see workspaces.py); None: on all, or not known


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

    def place(self, window_id: int, target: Rect, snap: str,
              decorations: bool = True) -> Placement: ...

    def metrics(self, window_id: int) -> Optional[tuple]: ...

    def find(self, wm_class: str) -> list[WindowInfo]: ...

    def current_desktop(self) -> Optional[int]: ...

    def desktop_count(self) -> Optional[int]: ...

    def desktop_info(self): ...       # workspaces.Desktops

    def move_to_desktop(self, window_id: int, desktop: int) -> None: ...

    def workspace_offset(self, desktop: int) -> tuple[int, int]: ...

    def close(self, window_id: int) -> None: ...

    def disconnect(self) -> None: ...
