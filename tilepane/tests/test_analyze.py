"""--analyze: the layout that the open windows of a monitor make."""

import io
import json
import os
import random
import tempfile
import unittest

from deskmap.backends import OpenWindow
from deskmap.monitors import Monitor
from deskmap.rect import Rect

from tests.fakes import FakeBackend
from tilepane import analyze, cli, geometry, processes
from tilepane.invocation import UsageError, parse

AREA = Rect(65, 30, 1855, 1170)


def items_of(layout, area=AREA):
    return [analyze.Item(lf.rect, {"run": lf.leaf.get("run", "x")}, i)
            for i, lf in enumerate(geometry.compute(layout, area)) if lf.leaf]


def rects(layout, area=AREA):
    return sorted((lf.rect.x, lf.rect.y, lf.rect.width, lf.rect.height)
                  for lf in geometry.compute(layout, area) if lf.leaf != {})


class DeriveTest(unittest.TestCase):
    def roundtrip(self, layout, area=AREA):
        result = analyze.derive(area, items_of(layout, area))
        self.assertEqual(result.deviation, 0, result.layout)
        self.assertEqual(rects(result.layout, area), rects(layout, area))
        return result

    def test_two_columns_with_a_margin_come_back_exactly(self):
        result = self.roundtrip({"margin": 10, "split": {"dir": "columns", "at": "60%",
                                 "a": {"run": "a"}, "b": {"dir": "rows", "at": "40%", "a": {"run": "b"}, "b": {"run": "c"}}}})
        self.assertEqual((result.margin, result.outer_margin, result.windows, result.empty), (10, None, 3, 0))

    def test_odd_margins_and_pixel_splits(self):
        self.roundtrip({"margin": 7, "split": {"dir": "rows", "at": "300px", "a": {"run": "a"},
                        "b": {"dir": "columns", "at": "-400px", "a": {"run": "b"}, "b": {"run": "c"}}}})

    def test_an_outer_margin_is_found(self):
        result = self.roundtrip({"margin": 8, "outer_margin": 20, "split": {"dir": "columns", "a": {"run": "a"}, "b": {"run": "b"}}})
        self.assertEqual(result.outer_margin, 20)

    def test_no_margin_at_all(self):
        result = self.roundtrip({"split": {"dir": "columns", "at": "33%", "a": {"run": "a"},
                                "b": {"dir": "rows", "a": {"run": "b"}, "b": {"run": "c"}}}})
        self.assertEqual(result.margin, 0)

    def test_random_layouts_come_back_exactly(self):
        rng = random.Random(7)

        def tree(depth):
            if depth == 0 or rng.random() < 0.25:
                return {"run": f"w{rng.randint(0, 99)}"}
            return {"dir": rng.choice(["columns", "rows"]), "at": f"{rng.randint(25, 75)}%",
                    "a": tree(depth - 1), "b": tree(depth - 1)}
        for _ in range(60):
            layout = {"margin": rng.choice([0, 6, 8, 11]), "split": tree(4)}
            if layout["split"].get("run"):
                continue
            leaves = geometry.compute(layout, AREA)
            if any(min(lf.rect.width, lf.rect.height) < 60 for lf in leaves):
                continue
            result = analyze.derive(AREA, items_of(layout))
            self.assertEqual(result.deviation, 0, (layout, result.layout))
            self.assertEqual(rects(result.layout), rects(layout), layout)

    def test_gaps_of_a_few_pixels_are_noise(self):
        # Terminals are placed at whole character cells, so the gaps differ by a few pixels.
        wins = [Rect(75, 40, 895, 1140), Rect(985, 40, 925, 1150)]
        result = analyze.derive(AREA, [analyze.Item(r, {"run": str(i)}, i) for i, r in enumerate(wins)])
        self.assertEqual((result.windows, result.empty), (2, 0))
        self.assertLessEqual(result.deviation, 10)

    def test_a_single_window_keeps_its_place_with_empty_panes_around_it(self):
        result = analyze.derive(AREA, [analyze.Item(Rect(300, 200, 800, 500), {"run": "only"}, 0)])
        self.assertEqual((result.windows, result.deviation), (1, 0))
        self.assertGreaterEqual(result.empty, 1)
        self.assertEqual(rects(result.layout), [(300, 200, 800, 500)])

    def test_a_hole_in_the_screen_becomes_an_empty_pane(self):
        wins = [Rect(65, 30, 900, 500), Rect(965, 30, 955, 1170), Rect(65, 700, 900, 500)]
        result = analyze.derive(AREA, [analyze.Item(r, {"run": str(i)}, i) for i, r in enumerate(wins)])
        self.assertEqual((result.windows, result.empty), (3, 1))
        self.assertEqual(result.deviation, 0)

    def test_overlapping_windows_all_stay_and_the_panes_do_not_overlap(self):
        wins = [Rect(145 + 120 * i, 70 + 40 * i, 900, 600) for i in range(5)]      # a cascade
        result = analyze.derive(AREA, [analyze.Item(r, {"run": f"w{i}"}, i) for i, r in enumerate(wins)])
        self.assertEqual(result.windows, 5)
        panes = [lf.rect for lf in geometry.compute(result.layout, AREA) if lf.leaf != {}]
        for i, a in enumerate(panes):
            for b in panes[i + 1:]:
                self.assertFalse(min(a.right, b.right) > max(a.x, b.x) and min(a.bottom, b.bottom) > max(a.y, b.y), (a, b))
        self.assertGreater(result.deviation, 1)
        self.assertTrue(any("differ" in n for n in result.notes))
        self.assertEqual(sorted(lf.leaf["run"] for lf in geometry.compute(result.layout, AREA) if lf.leaf.get("run")),
                         [f"w{i}" for i in range(5)])

    def test_windows_exactly_on_top_of_each_other_are_put_side_by_side(self):
        result = analyze.derive(AREA, [analyze.Item(Rect(100, 100, 800, 600), {"run": f"w{i}"}, i) for i in range(3)])
        self.assertEqual(result.windows, 3)
        self.assertTrue(any("on top of each other" in n for n in result.notes))

    def test_the_topmost_of_windows_on_top_of_each_other_comes_first(self):
        result = analyze.derive(AREA, [analyze.Item(Rect(100, 100, 800, 600), {"run": f"w{i}"}, i) for i in range(2)])
        leaves = sorted((lf for lf in geometry.compute(result.layout, AREA) if lf.leaf.get("run")),
                        key=lambda lf: (lf.rect.x, lf.rect.y))
        self.assertEqual(leaves[0].leaf["run"], "w1")

    def test_the_layout_is_a_valid_tilepane_layout(self):
        from tilepane import config
        result = analyze.derive(AREA, [analyze.Item(Rect(300, 200, 800, 500), {"run": "only"}, 0),
                                       analyze.Item(Rect(1200, 400, 500, 500), {"empty": False, "title": "Firefox"}, 1)])
        text = json.dumps({"version": 1, **result.layout})
        config.load_text(text, "analyzed.json", strict=True)

    def test_margins_of_overlapping_windows_are_not_guessed(self):
        result = analyze.derive(AREA, [analyze.Item(Rect(100, 100, 800, 600), {"run": "a"}, 0),
                                       analyze.Item(Rect(300, 200, 800, 600), {"run": "b"}, 1)])
        self.assertEqual((result.margin, result.outer_margin), (0, None))


