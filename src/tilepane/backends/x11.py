"""X11 backend on python-xlib, using EWMH hints.

Works with window managers that follow EWMH (Compiz, Mutter, KWin, Xfwm,
Openbox, ...). Tiling window managers need a floating rule for class
"tilepane". Position and size are set with `_NET_MOVERESIZE_WINDOW`, which
places the window frame's top-left corner and gives the client size.
"""

from __future__ import annotations

import importlib.util
import os
import time
from typing import Callable, Optional

from ..geometry import Rect
from ..placement import Extents, SizeHints, hints_from_wm, plan, visible_rect
from . import BackendError, Placement, WindowInfo

_SOURCE_APPLICATION = 1 << 12
_HAS_XYWH = (1 << 8) | (1 << 9) | (1 << 10) | (1 << 11)
_GRAVITY_NORTH_WEST = 1


def available() -> tuple[bool, str]:
    if not os.environ.get("DISPLAY"):
        return False, "DISPLAY is not set"
    if importlib.util.find_spec("Xlib") is None:
        return False, "python-xlib is not installed (pip install python-xlib)"
    try:
        from Xlib import display
        display.Display().close()
    except Exception as exc:  # noqa: BLE001 - any connection failure is a reason
        return False, f"cannot connect to the X server: {exc}"
    return True, ""


class X11Backend:
    name = "x11-xlib"

    def __init__(self) -> None:
        from Xlib import X, display

        self._X = X
        self.d = display.Display()
        self.root = self.d.screen().root

    def disconnect(self) -> None:
        self.d.close()

    # --- low-level helpers -------------------------------------------------

    def _atom(self, name: str) -> int:
        return self.d.intern_atom(name)

    def _window(self, wid: int):
        return self.d.create_resource_object("window", wid)

    def _cardinals(self, win, name: str) -> Optional[list[int]]:
        prop = win.get_full_property(self._atom(name), self._X.AnyPropertyType)
        return None if prop is None else [int(v) for v in prop.value]

    def _send(self, win, message: str, data: list[int]) -> None:
        from Xlib.protocol import event

        ev = event.ClientMessage(window=win, client_type=self._atom(message),
                                 data=(32, (data + [0] * 5)[:5]))
        mask = self._X.SubstructureRedirectMask | self._X.SubstructureNotifyMask
        self.root.send_event(ev, event_mask=mask)
        self.d.flush()

    # --- windows -----------------------------------------------------------

    def windows(self) -> set[int]:
        ids = self._cardinals(self.root, "_NET_CLIENT_LIST")
        return set(ids or [])

    def info(self, wid: int) -> Optional[WindowInfo]:
        from Xlib import error

        try:
            win = self._window(wid)
            cls = win.get_wm_class() or ("", "")
            pid = self._cardinals(win, "_NET_WM_PID")
            name = win.get_full_property(self._atom("_NET_WM_NAME"), self._X.AnyPropertyType)
            title = name.value.decode(errors="replace") if name is not None else (win.get_wm_name() or "")
            if isinstance(title, bytes):
                title = title.decode(errors="replace")
            return WindowInfo(wid, (cls[0], cls[1]), pid[0] if pid else None, title)
        except error.XError:
            return None

    def find(self, wm_class: str) -> list[WindowInfo]:
        found = [self.info(w) for w in sorted(self.windows())]
        return [i for i in found if i is not None and i.wm_class[1] == wm_class]

    def wait_new_window(self, before: set[int], match: Callable[[WindowInfo], bool],
                        timeout: float) -> Optional[WindowInfo]:
        deadline = time.monotonic() + timeout
        while True:
            for wid in sorted(self.windows() - before):
                info = self.info(wid)
                if info is not None and match(info):
                    return info
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.05)

    def close(self, window_id: int) -> None:
        self._send(self._window(window_id), "_NET_CLOSE_WINDOW",
                   [int(time.time()), 1, 0, 0, 0])

    # --- geometry ----------------------------------------------------------

    def _frame_extents(self, win) -> Extents:
        vals = self._cardinals(win, "_NET_FRAME_EXTENTS")
        if vals is None:
            self._send(win, "_NET_REQUEST_FRAME_EXTENTS", [])
            deadline = time.monotonic() + 0.5
            while vals is None and time.monotonic() < deadline:
                time.sleep(0.03)
                vals = self._cardinals(win, "_NET_FRAME_EXTENTS")
        return Extents(*vals[:4]) if vals and len(vals) >= 4 else Extents()

    def _gtk_extents(self, win) -> Extents:
        vals = self._cardinals(win, "_GTK_FRAME_EXTENTS")
        return Extents(*vals[:4]) if vals and len(vals) >= 4 else Extents()

    def _size_hints(self, win) -> Optional[SizeHints]:
        h = win.get_wm_normal_hints()
        if h is None:
            return None
        return hints_from_wm(h.flags, (h.base_width, h.base_height),
                             (h.width_inc, h.height_inc), (h.min_width, h.min_height))

    def metrics(self, window_id: int) -> Optional[tuple]:
        """(frame extents, gtk extents, size hints) of a window, to estimate later windows."""
        from Xlib import error

        try:
            win = self._window(window_id)
            return self._frame_extents(win), self._gtk_extents(win), self._size_hints(win)
        except error.XError:
            return None

    def _visible_now(self, win, frame: Extents, gtk: Extents) -> Rect:
        geo = win.get_geometry()
        pos = self.root.translate_coords(win, 0, 0)
        return visible_rect(pos.x, pos.y, geo.width, geo.height, frame, gtk)

    def _clear_states(self, win) -> None:
        names = ("_NET_WM_STATE_MAXIMIZED_HORZ", "_NET_WM_STATE_MAXIMIZED_VERT",
                 "_NET_WM_STATE_FULLSCREEN")
        current = self._cardinals(win, "_NET_WM_STATE") or []
        for name in names:
            atom = self._atom(name)
            if atom in current:
                self._send(win, "_NET_WM_STATE", [0, atom, 0, 1, 0])

    def place(self, window_id: int, target: Rect, snap: str) -> Placement:
        from Xlib import error

        try:
            win = self._window(window_id)
            frame, gtk = self._frame_extents(win), self._gtk_extents(win)
            hints = self._size_hints(win)
            p = plan(target, frame, gtk, hints, snap)
            self._clear_states(win)

            actual = target
            for _ in range(3):
                self._send(win, "_NET_MOVERESIZE_WINDOW",
                           [_GRAVITY_NORTH_WEST | _HAS_XYWH | _SOURCE_APPLICATION,
                            p.x, p.y, p.width, p.height])
                deadline = time.monotonic() + 0.6
                while True:
                    time.sleep(0.03)
                    actual = self._visible_now(win, frame, gtk)
                    if actual == p.visible or time.monotonic() >= deadline:
                        break
                if actual == p.visible:
                    break
            return Placement(target, p.visible, actual, p.cols, p.rows, list(p.notes))
        except error.XError as exc:
            raise BackendError(f"window {window_id:#x} went away or refused: {exc}") from exc
