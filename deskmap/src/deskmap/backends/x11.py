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

from ..rect import Rect
from ..placement import Extents, SizeHints, hints_from_wm, plan, visible_rect
from . import BackendError, Placement, WindowInfo

_SOURCE_APPLICATION = 1 << 12
_HAS_XYWH = (1 << 8) | (1 << 9) | (1 << 10) | (1 << 11)
_GRAVITY_NORTH_WEST = 1
_ALL_DESKTOPS = 0xFFFFFFFF


def card32(value: int) -> int:
    """A value for a 32-bit client message field. Coordinates can be negative
    (a viewport above or left of the current one on Compiz); the field is sent
    as two's complement and the window manager reads it back as signed."""
    return value & 0xFFFFFFFF


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
                                 data=(32, [card32(v) for v in (data + [0] * 5)[:5]]))
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
            desk = self._cardinals(win, "_NET_WM_DESKTOP")
            desktop = desk[0] if desk and desk[0] != _ALL_DESKTOPS else None
            return WindowInfo(wid, (cls[0], cls[1]), pid[0] if pid else None, title, desktop)
        except error.XError:
            return None

    def find(self, wm_class: str) -> list[WindowInfo]:
        found = [self.info(w) for w in sorted(self.windows())]
        found = [i for i in found if i is not None and i.wm_class[1] == wm_class]
        vps = self._viewports()
        if vps is not None:
            # One large desktop: a window's workspace is the viewport it is in.
            from dataclasses import replace

            from Xlib import error

            for n, i in enumerate(found):
                if i.desktop is None:
                    continue           # on every workspace
                try:
                    found[n] = replace(i, desktop=self._window_viewport(self._window(i.id), vps))
                except error.XError:
                    pass
        return found

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

    # --- workspaces (EWMH desktops, or Compiz viewports) ----------------------
    #
    # A workspace is an index: the EWMH desktop number, or on one large desktop
    # split into screen-sized viewports (Compiz), the viewport counted from the
    # top left along the rows. There a window's workspace is where it is, and
    # windows go to another viewport by being placed at its offset.

    def _desktops_raw(self) -> Optional[int]:
        vals = self._cardinals(self.root, "_NET_NUMBER_OF_DESKTOPS")
        return vals[0] if vals else None

    def _current_raw(self) -> Optional[int]:
        vals = self._cardinals(self.root, "_NET_CURRENT_DESKTOP")
        return vals[0] if vals else None

    def _viewports(self) -> Optional[tuple[int, int, int, int, int, int]]:
        """(columns, rows, viewport width, height, current x, y) on Compiz, else None."""
        from ..workspaces import Desktops, viewport_grid

        count = self._desktops_raw() or 0
        if count > 1:
            return None
        scr = self.d.screen()
        size = (scr.width_in_pixels, scr.height_in_pixels)
        vp = viewport_grid(Desktops(count, 0, geometry=self._cardinals(self.root, "_NET_DESKTOP_GEOMETRY"),
                                    screen=size))
        if vp is None:
            return None
        here = self._viewport() or (0, 0)
        return vp[0], vp[1], size[0], size[1], here[0], here[1]

    @staticmethod
    def _cell(vps: tuple, x: int, y: int) -> int:
        """The viewport index of a point on the large desktop."""
        cols, rows, w, h = vps[:4]
        return min(rows - 1, max(0, y // h)) * cols + min(cols - 1, max(0, x // w))

    def current_desktop(self) -> Optional[int]:
        vps = self._viewports()
        if vps is not None:
            return self._cell(vps, vps[4], vps[5])
        return self._current_raw()

    def desktop_count(self) -> Optional[int]:
        vps = self._viewports()
        return vps[0] * vps[1] if vps is not None else self._desktops_raw()

    def desktop_info(self):
        """Everything --workspaces shows: count, current, names, grid, viewports."""
        from ..workspaces import Desktops

        count = self._desktops_raw() or 0
        names_prop = self.root.get_full_property(self._atom("_NET_DESKTOP_NAMES"), self._X.AnyPropertyType)
        names: list[str] = []
        if names_prop is not None:
            raw = names_prop.value
            if isinstance(raw, str):
                raw = raw.encode()
            names = [n.decode(errors="replace") for n in bytes(raw).split(b"\0")]
        geo = self.d.screen()
        return Desktops(count, self._current_raw(), names,
                        self._cardinals(self.root, "_NET_DESKTOP_LAYOUT"),
                        self._cardinals(self.root, "_NET_DESKTOP_GEOMETRY"),
                        (geo.width_in_pixels, geo.height_in_pixels), self._viewport())

    def _viewport(self) -> Optional[tuple[int, int]]:
        vals = self._cardinals(self.root, "_NET_DESKTOP_VIEWPORT")
        if not vals or len(vals) < 2:
            return None
        i = 2 * (self._current_raw() or 0)
        return (vals[i], vals[i + 1]) if len(vals) >= i + 2 else (vals[0], vals[1])

    def _window_viewport(self, win, vps: tuple) -> int:
        """The viewport a window's centre is in (window positions are relative to the current one)."""
        geo = win.get_geometry()
        pos = self.root.translate_coords(win, 0, 0)
        return self._cell(vps, vps[4] + pos.x + geo.width // 2, vps[5] + pos.y + geo.height // 2)

    def workspace_offset(self, desktop: int) -> tuple[int, int]:
        """How far workspace `desktop` is from the current one, in root coordinates.

        (0, 0) for EWMH desktops, which all use the same coordinates.
        """
        vps = self._viewports()
        if vps is None:
            return 0, 0
        cols, rows, w, h, x, y = vps
        here = self._cell(vps, x, y)
        return (desktop % cols - here % cols) * w, (desktop // cols - here // cols) * h

    def move_to_desktop(self, window_id: int, desktop: int) -> None:
        """Move a window to an EWMH desktop. With viewports this does nothing:
        the window is placed at the viewport's offset instead."""
        from Xlib import error

        if self._viewports() is not None:
            return
        try:
            self._send(self._window(window_id), "_NET_WM_DESKTOP", [desktop, 1, 0, 0, 0])
        except error.XError as exc:
            raise BackendError(f"window {window_id:#x} could not be moved to another "
                               f"workspace: {exc}") from exc

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

    def _drop_increments(self, win) -> None:
        """Remove the resize increments, so the size is not rounded to character cells."""
        h = win.get_wm_normal_hints()
        if h is not None and h.flags & 64:       # PResizeInc
            h.flags &= ~64
            win.set_wm_normal_hints(h)
            self.d.flush()

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

    def _set_decorations(self, win, on: bool) -> bool:
        """Ask the window manager to draw (or not draw) the title bar and border.

        Returns True when the frame extents changed as a result. Uses the Motif
        hints, which most window managers honor.
        """
        before = self._frame_extents(win)
        atom = self._atom("_MOTIF_WM_HINTS")
        win.change_property(atom, atom, 32, [2, 0, 1 if on else 0, 0, 0])   # flag: decorations
        self.d.flush()
        deadline = time.monotonic() + 0.8
        while time.monotonic() < deadline:
            time.sleep(0.05)
            if self._frame_extents(win) != before:
                return True
        return False

    def place(self, window_id: int, target: Rect, snap: str,
              decorations: bool = True) -> Placement:
        from Xlib import error

        try:
            win = self._window(window_id)
            notes: list[str] = []
            if not decorations and not self._set_decorations(win, False):
                notes.append("the window manager did not remove the window decorations")
            frame, gtk = self._frame_extents(win), self._gtk_extents(win)
            if snap == "pixel":
                self._drop_increments(win)
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
            return Placement(target, p.visible, actual, p.cols, p.rows, notes + list(p.notes))
        except error.XError as exc:
            raise BackendError(f"window {window_id:#x} went away or refused: {exc}") from exc