class PaneForTest(unittest.TestCase):
    def test_a_terminal_gets_its_command(self):
        pane = analyze.pane_for(("xterm", "XTerm"), "t", 5, lambda pid: {"run": "htop", "cwd": "~"})
        self.assertEqual(pane, {"run": "htop", "cwd": "~"})

    def test_a_terminal_without_a_known_command_is_an_interactive_shell(self):
        self.assertEqual(analyze.pane_for(("xterm", "XTerm"), "t", 5, lambda pid: None), {"empty": False})

    def test_a_terminal_shared_by_several_windows_is_not_asked(self):
        asked = []
        pane = analyze.pane_for(("gnome-terminal-server", "Gnome-terminal"), "t", 5,
                                lambda pid: asked.append(pid) or {"run": "x"}, shared=True)
        self.assertEqual((pane, asked), ({"empty": False}, []))

    def test_other_windows_are_kept_as_a_titled_shell(self):
        pane = analyze.pane_for(("Navigator", "Firefox"), "Mozilla  Firefox", 5, lambda pid: None)
        self.assertEqual(pane, {"empty": False, "title": "Firefox: Mozilla Firefox"})
        self.assertEqual(analyze.pane_for(("calc", "Calc"), "Calc", 5, lambda pid: None)["title"], "Calc")


