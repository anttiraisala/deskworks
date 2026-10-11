import io
import json
import os
import tempfile
import unittest

from tests.fakes import FakeBackend, fake_terminals_on_path
from tilepane import cli, manager, monitors, opener, state, terminals
from tilepane.geometry import LeafRect, Rect
from tilepane.state import Record, StateStore

MONS = monitors.number_monitors([
    monitors.Monitor(0, "DP-1", 0, 0, 1920, 1080),
    monitors.Monitor(0, "HDMI-1", 1920, 0, 1920, 1080),
])
LAYOUT = {"name": "two", "margin": 0, "split": {
    "dir": "columns", "a": {"run": "htop", "id": "left"}, "b": {"run": "top"}}}


def leaf(i, rect, **kw):
    return LeafRect(i, rect, rect, {"id": i, "snap": "cell", "terminal": "xterm", **kw})


class StateStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = StateStore(self.tmp.name)

    def test_empty_when_no_file(self):
        self.assertEqual(self.store.load(), [])

    def test_transaction_persists_changes(self):
        with self.store.transaction() as recs:
            recs.append(Record(5, "/a.json", "x", "DP-1", "0", pid=7))
        got = self.store.load()
        self.assertEqual([(r.xid, r.key, r.leaf, r.pid) for r in got],
                         [(5, ("/a.json", "x", "DP-1"), "0", 7)])

    def test_corrupt_file_is_treated_as_empty(self):
        os.makedirs(self.tmp.name, exist_ok=True)
        with open(self.store.path, "w") as fh:
            fh.write("{ not json")
        self.assertEqual(self.store.load(), [])

    def test_incompatible_records_are_dropped(self):
        with open(self.store.path, "w") as fh:
            json.dump({"windows": [{"xid": 1, "bogus": True},
                                   {"xid": 2, "source": "s", "layout": "l", "monitor": "m", "leaf": "0"}]}, fh)
        self.assertEqual([r.xid for r in self.store.load()], [2])

    def test_state_dir_follows_xdg(self):
        old = os.environ.get("XDG_STATE_HOME")
        os.environ["XDG_STATE_HOME"] = "/tmp/xs"
        try:
            self.assertEqual(state.state_dir(), "/tmp/xs/tilepane")
        finally:
            if old is None:
                del os.environ["XDG_STATE_HOME"]
            else:
                os.environ["XDG_STATE_HOME"] = old

    def test_no_temp_files_left_behind(self):
        with self.store.transaction() as recs:
            recs.append(Record(1, "s", "l", "m", "0"))
        self.assertEqual(sorted(os.listdir(self.tmp.name)), ["state.json", "state.lock"])


