import json
import unittest

from deskmap import monitors

# Real output from a four-monitor X11 setup; xrandr's own order differs from
# the left-to-right numbering.
XRANDR = """Monitors: 4
 0: +*eDP-1 2048/344x1152/215+4480+1200  eDP-1
 1: +DP-1-1-5 2560/597x1440/336+1920+0  DP-1-1-5
 2: +DP-1-1-6 1920/518x1200/324+0+240  DP-1-1-6
 3: +DP-1-2 1920/518x1200/324+4480+0  DP-1-2
"""


class MonitorParsingTest(unittest.TestCase):
    def test_xrandr_numbered_by_position(self):
        result = monitors.parse_xrandr_listmonitors(XRANDR)
        self.assertEqual(
            [(m.number, m.name) for m in result],
            [(0, "DP-1-1-6"), (1, "DP-1-1-5"), (2, "DP-1-2"), (3, "eDP-1")],
        )

    def test_same_x_ordered_by_y(self):
        result = monitors.parse_xrandr_listmonitors(XRANDR)
        self.assertEqual(result[2].y, 0)
        self.assertEqual(result[3].y, 1200)

    def test_geometry_and_primary(self):
        edp = monitors.parse_xrandr_listmonitors(XRANDR)[3]
        self.assertEqual((edp.x, edp.y, edp.width, edp.height), (4480, 1200, 2048, 1152))
        self.assertTrue(edp.primary)

    def test_negative_offsets(self):
        text = " 0: +HDMI-1 1920/500x1080/300-1920+0  HDMI-1\n"
        m = monitors.parse_xrandr_listmonitors(text)[0]
        self.assertEqual((m.x, m.y), (-1920, 0))

    def test_sway(self):
        text = json.dumps([
            {"name": "B", "active": True, "rect": {"x": 1920, "y": 0, "width": 2560, "height": 1440}},
            {"name": "A", "active": True, "rect": {"x": 0, "y": 0, "width": 1920, "height": 1080}},
            {"name": "off", "active": False, "rect": {"x": 0, "y": 0, "width": 1, "height": 1}},
        ])
        self.assertEqual([m.name for m in monitors.parse_sway_outputs(text)], ["A", "B"])

    def test_hyprland_scale(self):
        text = json.dumps([{"name": "eDP-1", "x": 0, "y": 0, "width": 2880,
                            "height": 1800, "scale": 2.0, "focused": True}])
        m = monitors.parse_hyprland_monitors(text)[0]
        self.assertEqual((m.width, m.height), (1440, 900))