class ProcessesTest(unittest.TestCase):
    def tree(self, procs):
        """procs: pid -> (ppid, argv, cwd)"""
        root = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(root, True))
        for pid, (ppid, argv, cwd) in procs.items():
            d = os.path.join(root, str(pid))
            os.makedirs(d)
            with open(os.path.join(d, "stat"), "w") as fh:
                fh.write(f"{pid} (name with ) paren) S {ppid} 1 1 0\n")
            with open(os.path.join(d, "cmdline"), "wb") as fh:
                fh.write(b"\0".join(a.encode() for a in argv) + b"\0")
            if cwd:
                os.symlink(cwd, os.path.join(d, "cwd"))
        return root

    def test_the_deepest_process_that_is_not_a_shell(self):
        root = self.tree({100: (1, ["xterm"], None), 101: (100, ["-bash"], "/home/me"),
                          102: (101, ["htop", "-d", "5"], "/home/me/work dir")})
        self.assertEqual(processes.terminal_pane(100, proc=root, home="/home/me"),
                         {"run": "htop -d 5", "cwd": "~/work dir"})

    def test_a_terminal_that_runs_only_a_shell(self):
        root = self.tree({100: (1, ["xterm"], None), 101: (100, ["bash"], "/home/me")})
        self.assertIsNone(processes.terminal_pane(100, proc=root))

    def test_a_window_that_tilepane_opened_gives_its_own_settings(self):
        spec = json.dumps({"commands": ["date", "whoami"], "cwd": "/srv", "title": "t", "on_exit": "keep", "env": {}})
        root = self.tree({100: (1, ["xterm"], None),
                          101: (100, ["python3", "/x/tilepane/runner.py", spec], None),
                          102: (101, ["sh", "-c", "whoami"], None), 103: (102, ["whoami"], None)})
        self.assertEqual(processes.terminal_pane(100, proc=root),
                         {"run": ["date", "whoami"], "cwd": "/srv", "title": "t", "on_exit": "keep"})

    def test_unknown_process_and_missing_proc(self):
        self.assertIsNone(processes.terminal_pane(None))
        self.assertIsNone(processes.terminal_pane(4242, proc="/nonexistent-proc"))


class ParseTest(unittest.TestCase):
    def test_analyze_takes_a_file_and_edit(self):
        inv = parse(["--analyze", "mine.json", "--edit", "--monitor", "1", "--workspace", "all", "--terminals-only", "--yes"])
        self.assertEqual((inv.action, inv.edit_after, inv.workspace, inv.terminals_only, inv.yes),
                         ("analyze", True, "all", True, True))
        self.assertEqual((inv.tasks[0].source, inv.tasks[0].monitor), ("mine.json", "1"))

    def test_analyze_alone(self):
        inv = parse(["--analyze"])
        self.assertEqual((inv.action, inv.edit_after, inv.tasks), ("analyze", False, []))

    def test_analyze_cannot_be_mixed_with_other_actions_or_layout_names(self):
        for argv in (["--analyze", "--demo"], ["--analyze", "--close"], ["--analyze", "a.json", "b.json"],
                     ["--analyze", "a.json", "name"]):
            with self.assertRaises(UsageError, msg=argv):
                parse(argv)

    def test_terminals_only_needs_analyze(self):
        with self.assertRaises(UsageError):
            parse(["--terminals-only", "x.json"])


MONS = [Monitor(0, "L", 0, 0, 1000, 800, False), Monitor(1, "R", 1000, 0, 1000, 800, True)]
AREAS = {0: Rect(0, 0, 1000, 800), 1: Rect(1000, 0, 1000, 800)}


def win(wid, x, y, w, h, *, cls=("xterm", "XTerm"), desktop=0, title="t", kind="normal", hidden=False, pid=None):
    return OpenWindow(wid, cls, pid or wid, title, desktop, Rect(x, y, w, h), kind, hidden, False)


