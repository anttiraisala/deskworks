import unittest

from deskmap import workarea
from deskmap.rect import Rect
from deskmap.monitors import Monitor, number_monitors
from deskmap.workarea import Strut

# The four-monitor setup of the dev machine, in deskmap numbering.
MONS = number_monitors([
    Monitor(0, "eDP-1", 4480, 1200, 2048, 1152, True),
    Monitor(0, "DP-1-1-5", 1920, 0, 2560, 1440),
    Monitor(0, "DP-1-1-6", 0, 240, 1920, 1200),
    Monitor(0, "DP-1-2", 4480, 0, 1920, 1200),
])
# _GTK_WORKAREAS_D0 as reported by Compiz/Unity there (a 65 px launcher and a
# 30 px top bar on every monitor), in the order the window manager lists them.
GTK = [4545, 1230, 1983, 1122, 1985, 30, 2495, 1410, 65, 270, 1855, 1170, 4545, 30, 1855, 1170]


class GtkWorkareasTest(unittest.TestCase):
    def test_each_monitor_gets_its_own_rectangle(self):
        got = {m.name: workarea.from_gtk_workareas(GTK, m) for m in MONS}
        self.assertEqual(got["DP-1-1-6"], Rect(65, 270, 1855, 1170))
        self.assertEqual(got["DP-1-1-5"], Rect(1985, 30, 2495, 1410))
        self.assertEqual(got["DP-1-2"], Rect(4545, 30, 1855, 1170))
        self.assertEqual(got["eDP-1"], Rect(4545, 1230, 1983, 1122))

    def test_rectangle_is_clipped_to_the_monitor(self):
        m = Monitor(0, "A", 0, 0, 1000, 500)
        self.assertEqual(workarea.from_gtk_workareas([10, 20, 5000, 5000], m), Rect(10, 20, 990, 480))

    def test_no_rectangle_on_this_monitor(self):
        m = Monitor(0, "A", 9000, 0, 100, 100)
        self.assertIsNone(workarea.from_gtk_workareas(GTK, m))

    def test_trailing_values_are_ignored(self):
        self.assertIsNotNone(workarea.from_gtk_workareas(GTK + [1, 2], MONS[0]))


class StrutTest(unittest.TestCase):
    SCREEN = (6528, 2352)

    def test_top_panel_across_the_whole_width(self):
        s = workarea.strut_from_property([0, 0, 30, 0, 0, 0, 0, 0, 0, 6527, 0, 0], self.SCREEN)
        top = workarea.from_struts(MONS[2], [s], self.SCREEN)
        self.assertEqual(top, Rect(4480, 30, 1920, 1170))    # DP-1-2 touches y=0
        self.assertEqual(workarea.from_struts(MONS[0], [s], self.SCREEN), Rect(0, 240, 1920, 1200))

    def test_left_launcher_only_affects_the_leftmost_monitor(self):
        s = workarea.strut_from_property([65, 0, 0, 0, 0, 2351, 0, 0, 0, 0, 0, 0], self.SCREEN)
        self.assertEqual(workarea.from_struts(MONS[0], [s], self.SCREEN), Rect(65, 240, 1855, 1200))
        self.assertEqual(workarea.from_struts(MONS[1], [s], self.SCREEN), Rect(1920, 0, 2560, 1440))

    def test_bottom_and_right(self):
        bottom = workarea.strut_from_property([0, 0, 0, 40, 0, 0, 0, 0, 0, 0, 0, 6527], self.SCREEN)
        right = workarea.strut_from_property([0, 50, 0, 0, 0, 0, 0, 2351, 0, 0, 0, 0], self.SCREEN)
        m = MONS[2]    # DP-1-2: x 4480-6400, y 0-1200; the screen edge is at 6528 and 2352
        self.assertEqual(workarea.from_struts(m, [bottom], self.SCREEN), m_rect(m))   # not at the bottom edge
        self.assertEqual(workarea.from_struts(MONS[1], [right], self.SCREEN), m_rect(MONS[1]))
        e = MONS[3]    # eDP-1: bottom at y=2352 and right edge x=6528
        self.assertEqual(workarea.from_struts(e, [bottom], self.SCREEN), Rect(4480, 1200, 2048, 1112))
        self.assertEqual(workarea.from_struts(e, [right], self.SCREEN), Rect(4480, 1200, 1998, 1152))

    def test_plain_strut_spans_the_whole_edge(self):
        s = workarea.strut_from_property([0, 0, 24, 0], self.SCREEN)
        self.assertEqual(s.top_range, (0, 6527))
        self.assertEqual(workarea.from_struts(MONS[1], [s], self.SCREEN), Rect(1920, 24, 2560, 1416))

    def test_zero_strut_is_ignored(self):
        self.assertIsNone(workarea.strut_from_property([0, 0, 0, 0], self.SCREEN))
        self.assertIsNone(workarea.strut_from_property([], self.SCREEN))

    def test_several_struts_combine(self):
        top = Strut(top=30, top_range=(0, 6527))
        left = Strut(left=65, left_range=(0, 2351))
        self.assertEqual(workarea.from_struts(MONS[0], [top, left], self.SCREEN), Rect(65, 240, 1855, 1200))
        self.assertEqual(workarea.from_struts(MONS[2], [top, left], self.SCREEN), Rect(4480, 30, 1920, 1170))

    def test_degenerate_result_falls_back_to_monitor(self):
        huge = Strut(top=5000, top_range=(0, 6527))
        self.assertEqual(workarea.from_struts(MONS[1], [huge], self.SCREEN), m_rect(MONS[1]))


def m_rect(m):
    return workarea.monitor_rect(m)


class HelpersTest(unittest.TestCase):
    def test_intersect(self):
        self.assertEqual(workarea.intersect(Rect(0, 0, 10, 10), Rect(5, 5, 10, 10)), Rect(5, 5, 5, 5))
        self.assertIsNone(workarea.intersect(Rect(0, 0, 10, 10), Rect(10, 0, 5, 5)))


if __name__ == "__main__":
    unittest.main()
