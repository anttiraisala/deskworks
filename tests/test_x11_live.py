"""Opens real windows. Skipped unless TILEPANE_LIVE=1 (set TILEPANE_MONITOR to pick the monitor).

    TILEPANE_LIVE=1 TILEPANE_MONITOR=3 PYTHONPATH=src:. python3 -m unittest tests.test_x11_live -v
"""

import os
import time
import unittest

from tilepane import config, geometry, monitors, opener, terminals, workarea
from tilepane.backends import x11

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

    def test_gnome_terminal(self):
        self.check("gnome-terminal")

    def test_xterm(self):
        self.check("xterm")


if __name__ == "__main__":
    unittest.main()
