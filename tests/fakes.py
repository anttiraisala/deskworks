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

    def place(self, window_id, target, snap, decorations=True):
        self.placed.append((window_id, target, snap))
        self.decorations = decorations
        return Placement(target, target, target, 10, 20)

    def metrics(self, window_id):
        return Extents(0, 0, 30, 0), Extents(), SizeHints(14, 2, 10, 22, 54, 46)

    def find(self, wm_class):
        return [WindowInfo(w, self.wm_class, 100, "t") for w in sorted(self._open)
                if self.wm_class[1] == wm_class]

    def close(self, window_id):
        self.closed.append(window_id)
        self._open.discard(window_id)

    def vanish(self, window_id):
        """The user closed this window by hand."""
        self._open.discard(window_id)

    def disconnect(self):
        self.disconnected = True


def fake_terminals_on_path(test, names=("xterm",)):
    """Put stub terminal binaries first on PATH for the duration of a test.

    Tests that open windows through a fake backend still resolve the terminal
    with shutil.which; this keeps them independent of what the machine has.
    """
    import os
    import tempfile

    tmp = tempfile.TemporaryDirectory()
    test.addCleanup(tmp.cleanup)
    for name in names:
        path = os.path.join(tmp.name, name)
        with open(path, "w") as fh:
            fh.write("#!/bin/sh\nexit 0\n")
        os.chmod(path, 0o755)
    old = os.environ.get("PATH", "")
    os.environ["PATH"] = tmp.name + os.pathsep + old
    test.addCleanup(os.environ.__setitem__, "PATH", old)
