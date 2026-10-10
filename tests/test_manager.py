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
