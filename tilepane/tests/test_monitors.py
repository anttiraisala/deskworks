import unittest

from tilepane import doctor


class RecommendTest(unittest.TestCase):
    def test_x11_with_xlib(self):
        rec = doctor.recommend("x11", ["unity"], "Compiz", set(), "0.33")
        self.assertEqual((rec.backend, rec.ready), ("x11-xlib", True))

    def test_x11_without_any_tool(self):
        rec = doctor.recommend("x11", [], "", set(), "")
        self.assertFalse(rec.ready)

    def test_x11_tiling_wm_note(self):
        rec = doctor.recommend("x11", [], "i3", set(), "0.33")
        self.assertTrue(any("floating" in n for n in rec.notes))

    def test_wayland_gnome_not_ready(self):
        rec = doctor.recommend("wayland", ["gnome"], "", set(), "")
        self.assertEqual((rec.backend, rec.ready), ("wayland-gnome-extension", False))

    def test_wayland_sway_ready_with_swaymsg(self):
        rec = doctor.recommend("wayland", ["sway"], "", {"swaymsg"}, "")
        self.assertTrue(rec.ready)

    def test_no_session(self):
        self.assertEqual(doctor.recommend("unknown", [], "", set(), "").backend, "none")


if __name__ == "__main__":
    unittest.main()