class CommandTest(unittest.TestCase):
    def run_cli(self, argv, windows, *, active=None, pointer=None, desktop=0):
        backend = FakeBackend(desktop=desktop)
        backend.shown = windows
        backend.active = active
        backend.pointer_at = pointer
        out, err = io.StringIO(), io.StringIO()
        code = cli.main(argv, out=out, err=err, detected=MONS, backend=backend, work_areas=AREAS)
        return code, out.getvalue(), err.getvalue()

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, True))
        self.path = os.path.join(self.dir, "mine.json")
        self.windows = [win(1, 0, 0, 500, 800), win(2, 500, 0, 500, 400), win(3, 500, 400, 500, 400),
                        win(4, 1000, 0, 1000, 800, cls=("Navigator", "Firefox"), title="Mozilla"),
                        win(5, 100, 100, 100, 100, kind="other"), win(6, 0, 0, 300, 300, hidden=True),
                        win(7, 0, 0, 300, 300, desktop=2)]

    def test_the_monitor_of_the_active_window_is_analysed(self):
        code, out, err = self.run_cli(["--analyze", self.path], self.windows, active=1)
        self.assertEqual(code, 0, err)
        data = json.load(open(self.path))
        self.assertEqual(data["version"], 1)
        self.assertIn("$schema", data)
        leaves = geometry.compute(data, AREAS[0])
        self.assertEqual(sorted((lf.rect.x, lf.rect.y, lf.rect.width, lf.rect.height) for lf in leaves),
                         [(0, 0, 500, 800), (500, 0, 500, 400), (500, 400, 500, 400)])
        self.assertIn("3 window(s) -> 3 pane(s)", out)
        self.assertIn("matches the screen", out)
        self.assertIn("tilepane", out)
        self.assertIn("--monitor 0", out)

    def test_the_pointer_decides_when_there_is_no_active_window(self):
        code, out, err = self.run_cli(["--analyze", self.path], self.windows, active=None, pointer=(1500, 400))
        self.assertEqual(code, 0, err)
        data = json.load(open(self.path))
        self.assertEqual(data["split"]["title"], "Firefox: Mozilla")
        self.assertEqual(data["split"]["empty"], False)

    def test_monitor_option_chooses_the_monitor_and_hidden_and_other_windows_are_left_out(self):
        code, out, err = self.run_cli(["--analyze", self.path, "--monitor", "0"], self.windows, active=4)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.count("pane(s)"), 1)
        self.assertIn("3 window(s)", out)

    def test_terminals_only(self):
        code, out, err = self.run_cli(["--analyze", self.path, "--monitor", "1", "--terminals-only"],
                                      self.windows, active=1)
        self.assertEqual(code, 1)
        self.assertIn("no windows", out + err)
        self.assertFalse(os.path.exists(self.path))

    def test_every_monitor_gives_a_layout_in_one_file(self):
        code, out, err = self.run_cli(["--analyze", self.path, "--monitor", "all"], self.windows, active=1)
        self.assertEqual(code, 0, err)
        data = json.load(open(self.path))
        self.assertEqual([lay["name"] for lay in data["layouts"]], ["analyzed-monitor-0", "analyzed-monitor-1"])
        from tilepane import config
        config.load_text(json.dumps(data), "x.json", strict=True)

    def test_workspaces_give_layouts_that_remember_their_workspace(self):
        code, out, err = self.run_cli(["--analyze", self.path, "--monitor", "0", "--workspace", "all"],
                                      self.windows, active=1)
        self.assertEqual(code, 0, err)
        data = json.load(open(self.path))
        names = {lay["name"]: lay.get("workspace") for lay in data["layouts"]}
        self.assertEqual(len(names), 2)         # workspace 0 and workspace 2 (the only ones with windows)
        self.assertTrue(all(isinstance(v, int) for v in names.values()))

    def test_a_given_workspace_is_written_to_the_layout(self):
        code, out, err = self.run_cli(["--analyze", self.path, "--monitor", "0", "--workspace", "0"],
                                      self.windows, active=1)
        self.assertEqual(code, 0, err)
        self.assertIn("workspace", json.load(open(self.path)))

    def test_an_existing_file_is_not_replaced_without_yes(self):
        with open(self.path, "w") as fh:
            fh.write("keep me")
        code, out, err = self.run_cli(["--analyze", self.path], self.windows, active=1)
        self.assertEqual(code, 1)
        self.assertIn("--yes", err)
        self.assertEqual(open(self.path).read(), "keep me")
        code, out, err = self.run_cli(["--analyze", self.path, "--yes"], self.windows, active=1)
        self.assertEqual(code, 0, err)
        self.assertNotEqual(open(self.path).read(), "keep me")

    def test_dry_run_prints_the_layout_and_writes_nothing(self):
        code, out, err = self.run_cli(["--analyze", self.path, "--dry-run"], self.windows, active=1)
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["version"], 1)
        self.assertIn("3 window(s)", err)
        self.assertFalse(os.path.exists(self.path))

    def test_edit_opens_the_editor_on_the_new_file(self):
        opened = []
        orig = cli._Runner.edit
        cli._Runner.edit = lambda self, open_browser=None: opened.append(self.inv.tasks[0].source) or 0
        self.addCleanup(lambda: setattr(cli._Runner, "edit", orig))
        code, out, err = self.run_cli(["--analyze", self.path, "--edit"], self.windows, active=1)
        self.assertEqual(code, 0, err)
        self.assertEqual(opened, [self.path])
        self.assertTrue(os.path.exists(self.path))

    def test_no_windows_is_an_error(self):
        code, out, err = self.run_cli(["--analyze", self.path], [], active=None, pointer=(10, 10))
        self.assertEqual(code, 1)
        self.assertIn("no windows", out + err)
        self.assertFalse(os.path.exists(self.path))


if __name__ == "__main__":
    unittest.main()
