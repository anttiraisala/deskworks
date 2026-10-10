import io
import json
import os
import random
import subprocess
import tempfile
import unittest

from tests.fakes import FakeBackend, fake_terminals_on_path
from tilepane import cli, config, demo, geometry, monitors
from tilepane.geometry import Rect
from tilepane.state import StateStore

MONS = monitors.number_monitors([
    monitors.Monitor(0, "DP-1", 0, 0, 1920, 1080),
    monitors.Monitor(0, "HDMI-1", 1920, 0, 2560, 1440),
])


def nothing(_name):
    return None


def everything(name):
    return "/usr/bin/" + name


class BuildTest(unittest.TestCase):
    def test_random_layouts_are_valid_and_tile_the_area(self):
        for seed in range(300):
            for w, h in ((1920, 1080), (1280, 720), (1080, 1920), (3840, 2160)):
                rng = random.Random(seed)
                panes = rng.choice([None, 1, 2, 6, 9, 12])
                lay = demo.build(rng, w, h, panes=panes, seed=seed, which=everything)
                cfg = config.load_text(json.dumps(lay), "demo", strict=True)
                leaves = geometry.compute(config.resolve_layout(cfg, cfg.layouts[0]),
                                          Rect(0, 0, w, h))
                if panes:
                    self.assertEqual(len(leaves), panes)
                else:
                    self.assertIn(len(leaves), demo.DEFAULT_COUNTS)
                for lr in leaves:
                    self.assertGreaterEqual(lr.outer.width, demo.MIN_W - 1)
                    self.assertGreaterEqual(lr.outer.height, demo.MIN_H - 1)
                self.assertTrue(4 <= lay["margin"] <= 16)
                self.assertEqual(lay["on_exit"], "keep")

    def test_same_seed_same_layout(self):
        a = demo.build(random.Random("x"), 1920, 1080, which=everything)
        b = demo.build(random.Random("x"), 1920, 1080, which=everything)
        self.assertEqual(a, b)
        c = demo.build(random.Random("y"), 1920, 1080, which=everything)
        self.assertNotEqual(a, c)

    def test_split_points_stay_between_20_and_80_percent(self):
        def walk(node, w, h):
            if "dir" not in node:
                return
            size = w if node["dir"] == "columns" else h
            cut = demo._at_pixels(node["at"], size)
            self.assertTrue(0.19 * size <= cut <= 0.81 * size, (node["at"], size))

        for seed in range(200):
            lay = demo.build(random.Random(seed), 1920, 1080, panes=3, which=everything)
            walk(lay["split"], 1920, 1080)

    def test_too_many_panes(self):
        with self.assertRaises(demo.DemoError):
            demo.build(random.Random(1), 1920, 1080, panes=13)
        with self.assertRaises(demo.DemoError):
            demo.build(random.Random(1), 400, 200, panes=6)

    def test_panes_differ_while_the_pool_lasts(self):
        leaves = demo.pick_panes(random.Random(3), 6, everything)
        self.assertEqual(len({leaf["run"] for leaf in leaves}), 6)
        # With nothing installed the fallbacks repeat only after all are used.
        leaves = demo.pick_panes(random.Random(3), 12, nothing)
        distinct = {e.fallback[1] for e in demo.POOL}
        self.assertEqual(len({leaf["run"] for leaf in leaves[:len(distinct)]}), len(distinct))

    def test_missing_command_uses_fallback(self):
        entry = next(e for e in demo.POOL if e.title == "htop")
        self.assertEqual(demo.pane(entry, everything), {"run": "htop", "title": "htop"})
        leaf = demo.pane(entry, nothing)
        self.assertTrue(leaf["run"].startswith("sh -c "))
        self.assertEqual(leaf["title"], entry.fallback[0])

    def test_streaming_command_is_guarded(self):
        entry = next(e for e in demo.POOL if e.title == "kernel log")
        run = demo.pane(entry, everything)["run"]
        self.assertIn("dmesg -w", run)
        self.assertIn("not available here", run)

    def test_guard_falls_back_when_the_command_exits_at_once(self):
        entry = demo.Entry("broken", "false", ("false",), ("echo", "echo fallback ran; exit 0"),
                           streams=True)
        run = demo.pane(entry, everything)["run"]
        proc = subprocess.run(run, shell=True, capture_output=True, text=True, timeout=5)
        self.assertIn("fallback ran", proc.stdout)

    def test_fallbacks_are_valid_sh(self):
        for title, script in {e.fallback for e in demo.POOL}:
            with self.subTest(title=title):
                proc = subprocess.run(["sh", "-n", "-c", script], capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_parse_duration(self):
        self.assertEqual(demo.parse_duration("30s"), 30)
        self.assertEqual(demo.parse_duration("2m"), 120)
        self.assertEqual(demo.parse_duration("1h"), 3600)
        self.assertEqual(demo.parse_duration("1.5"), 1.5)
        for bad in ("", "0", "-1s", "5d", "soon"):
            with self.subTest(bad=bad), self.assertRaises(demo.DemoError):
                demo.parse_duration(bad)


class CliDemoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.backend = FakeBackend()
        self.store = StateStore(os.path.join(self.tmp.name, "state"))
        self.started = []
        fake_terminals_on_path(self)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        code = cli.main(list(argv), out=out, err=err, detected=MONS, backend=self.backend,
                        popen=lambda cmd, **kw: self.started.append(cmd), store=self.store)
        return code, out.getvalue(), err.getvalue()

    def test_dry_run_is_reproducible_and_opens_nothing(self):
        code, out1, err = self.run_cli("--demo", "4", "--dry-run", "--seed", "42")
        self.assertEqual(code, 0, err)
        self.assertIn("demo: seed 42 (repeat it with --seed 42)", out1)
        self.assertIn('layout "demo"  (--demo --seed 42)  monitor 0 DP-1', out1)
        self.assertEqual(self.started, [])
        _, out2, _ = self.run_cli("--demo", "4", "--dry-run", "--seed", "42")
        self.assertEqual(out1, out2)

    def test_seed_is_printed_when_random(self):
        code, out, _ = self.run_cli("--demo", "--dry-run")
        self.assertEqual(code, 0)
        self.assertRegex(out, r"demo: seed \d+ \(repeat it with --seed \d+\)")

    def test_opens_windows_on_the_chosen_monitor(self):
        code, out, err = self.run_cli("--demo", "3", "--monitor", "1", "--seed", "1")
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.started), 3)
        self.assertIn("3 opened", out)
        self.assertTrue(all(p[1].x >= 1920 for p in self.backend.placed))

    def test_new_demo_replaces_the_previous_one(self):
        self.run_cli("--demo", "3", "--seed", "1")
        first = set(self.backend._open)
        code, out, err = self.run_cli("--demo", "4", "--seed", "2")
        self.assertEqual(code, 0, err)
        self.assertEqual(set(self.backend.closed), first)
        self.assertEqual(len(self.backend._open), 4)

    def test_demo_on_another_monitor_is_kept(self):
        self.run_cli("--demo", "3", "--monitor", "0", "--seed", "1")
        self.run_cli("--demo", "3", "--monitor", "1", "--seed", "1")
        self.assertEqual(self.backend.closed, [])
        self.assertEqual(len(self.backend._open), 6)

    def test_close_all_closes_demo(self):
        self.run_cli("--demo", "3", "--seed", "1")
        code, out, _ = self.run_cli("--close", "all")
        self.assertIn("closed 3 window(s)", out)

    def test_save_writes_an_editable_layout(self):
        path = os.path.join(self.tmp.name, "demo.json")
        code, out, err = self.run_cli("--demo", "3", "--seed", "5", "--save", path, "--dry-run")
        self.assertEqual(code, 0, err)
        cfg = config.load_file(path, strict=True)
        self.assertEqual(cfg.names(), ["demo"])
        self.assertIn("--seed 5", cfg.layouts[0]["description"])
        # The saved file opens as an ordinary layout with the same rectangles.
        _, again, _ = self.run_cli("--dry-run", path)
        rows = [line.split()[:5] for line in out.splitlines() if line.startswith("  ")]
        rows2 = [line.split()[:5] for line in again.splitlines() if line.startswith("  ")]
        self.assertEqual(rows, rows2)

    def test_saved_demo_reopens_without_duplicates(self):
        path = os.path.join(self.tmp.name, "demo.json")
        self.run_cli("--demo", "3", "--seed", "5", "--save", path)
        code, out, err = self.run_cli(path)
        self.assertEqual(code, 0, err)
        self.assertIn("0 opened, 3 re-placed", out)

    def test_all_monitors_get_one_layout_each(self):
        path = os.path.join(self.tmp.name, "demo.json")
        code, out, err = self.run_cli("--demo", "2", "--monitor", "all", "--save", path, "--dry-run")
        self.assertEqual(code, 0, err)
        self.assertEqual(config.load_file(path).names(), ["demo-0", "demo-1"])

    def test_save_error(self):
        code, _, err = self.run_cli("--demo", "--save", "/nonexistent/dir/d.json", "--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("--save", err)

    def test_too_many_panes_for_the_monitor(self):
        code, _, err = self.run_cli("--demo", "13", "--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("1 to 12 panes", err)

    def test_unknown_monitor(self):
        code, _, err = self.run_cli("--demo", "--monitor", "7", "--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("--demo", err)

    def test_for_reaches_the_runner(self):
        self.run_cli("--demo", "1", "--seed", "1", "--for", "30s")
        spec = json.loads(self.started[0][-1])
        self.assertEqual(spec["lifetime"], 30.0)


if __name__ == "__main__":
    unittest.main()
