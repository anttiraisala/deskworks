import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.fakes import FakeBackend
from tilepane import opener, placement, runner, terminals
from tilepane.geometry import LeafRect, Rect
from tilepane.placement import Extents, PlacementError, SizeHints, plan

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


class TerminalsTest(unittest.TestCase):
    def req(self, **kw):
        return terminals.LaunchRequest(title="T", argv=["python", "run.py", "{}"], **kw)

    def test_gnome_terminal_command(self):
        cmd = terminals.GnomeTerminal().command(
            self.req(geometry=terminals.Geometry(80, 24, 100, 200)))
        self.assertEqual(cmd, ["gnome-terminal", "--class=tilepane", "--title=T",
                               "--geometry=80x24+100+200", "--", "python", "run.py", "{}"])

    def test_xterm_command_without_geometry(self):
        cmd = terminals.Xterm().command(self.req())
        self.assertEqual(cmd, ["xterm", "-class", "tilepane", "-name", "tilepane", "-T", "T",
                               "-e", "python", "run.py", "{}"])

    def test_negative_position_uses_plus_minus(self):
        cmd = terminals.Xterm().command(self.req(geometry=terminals.Geometry(80, 24, -100, 5)))
        self.assertIn("80x24+-100+5", cmd)

    def test_custom_template(self):
        term = terminals.CustomTerminal(
            ["foot", "--title", "{title}", "--window-size-chars={cols}x{rows}", "--", "{command}"])
        cmd = term.command(self.req(geometry=terminals.Geometry(80, 24, 1, 2)))
        self.assertEqual(cmd, ["foot", "--title", "T", "--window-size-chars=80x24", "--",
                               "python", "run.py", "{}"])
        self.assertTrue(term.matches(("any", "thing")))

    def test_matches_class(self):
        self.assertTrue(terminals.Xterm().matches(("x", "tilepane")))
        self.assertFalse(terminals.Xterm().matches(("x", "Firefox")))

    def test_auto_picks_first_available_in_order(self):
        only_xterm = lambda b: "/usr/bin/xterm" if b == "xterm" else None
        self.assertEqual(terminals.resolve("auto", which=only_xterm).name, "xterm")
        both = lambda b: "/bin/" + b
        self.assertEqual(terminals.resolve("auto", which=both).name, "gnome-terminal")

    def test_auto_with_nothing_installed(self):
        with self.assertRaises(terminals.TerminalError):
            terminals.resolve("auto", which=lambda b: None)

    def test_named_terminal_errors(self):
        with self.assertRaises(terminals.TerminalError) as cm:
            terminals.resolve("kitty", which=lambda b: "/x")
        self.assertIn("not supported yet", str(cm.exception))
        with self.assertRaises(terminals.TerminalError) as cm:
            terminals.resolve("xterm", which=lambda b: None)
        self.assertIn("not installed", str(cm.exception))

    def test_custom_dict(self):
        self.assertEqual(terminals.resolve({"cmd": ["foot", "{command}"]}).name, "foot")


class RunnerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = os.path.join(self.tmp.name, "log")
        self.execs = []
        self.out = io.StringIO()

    def go(self, **spec):
        return runner.run(spec, execvp=lambda *a: self.execs.append(a),
                          sleep=lambda s: self.sleeps.append(s), out=self.out)

    sleeps: list

    def run_spec(self, **spec):
        self.sleeps = []
        return self.go(**spec)

    def lines(self):
        return Path(self.log).read_text().split() if os.path.exists(self.log) else []

    def test_sequence_runs_in_order_then_shell(self):
        self.run_spec(commands=[f"echo a >> {self.log}", f"echo b >> {self.log}"])
        self.assertEqual(self.lines(), ["a", "b"])
        self.assertEqual(len(self.execs), 1)
        self.assertIn("finished with exit status 0", self.out.getvalue())

    def test_continues_after_failure_by_default(self):
        self.run_spec(commands=["false", f"echo b >> {self.log}"])
        self.assertEqual(self.lines(), ["b"])

    def test_stop_on_error(self):
        self.run_spec(commands=["false", f"echo b >> {self.log}"], stop_on_error=True)
        self.assertEqual(self.lines(), [])
        self.assertIn("exit status 1", self.out.getvalue())

    def test_close_returns_status_without_shell(self):
        self.assertEqual(self.run_spec(commands=["exit 3"], on_exit="close"), 3)
        self.assertEqual(self.execs, [])

    def test_restart_honors_max_restarts_and_delay(self):
        self.run_spec(commands=[f"echo x >> {self.log}"], on_exit="restart",
                      restart_delay=2, max_restarts=2)
        self.assertEqual(len(self.lines()), 3)      # first run + 2 restarts
        self.assertEqual(self.sleeps, [2.0, 2.0])
        self.assertEqual(len(self.execs), 1)
        self.assertIn("reached max_restarts", self.out.getvalue())

    def test_no_commands_goes_straight_to_shell(self):
        self.run_spec(commands=[])
        self.assertEqual(len(self.execs), 1)
        self.assertNotIn("finished", self.out.getvalue())

    def test_cwd_and_env(self):
        old = os.getcwd()
        try:
            self.run_spec(commands=[f"pwd > {self.log}; echo $GREETING >> {self.log}"],
                          cwd=self.tmp.name, env={"GREETING": "hi $HOME"})
        finally:
            os.chdir(old)
        pwd, greeting = Path(self.log).read_text().split("\n")[:2]
        self.assertEqual(os.path.realpath(pwd), os.path.realpath(self.tmp.name))
        self.assertEqual(greeting, f"hi {os.path.expanduser('~')}")

    def test_missing_cwd_is_reported_and_commands_skipped(self):
        self.run_spec(commands=[f"echo x >> {self.log}"], cwd="/nonexistent/dir")
        self.assertEqual(self.lines(), [])
        self.assertIn("cannot use working directory", self.out.getvalue())
        self.assertEqual(len(self.execs), 1)

    def test_title_escape(self):
        self.run_spec(commands=[], title="my title")
        self.assertIn("\033]0;my title\007", self.out.getvalue())

    def test_runs_as_a_script(self):
        spec = json.dumps({"commands": ["exit 4"], "on_exit": "close"})
        proc = subprocess.run([sys.executable, str(Path(runner.__file__)), spec])
        self.assertEqual(proc.returncode, 4)

    def test_bad_spec(self):
        self.assertEqual(runner.main(["not json"]), 2)
        self.assertEqual(runner.main([]), 2)

    def test_ctrl_c_still_reaches_children(self):
        # The runner must install a handler, not SIG_IGN, or children would inherit "ignore".
        import signal
        self.run_spec(commands=["true"], on_exit="close")
        self.assertTrue(callable(signal.getsignal(signal.SIGINT)))
        signal.signal(signal.SIGINT, signal.default_int_handler)


def leaf_rect(id_, rect, **leaf):
    base = {"id": id_, "snap": "cell", "terminal": "auto", "on_exit": "keep"}
    base.update(leaf)
    return LeafRect(id_, rect, rect, base)


