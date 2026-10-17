import unittest

from deskmap import placement
from deskmap.placement import Extents, PlacementError, SizeHints, plan
from deskmap.rect import Rect

# Numbers measured on the dev machine (Compiz, gnome-terminal 3.52):
# base 14x2, cell 10x22, title bar 32 px, no side or bottom border.
GT_HINTS = SizeHints(14, 2, 10, 22, 54, 46)
FRAME = Extents(0, 0, 32, 0)


class PlacementTest(unittest.TestCase):
    def test_cell_snap_rounds_down_and_keeps_top_left(self):
        p = plan(Rect(4700, 1350, 700, 432), FRAME, Extents(), GT_HINTS, "cell")
        self.assertEqual((p.x, p.y), (4700, 1350))
        self.assertEqual((p.width, p.height), (694, 398))       # 68 cols x 18 rows
        self.assertEqual((p.cols, p.rows), (68, 18))
        self.assertEqual(p.visible, Rect(4700, 1350, 694, 430))

    def test_exact_fit_is_not_reduced(self):
        p = plan(Rect(0, 0, 814, 562), FRAME, Extents(), GT_HINTS, "cell")
        self.assertEqual((p.cols, p.rows), (80, 24))
        self.assertEqual(p.visible, Rect(0, 0, 814, 562))

    def test_pixel_snap_keeps_exact_client_size(self):
        p = plan(Rect(0, 0, 700, 432), FRAME, Extents(), GT_HINTS, "pixel")
        self.assertEqual((p.width, p.height, p.cols), (700, 400, None))

    def test_no_hints_means_no_cell_snap_and_a_note(self):
        p = plan(Rect(0, 0, 700, 432), FRAME, Extents(), None, "cell")
        self.assertEqual((p.width, p.height), (700, 400))
        self.assertTrue(p.notes)

    def test_tiny_pane_is_clamped_to_minimum(self):
        p = plan(Rect(0, 0, 40, 60), FRAME, Extents(), GT_HINTS, "cell")
        self.assertTrue(p.clamped)
        self.assertGreaterEqual(p.width, GT_HINTS.min_w)
        self.assertTrue(p.notes)

    def test_target_smaller_than_frame_is_an_error(self):
        with self.assertRaises(PlacementError):
            plan(Rect(0, 0, 100, 20), FRAME, Extents(), GT_HINTS, "cell")

    def test_gtk_shadow_extends_the_client_and_moves_the_origin(self):
        gtk = Extents(10, 10, 5, 15)
        p = plan(Rect(100, 100, 500, 300), Extents(), gtk, None, "pixel")
        self.assertEqual((p.x, p.y, p.width, p.height), (90, 95, 520, 320))
        self.assertEqual(p.visible, Rect(100, 100, 500, 300))

    def test_visible_rect_inverts_plan(self):
        p = plan(Rect(300, 200, 700, 432), FRAME, Extents(), GT_HINTS, "cell")
        back = placement.visible_rect(p.x, p.y + FRAME.top, p.width, p.height, FRAME, Extents())
        self.assertEqual(back, p.visible)

    def test_hints_from_wm(self):
        h = placement.hints_from_wm(852, (14, 2), (10, 22), (54, 46))
        self.assertEqual(h, SizeHints(14, 2, 10, 22, 54, 46))
        self.assertIsNone(placement.hints_from_wm(0, (0, 0), (1, 1), (0, 0)))
        # no base size flag: the minimum size is the base
        h = placement.hints_from_wm(16 | 64, (0, 0), (6, 13), (10, 17))
        self.assertEqual((h.base_w, h.base_h), (10, 17))