class ManagerTest(unittest.TestCase):
    KEY = ("/a.json", "two", "DP-1")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.backend = FakeBackend()
        self.store = StateStore(self.tmp.name)
        op = opener.Opener(self.backend, popen=lambda *a, **k: None,
                           resolve_terminal=lambda s: terminals.Xterm(), timeout=0.1)
        self.mgr = manager.Manager(self.backend, self.store, op)
        self.left, self.right = leaf("left", Rect(0, 0, 500, 500)), leaf("1", Rect(500, 0, 500, 500))

    def test_first_open_records_windows(self):
        rep = self.mgr.open_unit(self.KEY, [self.left, self.right])
        self.assertEqual((rep.opened, rep.replaced), (2, 0))
        recs = self.store.load()
        self.assertEqual([(r.leaf, r.key) for r in recs], [("left", self.KEY), ("1", self.KEY)])

    def test_second_open_replaces_instead_of_duplicating(self):
        self.mgr.open_unit(self.KEY, [self.left, self.right])
        moved = leaf("left", Rect(0, 0, 400, 400))
        rep = self.mgr.open_unit(self.KEY, [moved, self.right])
        self.assertEqual((rep.opened, rep.replaced), (0, 2))
        self.assertEqual(len(self.backend._open), 2)
        self.assertEqual(self.backend.placed[-2][1], Rect(0, 0, 400, 400))
        self.assertTrue(all(r.action == "replaced" for r in rep.results))

    def test_window_closed_by_hand_is_reopened(self):
        self.mgr.open_unit(self.KEY, [self.left, self.right])
        gone = self.store.load()[0].xid
        self.backend.vanish(gone)
        rep = self.mgr.open_unit(self.KEY, [self.left, self.right])
        self.assertEqual((rep.opened, rep.replaced), (1, 1))
        self.assertNotIn(gone, [r.xid for r in self.store.load()])

    def test_extra_windows_are_kept_without_prune(self):
        self.mgr.open_unit(self.KEY, [self.left, self.right])
        rep = self.mgr.open_unit(self.KEY, [self.left])
        self.assertEqual((rep.extra, rep.pruned), (["1"], 0))
        self.assertEqual(len(self.backend._open), 2)

    def test_prune_closes_extra_windows(self):
        self.mgr.open_unit(self.KEY, [self.left, self.right])
        rep = self.mgr.open_unit(self.KEY, [self.left], prune=True)
        self.assertEqual((rep.extra, rep.pruned), ([], 1))
        self.assertEqual(len(self.backend._open), 1)
        self.assertEqual([r.leaf for r in self.store.load()], ["left"])

    def test_other_keys_are_untouched(self):
        self.mgr.open_unit(self.KEY, [self.left])
        other = ("/a.json", "two", "HDMI-1")
        rep = self.mgr.open_unit(other, [self.left])
        self.assertEqual((rep.opened, rep.replaced), (1, 0))
        self.mgr.open_unit(self.KEY, [self.left], prune=True)
        self.assertEqual(len(self.store.load()), 2)

    def test_empty_panes_have_no_window(self):
        rep = self.mgr.open_unit(self.KEY, [leaf("x", Rect(0, 0, 9, 9), empty=True)])
        self.assertEqual((rep.opened, rep.results), (0, []))

    def test_failed_pane_is_not_recorded(self):
        self.backend.appear = False
        rep = self.mgr.open_unit(self.KEY, [self.left])
        self.assertEqual(len(rep.failed), 1)
        self.assertEqual(self.store.load(), [])

    def test_is_open_ignores_dead_windows(self):
        self.assertFalse(self.mgr.is_open(self.KEY))
        self.mgr.open_unit(self.KEY, [self.left])
        self.assertTrue(self.mgr.is_open(self.KEY))
        self.backend.vanish(self.store.load()[0].xid)
        self.assertFalse(self.mgr.is_open(self.KEY))
        self.assertEqual(self.store.load(), [])

    def test_close_by_selector(self):
        a, b, c = ("/a.json", "two", "DP-1"), ("/a.json", "two", "HDMI-1"), ("/b.json", "one", "DP-1")
        for key in (a, b, c):
            self.mgr.open_unit(key, [self.left])
        self.assertEqual(self.mgr.close(source="/a.json", layout="two", monitor="HDMI-1"), 1)
        self.assertEqual(self.mgr.close(source="/a.json"), 1)
        self.assertEqual(self.mgr.close(), 1)
        self.assertEqual((self.backend._open, self.store.load()), (set(), []))
        self.assertEqual(self.mgr.close(), 0)

    def test_workspaces_keep_their_own_windows(self):
        self.backend.desktop = 0
        self.mgr.open_unit(self.KEY, [self.left, self.right], workspace=0)
        self.backend.desktop = 1
        rep = self.mgr.open_unit(self.KEY, [self.left, self.right], workspace=1)
        self.assertEqual((rep.opened, rep.replaced), (2, 0))
        self.assertEqual(len(self.backend._open), 4)
        # Opening again on workspace 0 re-places that workspace's windows only.
        rep = self.mgr.open_unit(self.KEY, [self.left, self.right], workspace=0)
        self.assertEqual((rep.opened, rep.replaced), (0, 2))
        self.assertEqual(sorted(r.workspace for r in self.store.load()), [0, 0, 1, 1])

    def test_close_on_one_workspace(self):
        for ws in (0, 1):
            self.backend.desktop = ws
            self.mgr.open_unit(self.KEY, [self.left], workspace=ws)
        self.assertEqual(self.mgr.close(workspace=1), 1)
        self.assertEqual([r.workspace for r in self.store.load()], [0])
        self.assertEqual(self.mgr.close(workspace=None), 1)

    def test_is_open_per_workspace(self):
        self.backend.desktop = 0
        self.mgr.open_unit(self.KEY, [self.left], workspace=0)
        self.assertTrue(self.mgr.is_open(self.KEY, 0))
        self.assertFalse(self.mgr.is_open(self.KEY, 1))
        self.assertTrue(self.mgr.is_open(self.KEY, None))

    def test_window_moved_by_hand_follows_its_workspace(self):
        self.backend.desktop = 0
        self.mgr.open_unit(self.KEY, [self.left], workspace=0)
        xid = self.store.load()[0].xid
        self.backend.move_to_desktop(xid, 2)
        self.assertFalse(self.mgr.is_open(self.KEY, 0))
        self.assertEqual(self.store.load()[0].workspace, 2)

    def test_window_on_all_workspaces_matches_any(self):
        self.backend.desktop = 0
        self.mgr.open_unit(self.KEY, [self.left], workspace=0)
        self.backend.move_to_desktop(self.store.load()[0].xid, None)   # made sticky
        rep = self.mgr.open_unit(self.KEY, [self.left], workspace=3)
        self.assertEqual((rep.opened, rep.replaced), (0, 1))

    def test_opening_on_another_workspace_moves_new_windows(self):
        self.backend.desktop = 0
        self.mgr.open_unit(self.KEY, [self.left], workspace=2)
        xid = self.store.load()[0].xid
        self.assertEqual(self.backend.desktops[xid], 2)
        self.assertEqual(self.store.load()[0].workspace, 2)

    def test_no_workspaces_behaves_as_one(self):
        self.mgr.open_unit(self.KEY, [self.left], workspace=None)
        rep = self.mgr.open_unit(self.KEY, [self.left], workspace=None)
        self.assertEqual((rep.opened, rep.replaced), (0, 1))

    def test_window_that_ignores_close_is_asked_again_and_kept(self):
        self.mgr.close_timeout = 0.05
        self.mgr.open_unit(self.KEY, [self.left, self.right])
        stubborn = self.store.load()[0].xid
        self.backend.refuse.add(stubborn)
        self.assertEqual(self.mgr.close(), 1)
        self.assertEqual(self.mgr.refused, [stubborn])
        self.assertEqual(self.backend.closed.count(stubborn), 2)
        self.assertEqual([r.xid for r in self.store.load()], [stubborn])
        # The next close tries it again.
        self.backend.refuse.clear()
        self.assertEqual(self.mgr.close(), 1)
        self.assertEqual((self.mgr.refused, self.store.load()), ([], []))

    def test_source_path_is_absolute(self):
        self.assertEqual(manager.source_path("x.json", "/d.json"), os.path.abspath("x.json"))
        self.assertEqual(manager.source_path(None, "/d.json"), "/d.json")


class CliStateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "a.json")
        with open(self.path, "w") as fh:
            json.dump(LAYOUT, fh)
        self.backend = FakeBackend()
        self.store = StateStore(os.path.join(self.tmp.name, "state"))
        fake_terminals_on_path(self)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        code = cli.main(list(argv), out=out, err=err, detected=MONS, backend=self.backend,
                        popen=lambda *a, **k: None, store=self.store)
        return code, out.getvalue(), err.getvalue()

    def test_open_twice_does_not_duplicate(self):
        self.assertEqual(self.run_cli(self.path)[0], 0)
        code, out, err = self.run_cli(self.path)
        self.assertEqual(code, 0, err)
        self.assertIn("0 opened, 2 re-placed", out)
        self.assertEqual(len(self.backend._open), 2)

    def test_close_by_layout_name(self):
        self.run_cli(self.path)
        code, out, _ = self.run_cli("--close", self.path, "two")
        self.assertEqual(code, 0)
        self.assertIn("closed 2 window(s)", out)
        self.assertEqual(self.backend._open, set())

    def test_close_narrowed_by_monitor(self):
        self.run_cli(self.path, "--monitor", "0,1")
        self.assertEqual(len(self.backend._open), 4)
        code, out, _ = self.run_cli("--close", self.path, "two", "--monitor", "HDMI-1")
        self.assertIn("closed 2", out)
        self.assertEqual(len(self.backend._open), 2)
        self.assertEqual({r.monitor for r in self.store.load()}, {"DP-1"})

    def test_close_whole_file_without_layout_name(self):
        self.run_cli(self.path)
        code, out, _ = self.run_cli("--close", self.path)
        self.assertIn("closed 2", out)

    def test_close_when_nothing_is_open(self):
        code, out, _ = self.run_cli("--close", self.path, "two")
        self.assertEqual(code, 0)
        self.assertIn("nothing was open", out)

    def test_close_all(self):
        self.run_cli(self.path)
        code, out, _ = self.run_cli("--close", "all")
        self.assertIn("closed 2 window(s)", out)
        self.assertEqual(self.backend._open, set())

    def test_toggle_opens_then_closes(self):
        code, out, _ = self.run_cli("--toggle", self.path)
        self.assertIn("2 opened", out)
        self.assertEqual(len(self.backend._open), 2)
        code, out, _ = self.run_cli("--toggle", self.path)
        self.assertIn("closed 2 window(s)", out)
        self.assertEqual(self.backend._open, set())
        self.assertIn("2 opened", self.run_cli("--toggle", self.path)[1])

    def test_toggle_per_monitor(self):
        self.run_cli(self.path, "--monitor", "0")
        code, out, _ = self.run_cli("--toggle", self.path, "--monitor", "0,1")
        self.assertIn("monitor 0 DP-1 1920x1080+0+0: closed 2", out)
        self.assertIn("monitor 1 HDMI-1 1920x1080+1920+0: 2 opened", out)

    def test_prune_option(self):
        self.run_cli(self.path)
        with open(self.path, "w") as fh:
            json.dump(dict(LAYOUT, split={"run": "only", "id": "left"}), fh)
        code, out, _ = self.run_cli(self.path)
        self.assertIn("windows for panes that no longer exist: 1", out)
        code, out, _ = self.run_cli(self.path, "--prune")
        self.assertIn("1 pruned", out)
        self.assertEqual(len(self.backend._open), 1)

    def test_unknown_monitor_for_close(self):
        code, out, err = self.run_cli("--close", self.path, "--monitor", "9")
        self.assertEqual(code, 1)
        self.assertIn("no monitor 9", err)