class OpenerTest(unittest.TestCase):
    def make(self, backend=None, term=None):
        self.backend = backend or FakeBackend()
        self.started = []
        self.term = term or terminals.Xterm()
        return opener.Opener(self.backend, popen=lambda cmd, **kw: self.started.append((cmd, kw)),
                             resolve_terminal=lambda setting: self.term, timeout=0.1)

    def test_opens_and_places_each_pane(self):
        op = self.make()
        leaves = [leaf_rect("0", Rect(0, 0, 500, 500), run="htop"),
                  leaf_rect("1", Rect(500, 0, 500, 500), run=["a", "b"], title="two")]
        results = op.open_layout(leaves)
        self.assertTrue(all(r.ok for r in results))
        self.assertEqual([p[1] for p in self.backend.placed], [Rect(0, 0, 500, 500), Rect(500, 0, 500, 500)])
        self.assertEqual(len(self.started), 2)
        cmd, kw = self.started[1]
        self.assertTrue(kw["start_new_session"])
        self.assertIn("two", cmd)
        spec = json.loads(cmd[-1])
        self.assertEqual(spec["commands"], ["a", "b"])
        self.assertEqual(spec["on_exit"], "keep")

    def test_runner_is_started_as_a_script_with_this_python(self):
        op = self.make()
        op.open_layout([leaf_rect("0", Rect(0, 0, 500, 500), run="htop")])
        cmd = self.started[0][0]
        self.assertEqual(cmd[cmd.index("-e") + 1], sys.executable)
        self.assertTrue(cmd[cmd.index("-e") + 2].endswith("runner.py"))

    def test_empty_panes_open_nothing(self):
        op = self.make()
        results = op.open_layout([leaf_rect("0", Rect(0, 0, 500, 500), empty=True)])
        self.assertEqual((results, self.started), ([], []))

    def test_timeout_is_a_failure_and_next_pane_still_opens(self):
        backend = FakeBackend(appear=False)
        op = self.make(backend)
        results = op.open_layout([leaf_rect("0", Rect(0, 0, 500, 500)),
                                  leaf_rect("1", Rect(500, 0, 500, 500))])
        self.assertEqual([r.ok for r in results], [False, False])
        self.assertIn("no xterm window appeared", results[0].error)
        self.assertEqual(len(self.started), 2)

    def test_terminal_error_is_reported(self):
        def boom(setting):
            raise terminals.TerminalError("no supported terminal found")
        op = opener.Opener(FakeBackend(), popen=lambda *a, **k: None, resolve_terminal=boom)
        results = op.open_layout([leaf_rect("0", Rect(0, 0, 500, 500))])
        self.assertFalse(results[0].ok)
        self.assertIn("no supported terminal", results[0].error)

    def test_start_failure(self):
        def broken(cmd, **kw):
            raise FileNotFoundError("xterm")
        op = opener.Opener(FakeBackend(), popen=broken, resolve_terminal=lambda s: terminals.Xterm())
        self.assertIn("cannot start xterm", op.open_layout([leaf_rect("0", Rect(0, 0, 9, 9))])[0].error)

    def test_later_windows_get_exact_geometry_from_learned_metrics(self):
        op = self.make(term=terminals.GnomeTerminal())
        op.open_layout([leaf_rect("0", Rect(0, 0, 500, 500)),
                        leaf_rect("1", Rect(500, 0, 700, 432))])
        first, second = self.started[0][0], self.started[1][0]
        self.assertFalse(any(a.startswith("--geometry") for a in first))
        geo = [a for a in second if a.startswith("--geometry")][0]
        self.assertEqual(geo, "--geometry=68x18+500+0")

    def test_unsupported_settings_warn(self):
        op = self.make()
        r = op.open_layout([leaf_rect("0", Rect(0, 0, 500, 500), decorations=False,
                                      font_size=12, mode="cycle")])[0]
        text = " ".join(r.warnings)
        self.assertIn("decorations", text)
        self.assertIn("font_size", text)
        self.assertIn("mode 'cycle'", text)

    def test_default_decorations_do_not_warn(self):
        op = self.make()
        r = op.open_layout([leaf_rect("0", Rect(0, 0, 500, 500), decorations=True)])[0]
        self.assertEqual(r.warnings, [])

    def test_class_mismatch_means_no_window(self):
        backend = FakeBackend(wm_class=("x", "Firefox"))
        op = self.make(backend)
        self.assertFalse(op.open_layout([leaf_rect("0", Rect(0, 0, 500, 500))])[0].ok)

    def test_titles(self):
        self.assertEqual(opener.default_title({"title": "T", "run": "x"}), "T")
        self.assertEqual(opener.default_title({"run": ["htop", "x"]}), "htop")
        self.assertEqual(opener.default_title({}), "tilepane")

    def test_runner_spec(self):
        spec = opener.runner_spec({"run": "htop", "cwd": "~", "env": {"A": "1"},
                                   "on_exit": "restart", "restart_delay": 3})
        self.assertEqual(spec["commands"], ["htop"])
        self.assertEqual((spec["cwd"], spec["env"], spec["on_exit"], spec["restart_delay"]),
                         ("~", {"A": "1"}, "restart", 3))
        self.assertEqual(opener.runner_spec({})["commands"], [])


if __name__ == "__main__":
    unittest.main()
