"""Test doubles for the window backend."""

from tilepane.backends import Placement, WindowInfo
from tilepane.placement import Extents, SizeHints


class FakeBackend:
    """A backend that 'opens' windows without an X server.

    Every pane that is started makes a new window appear (unless appear is
    False). Placement succeeds with a cell size of 10x20 and a 30 px title bar.
    """

    name = "fake"

    def __init__(self, appear=True, wm_class=("tilepane", "tilepane")):
        self.appear = appear
        self.wm_class = wm_class
        self._next = 1
        self._open: set[int] = set()
        self.placed: list[tuple[int, object, str]] = []
        self.closed: list[int] = []
        self.disconnected = False

    def windows(self):
        # Each call before a launch reports the current set; a window "appears"
        # when wait_new_window is called after a launch.
        return set(self._open)

    def wait_new_window(self, before, match, timeout):
        if not self.appear:
            return None
        wid = self._next
        self._next += 1
        self._open.add(wid)
        info = WindowInfo(wid, self.wm_class, 100, "t")
        return info if match(info) else None

    def place(self, window_id, target, snap):
        self.placed.append((window_id, target, snap))
        return Placement(target, target, target, 10, 20)

    def metrics(self, window_id):
        return Extents(0, 0, 30, 0), Extents(), SizeHints(14, 2, 10, 22, 54, 46)

    def find(self, wm_class):
        return []

    def close(self, window_id):
        self.closed.append(window_id)

    def disconnect(self):
        self.disconnected = True