if __name__ == "__main__":
    unittest.main()


class CliWorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "a.json")
        with open(self.path, "w") as fh:
            json.dump(LAYOUT, fh)
        self.backend = FakeBackend(desktop=0)
        self.store = StateStore(os.path.join(self.tmp.name, "state"))
        fake_terminals_on_path(self)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        code = cli.main(list(argv), out=out, err=err, detected=MONS, backend=self.backend,
                        popen=lambda *a, **k: None, store=self.store)
        return code, out.getvalue(), err.getvalue()

    def on(self, ws):
        self.backend.desktop = ws

    def test_reopen_on_another_workspace_keeps_the_old_windows(self):
        self.run_cli(self.path)
        self.on(1)
        code, out, err = self.run_cli(self.path)
        self.assertEqual(code, 0, err)
        self.assertIn("(workspace 2): 2 opened, 0 re-placed", out)
        self.assertEqual(self.backend.closed, [])
        self.assertEqual(len(self.backend._open), 4)

    def test_close_defaults_to_the_current_workspace(self):
        self.run_cli(self.path)
        self.on(1)
        self.run_cli(self.path)
        code, out, _ = self.run_cli("--close", "all")
        self.assertIn("closed 2 window(s) (workspace 2)", out)
        self.assertEqual(len(self.backend._open), 2)
        self.on(0)
        code, out, _ = self.run_cli("--close", self.path, "two")
        self.assertIn("closed 2 window(s)", out)
        self.assertEqual(self.backend._open, set())

    def test_close_on_all_or_a_given_workspace(self):
        self.run_cli(self.path)
        self.on(1)
        self.run_cli(self.path)
        self.on(2)
        _, out, _ = self.run_cli("--close", "all", "--workspace", "1")
        self.assertIn("closed 2 window(s) (workspace 1)", out)
        self.run_cli(self.path)
        _, out, _ = self.run_cli("--close", "all", "--workspace", "all")
        self.assertIn("closed 4 window(s)", out)
        self.assertEqual(self.backend._open, set())

    def test_toggle_is_per_workspace(self):
        self.run_cli("--toggle", self.path)
        self.on(1)
        _, out, _ = self.run_cli("--toggle", self.path)
        self.assertIn("2 opened", out)
        _, out, _ = self.run_cli("--toggle", self.path)
        self.assertIn("(workspace 2): closed 2", out)
        self.assertEqual(len(self.backend._open), 2)

    def test_open_on_a_given_workspace(self):
        code, out, err = self.run_cli(self.path, "--workspace", "3")
        self.assertEqual(code, 0, err)
        self.assertIn("(workspace 3)", out)
        self.assertEqual(set(self.backend.desktops.values()), {2})

    def test_demo_replaces_only_on_the_same_workspace(self):
        self.run_cli("--demo", "2", "--seed", "1")
        self.on(1)
        self.run_cli("--demo", "2", "--seed", "1")
        self.assertEqual(self.backend.closed, [])
        self.run_cli("--demo", "3", "--seed", "2")
        self.assertEqual(len(self.backend.closed), 2)
        self.assertEqual(len(self.backend._open), 5)

    def test_close_reports_windows_that_stay_open(self):
        manager.Manager.close_timeout, old = 0.05, manager.Manager.close_timeout
        self.addCleanup(setattr, manager.Manager, "close_timeout", old)
        self.run_cli(self.path)
        self.backend.refuse.add(min(self.backend._open))
        code, out, err = self.run_cli("--close", "all")
        self.assertEqual(code, 1)
        self.assertIn("closed 1 window(s)", out)
        self.assertIn("1 window(s) did not close", err)

    def test_layout_with_only_empty_panes_opens_nothing(self):
        path = os.path.join(self.tmp.name, "nothing.json")
        with open(path, "w") as fh:
            json.dump({"name": "nothing", "split": {"dir": "columns"}}, fh)
        code, out, err = self.run_cli(path)
        self.assertEqual(code, 0, err)
        self.assertIn("0 opened, 0 re-placed", out)
        self.assertEqual(self.backend._open, set())

    def write_layout(self, **extra):
        path = os.path.join(self.tmp.name, "ws.json")
        with open(path, "w") as fh:
            json.dump({**LAYOUT, **extra}, fh)
        return path

    def test_layout_workspace_opens_there(self):
        path = self.write_layout(workspace=3)
        code, out, err = self.run_cli(path)
        self.assertEqual(code, 0, err)
        self.assertIn("(workspace 3): 2 opened", out)
        self.assertEqual(set(self.backend.desktops.values()), {2})

    def test_command_line_workspace_overrides_the_layout(self):
        path = self.write_layout(workspace=3)
        code, out, err = self.run_cli(path, "--workspace", "2")
        self.assertIn("(workspace 2): 2 opened", out)
        self.assertEqual(set(self.backend.desktops.values()), {1})
        self.on(1)
        _, out, _ = self.run_cli(path, "--workspace", "current")
        self.assertIn("(workspace 2): 0 opened, 2 re-placed", out)

    def test_defaults_workspace_applies_to_every_layout(self):
        path = os.path.join(self.tmp.name, "d.json")
        with open(path, "w") as fh:
            json.dump({"defaults": {"workspace": 4}, "layouts": [LAYOUT]}, fh)
        self.run_cli(path)
        self.assertEqual(set(self.backend.desktops.values()), {3})

    def test_close_and_toggle_use_the_layout_workspace(self):
        path = self.write_layout(workspace=3)
        self.run_cli(path)
        self.on(1)
        code, out, _ = self.run_cli("--close", path)
        self.assertIn("(workspace 3): closed 2 window(s)", out)
        self.assertEqual(self.backend._open, set())
        _, out, _ = self.run_cli("--toggle", path)
        self.assertIn("(workspace 3): 2 opened", out)
        _, out, _ = self.run_cli("--toggle", path)
        self.assertIn("(workspace 3): closed 2", out)

    def test_missing_layout_workspace_warns_and_uses_current(self):
        path = self.write_layout(workspace=9)
        self.on(1)
        code, out, err = self.run_cli(path)
        self.assertEqual(code, 0, err)
        self.assertIn("workspace 9 does not exist (there are 4)", err)
        self.assertIn("(workspace 2): 2 opened", out)

    def test_workspace_errors(self):
        code, _, err = self.run_cli(self.path, "--workspace", "9")
        self.assertEqual(code, 1)
        self.assertIn("only 4 workspaces", err)
        self.backend.desktop = None
        code, _, err = self.run_cli(self.path, "--workspace", "2")
        self.assertEqual(code, 1)
        self.assertIn("does not report workspaces", err)


class ExitShellTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "a.json")
        with open(self.path, "w") as fh:
            json.dump(LAYOUT, fh)
        self.store = StateStore(os.path.join(self.tmp.name, "state"))
        self.calls = []
        fake_terminals_on_path(self)

    def run_cli(self, *argv, backend=None):
        out, err = io.StringIO(), io.StringIO()
        code = cli.main(list(argv), out=out, err=err, detected=MONS, backend=backend or FakeBackend(),
                        popen=lambda *a, **k: None, store=self.store,
                        exit_shell=lambda e: self.calls.append("exit"))
        return code, out.getvalue(), err.getvalue()

    def test_shell_closed_after_success(self):
        code, _, err = self.run_cli(self.path, "-x")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.calls, ["exit"])
        self.run_cli("--close", "all", "--exit-shell")
        self.assertEqual(self.calls, ["exit", "exit"])

    def test_shell_kept_when_something_failed(self):
        code, _, err = self.run_cli(self.path, "-x", backend=FakeBackend(appear=False))
        self.assertEqual(code, 1)
        self.assertEqual(self.calls, [])
        self.assertIn("terminal stays open", err)

    def test_not_without_the_option(self):
        self.run_cli(self.path)
        self.assertEqual(self.calls, [])

    def test_only_with_window_actions(self):
        from tilepane.invocation import UsageError, parse
        for argv in (["--dry-run", "a.json", "-x"], ["--edit", "a.json", "-x"], ["--list", "-x"]):
            with self.subTest(argv=argv), self.assertRaises(UsageError):
                parse(argv)
        self.assertTrue(parse(["a.json", "-x"]).exit_shell)
        self.assertTrue(parse(["--demo", "--exit-shell"]).exit_shell)


