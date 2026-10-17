import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.fakes import FakeBackend
from tilepane import opener, runner, terminals
from tilepane.geometry import LeafRect, Rect

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

    def fake_shell(self):
        """A $SHELL that runs -lc commands and otherwise 'stays open' for a while."""
        path = os.path.join(self.tmp.name, "shell")
        Path(path).write_text('#!/bin/sh\nif [ "$1" = -lc ]; then exec /bin/sh -c "$2"; fi\n'
                              f'echo shell >> {self.log}; exec sleep 5\n')
        os.chmod(path, 0o755)
        old = os.environ.get("SHELL")
        os.environ["SHELL"] = path
        self.addCleanup(lambda: os.environ.__setitem__("SHELL", old) if old is not None
                        else os.environ.pop("SHELL", None))

    def stop(self, proc):
        # Tests must not signal their own process group.
        proc.terminate()
        proc.wait()

    def test_lifetime_stops_a_running_command(self):
        self.fake_shell()
        self.sleeps = []
        start = time.monotonic()
        code = runner.run({"commands": ["sleep 5", f"echo late >> {self.log}"], "lifetime": 0.3},
                          execvp=lambda *a: self.execs.append(a), out=self.out, stop=self.stop)
        self.assertEqual(code, 0)
        self.assertLess(time.monotonic() - start, 3)
        self.assertEqual(self.lines(), [])
        self.assertEqual(self.execs, [])

    def test_lifetime_also_ends_the_shell_after_the_commands(self):
        self.fake_shell()
        start = time.monotonic()
        runner.run({"commands": [f"echo a >> {self.log}"], "lifetime": 0.5},
                   execvp=lambda *a: self.execs.append(a), out=self.out, stop=self.stop)
        self.assertLess(time.monotonic() - start, 3)
        self.assertEqual(self.lines(), ["a", "shell"])
        self.assertEqual(self.execs, [])

    def test_lifetime_ends_restart_loop(self):
        self.fake_shell()
        sleeps = []
        runner.run({"commands": ["true"], "on_exit": "restart", "restart_delay": 10,
                    "lifetime": 1}, execvp=lambda *a: self.execs.append(a), out=self.out,
                   sleep=sleeps.append, stop=self.stop)
        self.assertEqual(sleeps, [])
        self.assertEqual(self.execs, [])

    def test_shell_from_spec_runs_commands_and_the_prompt(self):
        self.fake_shell()
        shell = os.environ["SHELL"]
        os.environ["SHELL"] = "/bin/false"      # must not be used
        self.run_spec(commands=[f'echo "$SHELL" >> {self.log}'], shell=shell, env={"X": "1"})
        self.assertEqual(self.lines(), [shell])
        file, args, env = self.execs[0]
        self.assertEqual((file, args, env["SHELL"], env["X"]), (shell, [shell], shell, "1"))

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
        self.assertNotIn("decorations", text)     # handled by the backend, not the terminal
        self.assertFalse(self.backend.decorations)
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

    def test_resolve_shell(self):
        found = {"zsh": "/usr/bin/zsh"}.get
        self.assertEqual(opener.resolve_shell("auto", env={"SHELL": "/bin/bash"}), "/bin/bash")
        self.assertEqual(opener.resolve_shell(None, env={}), "/bin/sh")
        self.assertEqual(opener.resolve_shell("zsh", which=found), "/usr/bin/zsh")
        self.assertEqual(opener.resolve_shell("/bin/sh"), "/bin/sh")
        with self.assertRaisesRegex(opener.ShellError, "not installed"):
            opener.resolve_shell("fish", which=found)
        with self.assertRaisesRegex(opener.ShellError, "not an executable"):
            opener.resolve_shell("/nonexistent/zsh")

    def test_pane_with_missing_shell_fails_alone(self):
        from tests.fakes import FakeBackend
        op = opener.Opener(FakeBackend(), popen=lambda *a, **k: None,
                           resolve_terminal=lambda s: terminals.Xterm(), timeout=0.1)
        bad = op.open_pane(LeafRect("0", Rect(0, 0, 9, 9), Rect(0, 0, 9, 9), {"shell": "nosuchshell"}))
        self.assertFalse(bad.ok)
        self.assertIn("shell 'nosuchshell' is not installed", bad.error)

    def test_shell_reaches_the_runner(self):
        from tests.fakes import FakeBackend
        started = []
        op = opener.Opener(FakeBackend(), popen=lambda cmd, **k: started.append(cmd),
                           resolve_terminal=lambda s: terminals.Xterm(), timeout=0.1)
        op.open_pane(LeafRect("0", Rect(0, 0, 9, 9), Rect(0, 0, 9, 9), {"shell": "/bin/sh"}))
        self.assertEqual(json.loads(started[0][-1])["shell"], "/bin/sh")

    def test_runner_spec(self):
        spec = opener.runner_spec({"run": "htop", "cwd": "~", "env": {"A": "1"},
                                   "on_exit": "restart", "restart_delay": 3})
        self.assertEqual(spec["commands"], ["htop"])
        self.assertEqual((spec["cwd"], spec["env"], spec["on_exit"], spec["restart_delay"]),
                         ("~", {"A": "1"}, "restart", 3))
        self.assertEqual(opener.runner_spec({})["commands"], [])


if __name__ == "__main__":
    unittest.main()
