"""Opens real windows. Skipped unless TILEPANE_LIVE=1 (set TILEPANE_MONITOR to pick the monitor).

    TILEPANE_LIVE=1 TILEPANE_MONITOR=3 PYTHONPATH=src:.:../deskmap/src python3 -m unittest tests.test_x11_live -v
"""

import os
import time
import unittest

from deskmap import monitors, workarea
from tilepane import config, geometry, opener, terminals
from deskmap.backends import x11

LIVE = os.environ.get("TILEPANE_LIVE") == "1" and x11.available()[0]


@unittest.skipUnless(LIVE, "set TILEPANE_LIVE=1 on an X11 session to open real windows")
class LiveTest(unittest.TestCase):
    def setUp(self):
        self.backend = x11.X11Backend()
        found, _, _ = monitors.detect()
        self.mon = found[int(os.environ.get("TILEPANE_MONITOR", "0"))]
        self.area = workarea.detect(found)[0][self.mon.number]
        self.opened = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for wid in self.opened:
            self.backend.close(wid)
        time.sleep(1.0)
        self.backend.disconnect()

    def open_layout(self, term_name, layout):
        cfg = config.load_text(__import__("json").dumps(layout), "live")
        resolved = config.resolve_layout(cfg, cfg.layouts[0])
        leaves = geometry.compute(resolved, self.area)
        op = opener.Opener(self.backend, resolve_terminal=lambda s: terminals.IMPLEMENTED[term_name])
        results = op.open_layout(leaves)
        self.opened += [r.window_id for r in results if r.window_id]
        return leaves, results

    def check(self, term_name):
        if not terminals.IMPLEMENTED[term_name].available():
            self.skipTest(f"{term_name} is not installed")
        layout = {"name": "live", "margin": 8, "outer_margin": 16, "split": {
            "dir": "columns", "at": "50%",
            "a": {"run": "sleep 30", "title": "live-a"},
            "b": {"dir": "rows", "a": {"run": "sleep 30"}, "b": {"run": "sleep 30"}}}}
        leaves, results = self.open_layout(term_name, layout)
        self.assertEqual([r.ok for r in results], [True, True, True], [r.error for r in results])
        for lr, r in zip(leaves, results):
            p = r.placement
            self.assertTrue(p.exact, f"{r.id}: planned {p.planned}, got {p.actual}")
            # the visible window is the pane rectangle rounded down to whole cells
            self.assertEqual((p.actual.x, p.actual.y), (lr.rect.x, lr.rect.y))
            self.assertLessEqual(p.actual.width, lr.rect.width)
            self.assertLessEqual(p.actual.height, lr.rect.height)
            self.assertLess(lr.rect.width - p.actual.width, 40)
            self.assertLess(lr.rect.height - p.actual.height, 40)

    def check_exact(self, term_name, **extra):
        if not terminals.IMPLEMENTED[term_name].available():
            self.skipTest(f"{term_name} is not installed")
        layout = {"name": "live", "margin": 8, "snap": "pixel", "split": {
            "dir": "columns", "at": "50%",
            "a": {"run": "sleep 30", **extra}, "b": {"run": "sleep 30", **extra}}}
        leaves, results = self.open_layout(term_name, layout)
        self.assertEqual([r.ok for r in results], [True, True], [r.error for r in results])
        for lr, r in zip(leaves, results):
            self.assertEqual(r.placement.actual, lr.rect, f"{r.id}: {r.placement.notes}")

    def test_pixel_snap_is_exact(self):
        self.check_exact("gnome-terminal")
        self.check_exact("xterm")

    def test_undecorated_windows_fill_the_rectangle(self):
        self.check_exact("gnome-terminal", decorations=False)
        self.check_exact("xterm", decorations=False)

    def test_reopen_replaces_and_close_removes(self):
        from tilepane import manager, state
        import tempfile
        if not terminals.IMPLEMENTED["xterm"].available():
            self.skipTest("xterm is not installed")
        layout = {"name": "live", "margin": 8, "split": {
            "dir": "columns", "a": {"run": "sleep 30", "id": "a"}, "b": {"run": "sleep 30", "id": "b"}}}
        cfg = config.load_text(__import__("json").dumps(layout), "live")
        leaves = geometry.compute(config.resolve_layout(cfg, cfg.layouts[0]), self.area)
        with tempfile.TemporaryDirectory() as d:
            op = opener.Opener(self.backend, resolve_terminal=lambda s: terminals.IMPLEMENTED["xterm"])
            mgr = manager.Manager(self.backend, state.StateStore(d), op)
            key = ("/live.json", "live", self.mon.name)
            first = mgr.open_unit(key, leaves)
            self.opened += [r.window_id for r in first.results]
            second = mgr.open_unit(key, leaves)
            self.assertEqual((first.opened, second.opened, second.replaced), (2, 0, 2))
            self.assertEqual(len(self.backend.find("tilepane")), 2)
            self.assertEqual(mgr.close(source="/live.json"), 2)
            time.sleep(1.0)
            self.assertEqual(self.backend.find("tilepane"), [])

    def test_analyze_reads_the_windows_back(self):
        """The windows tilepane opened are listed with their rectangles, and --analyze makes their layout again."""
        from tilepane import analyze, processes
        if not terminals.IMPLEMENTED["xterm"].available():
            self.skipTest("xterm is not installed")
        layout = {"name": "live", "margin": 8, "snap": "pixel", "split": {
            "dir": "columns", "at": "50%", "a": {"run": "sleep 30", "title": "live-a"},
            "b": {"dir": "rows", "a": {"run": "sleep 31"}, "b": {"run": "sleep 32"}}}}
        leaves, results = self.open_layout("xterm", layout)
        mine = {r.window_id: r for r in results}
        listed = [w for w in self.backend.open_windows() if w.id in mine]
        self.assertEqual(len(listed), 3)
        for w in listed:
            self.assertEqual(w.rect, mine[w.id].placement.actual)
            self.assertEqual((w.kind, w.hidden), ("normal", False))
        items = [analyze.Item(w.rect, analyze.pane_for(w.wm_class, w.title, w.pid, processes.terminal_pane), i)
                 for i, w in enumerate(listed)]
        result = analyze.derive(self.area, items)
        self.assertEqual((result.windows, result.empty), (3, 0))
        self.assertLessEqual(result.deviation, 1)
        runs = sorted(lf.leaf["run"] for lf in geometry.compute(result.layout, self.area))
        self.assertEqual(runs, ["sleep 30", "sleep 31", "sleep 32"])

    def test_gnome_terminal(self):
        self.check("gnome-terminal")

    def test_xterm(self):
        self.check("xterm")


if __name__ == "__main__":
    unittest.main()