class LauncherTest(unittest.TestCase):
    def test_parent_shell(self):
        from tilepane import launcher
        read = {"/proc/42/comm": "bash\n", "/proc/43/comm": "-zsh\n", "/proc/44/comm": "cinnamon\n"}.__getitem__
        self.assertEqual(launcher.parent_shell(42, read=read, isatty=lambda fd: True), (42, ""))
        self.assertEqual(launcher.parent_shell(43, read=read, isatty=lambda fd: True)[0], 43)
        self.assertIsNone(launcher.parent_shell(44, read=read, isatty=lambda fd: True)[0])
        self.assertIsNone(launcher.parent_shell(42, read=read, isatty=lambda fd: False)[0])
        self.assertIsNone(launcher.parent_shell(1, read=read, isatty=lambda fd: True)[0])

    def test_exit_shell_hangs_up_the_shell(self):
        import signal
        from tilepane import launcher
        sent, out = [], io.StringIO()
        self.assertTrue(launcher.exit_shell(out, find=lambda: (42, ""), kill=lambda p, s: sent.append((p, s))))
        self.assertEqual(sent, [(42, signal.SIGHUP)])
        self.assertFalse(launcher.exit_shell(out, find=lambda: (None, "not a shell"), kill=lambda p, s: sent.append(1)))
        self.assertIn("nothing was closed", out.getvalue())
