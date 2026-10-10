import io
import json
import os
import tempfile
import unittest

from tilepane import cli, monitors
from tilepane.invocation import Task, UsageError, parse

MONS = monitors.number_monitors([
    monitors.Monitor(0, "DP-1", 0, 240, 1920, 1200),
    monitors.Monitor(0, "HDMI-1", 1920, 0, 2560, 1440, primary=True),
])

TWO_COLUMNS = {"name": "two", "margin": 0, "split": {
    "dir": "columns", "at": "50%", "a": {"run": "htop"}, "b": {"run": ["a", "b"], "title": "x"}}}


class ParseTest(unittest.TestCase):
    def tasks(self, *argv):
        return [(t.source, t.layouts, t.monitor) for t in parse(list(argv)).tasks]

    def test_no_arguments_is_help(self):
        self.assertEqual(parse([]).action, "help")

    def test_json_layout_monitor_belong_to_the_task(self):
        got = self.tasks("--json", "a.json", "--layout", "x", "--monitor", "1",
                         "--json", "b.json", "--monitor", "2")
        self.assertEqual(got, [("a.json", ["x"], "1"), ("b.json", [], "2")])

    def test_positional_file_then_names(self):
        self.assertEqual(self.tasks("meters.json", "three"), [("meters.json", ["three"], None)])

    def test_names_without_file_use_default_config(self):
        self.assertEqual(self.tasks("3", "5"), [(None, ["3", "5"], None)])

    def test_name_after_file_task_then_new_file(self):
        self.assertEqual(self.tasks("3", "b.json", "x"),
                         [(None, ["3"], None), ("b.json", ["x"], None)])

    def test_layout_option_without_task_starts_default_task(self):
        self.assertEqual(self.tasks("--layout", "3"), [(None, ["3"], None)])

    def test_monitor_before_first_task_is_the_default(self):
        inv = parse(["--monitor", "2", "3", "--json", "a.json"])
        self.assertEqual(inv.default_monitor, "2")
        self.assertEqual([t.monitor for t in inv.tasks], [None, None])

    def test_monitor_after_name_belongs_to_task(self):
        self.assertEqual(self.tasks("3", "--monitor", "1"), [(None, ["3"], "1")])

    def test_equals_form(self):
        self.assertEqual(self.tasks("--json=a.json", "--monitor=1"), [("a.json", [], "1")])

    def test_config_is_alias_of_json(self):
        self.assertEqual(self.tasks("--config", "a.json"), [("a.json", [], None)])

    def test_file_named_like_a_layout_wins_but_layout_forces_name(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.getcwd()
            os.chdir(d)
            try:
                open("3", "w").close()
                self.assertEqual(self.tasks("3"), [("3", [], None)])
                self.assertEqual(self.tasks("--layout", "3"), [(None, ["3"], None)])
            finally:
                os.chdir(old)

    def test_flags(self):
        inv = parse(["--dry-run", "--strict", "-v", "--eval-when", "--wait-monitors", "2.5", "a.json"])
        self.assertTrue(inv.dry_run and inv.strict and inv.verbose and inv.eval_when)
        self.assertEqual(inv.wait_monitors, 2.5)

    def test_actions(self):
        for flag, action in [("--doctor", "doctor"), ("--monitors", "monitors"),
                             ("--list", "list"), ("--version", "version"), ("-h", "help")]:
            self.assertEqual(parse([flag]).action, action)
        inv = parse(["--explain", "on_exit"])
        self.assertEqual((inv.action, inv.explain), ("explain", "on_exit"))

    def test_errors(self):
        for argv in (["--bogus"], ["--monitor"], ["--json"], ["--dry-run=1"],
                     ["--wait-monitors", "x"], ["--wait-monitors", "-1"],
                     ["a.json", "--monitor", "1", "--monitor", "2"],
                     ["--monitor", "1", "--monitor", "2"], ["--layout", ""]):
            with self.subTest(argv=argv), self.assertRaises(UsageError):
                parse(argv)

    def test_unknown_option_suggests(self):
        with self.assertRaises(UsageError) as cm:
            parse(["--dryrun"])
        self.assertIn("--dry-run", str(cm.exception))

    def test_not_yet_implemented_options(self):
        for opt in ("--close", "--toggle", "--demo", "--edit"):
            with self.subTest(opt=opt), self.assertRaises(UsageError) as cm:
                parse([opt])
            self.assertIn("not implemented yet", str(cm.exception))

    def test_double_dash_makes_rest_positional(self):
        self.assertEqual(self.tasks("--", "--weird"), [(None, ["--weird"], None)])


class CliTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def write(self, name, data):
        path = os.path.join(self.dir.name, name)
        with open(path, "w") as fh:
            fh.write(data if isinstance(data, str) else json.dumps(data))
        return path

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        code = cli.main(list(argv), out=out, err=err, detected=MONS)
        return code, out.getvalue(), err.getvalue()

    def test_dry_run_prints_rectangles(self):
        path = self.write("a.json", TWO_COLUMNS)
        code, out, err = self.run_cli("--dry-run", path)
        self.assertEqual(code, 0, err)
        self.assertIn('layout "two"', out)
        self.assertIn("monitor 0 DP-1 1920x1200+0+240", out)
        self.assertRegex(out, r"0\s+0\s+240\s+960\s+1200\s+htop")
        self.assertRegex(out, r"1\s+960\s+240\s+960\s+1200\s+a; b")

    def test_monitor_selection_and_offsets(self):
        path = self.write("a.json", TWO_COLUMNS)
        code, out, err = self.run_cli("--dry-run", path, "--monitor", "HDMI-1")
        self.assertEqual(code, 0, err)
        self.assertRegex(out, r"0\s+1920\s+0\s+1280\s+1440\s+htop")

    def test_monitor_list_opens_on_each(self):
        path = self.write("a.json", TWO_COLUMNS)
        code, out, _ = self.run_cli("--dry-run", path, "--monitor", "0,1")
        self.assertEqual(out.count('layout "two"'), 2)
        self.assertIn("2 ok, 0 failed", out)

    def test_monitor_all_primary_and_alias(self):
        data = dict(TWO_COLUMNS, monitors={"main": "HDMI-1"})
        path = self.write("a.json", data)
        self.assertEqual(self.run_cli("--dry-run", path, "--monitor", "all")[1].count("layout"), 2)
        self.assertIn("HDMI-1", self.run_cli("--dry-run", path, "--monitor", "primary")[1])
        self.assertIn("HDMI-1", self.run_cli("--dry-run", path, "--monitor", "main")[1])

    def test_default_monitor_before_task(self):
        path = self.write("a.json", TWO_COLUMNS)
        code, out, _ = self.run_cli("--monitor", "1", "--dry-run", path)
        self.assertIn("monitor 1 HDMI-1", out)

    def test_several_tasks_and_failure_does_not_stop_others(self):
        good = self.write("good.json", TWO_COLUMNS)
        bad = self.write("bad.json", "{ not json")
        code, out, err = self.run_cli("--dry-run", "--json", bad, "--json", good, "--monitor", "1",
                                      "--json", "/nonexistent.json")
        self.assertEqual(code, 1)
        self.assertIn('layout "two"', out)
        self.assertIn("invalid JSON", err)
        self.assertIn("file not found", err)
        self.assertIn("1 ok, 2 failed", err)

    def test_unknown_monitor_is_a_task_error(self):
        path = self.write("a.json", TWO_COLUMNS)
        code, out, err = self.run_cli("--dry-run", path, "--monitor", "9")
        self.assertEqual(code, 1)
        self.assertIn("no monitor 9", err)
        self.assertIn("0 DP-1", err)

    def test_layout_selection_in_multi_layout_file(self):
        path = self.write("m.json", {"layouts": [
            dict(TWO_COLUMNS, name="one"), dict(TWO_COLUMNS, name="two")]})
        code, out, err = self.run_cli("--dry-run", path)
        self.assertEqual(code, 1)
        self.assertIn("choose one with --layout NAME (one, two)", err)
        code, out, err = self.run_cli("--dry-run", path, "two")
        self.assertEqual(code, 0, err)
        self.assertIn('layout "two"', out)
        self.assertNotIn('layout "one"', out)
        code, out, err = self.run_cli("--dry-run", path, "nope")
        self.assertEqual(code, 1)
        self.assertIn("no layout named 'nope'", err)

    def test_several_names_open_several_layouts(self):
        path = self.write("m.json", {"layouts": [
            dict(TWO_COLUMNS, name="one"), dict(TWO_COLUMNS, name="two")]})
        code, out, _ = self.run_cli("--dry-run", path, "one", "two")
        self.assertEqual(out.count("layout "), 2)

    def test_config_warnings_go_to_stderr_once(self):
        data = dict(TWO_COLUMNS, onexit="close")
        path = self.write("w.json", data)
        code, out, err = self.run_cli("--dry-run", "--json", path, "--json", path, "--monitor", "1")
        self.assertEqual(code, 0)
        self.assertEqual(err.count("unknown key 'onexit'"), 1)

    def test_strict_turns_warnings_into_errors(self):
        path = self.write("w.json", dict(TWO_COLUMNS, onexit="close"))
        code, out, err = self.run_cli("--dry-run", "--strict", path)
        self.assertEqual(code, 1)
        self.assertIn("unknown key", err)

    def test_geometry_error_is_reported(self):
        small = {"name": "s", "margin": 8, "split": {"dir": "columns", "at": "1px", "a": {}, "b": {}}}
        path = self.write("s.json", small)
        code, out, err = self.run_cli("--dry-run", path)
        self.assertEqual(code, 1)
        self.assertIn("too small", err)

    def test_when_is_not_evaluated_without_flag(self):
        data = {"name": "w", "margin": 0, "split": {
            "dir": "columns", "a": {"run": "x"}, "b": {"run": "y", "when": "false"}}}
        path = self.write("w.json", data)
        code, out, _ = self.run_cli("--dry-run", path)
        self.assertIn("[when: false]", out)
        self.assertEqual(out.count("\n  0 ") + out.count("\n  1 "), 2)
        code, out, _ = self.run_cli("--dry-run", "--eval-when", path)
        self.assertNotIn("[when:", out)
        self.assertRegex(out, r"\n  0\s+0\s+240\s+1920\s+1200\s+x")

    def test_verbose_shows_pane_rectangle_and_settings(self):
        path = self.write("a.json", TWO_COLUMNS)
        code, out, _ = self.run_cli("--dry-run", "-v", path)
        self.assertIn("pane 960x1200+0+240", out)
        self.assertIn("snap cell", out)

    def test_not_dry_run_is_not_implemented(self):
        path = self.write("a.json", TWO_COLUMNS)
        code, out, err = self.run_cli(path)
        self.assertEqual(code, 2)
        self.assertIn("not implemented yet", err)

    def test_missing_default_config(self):
        old = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self.dir.name
        try:
            code, out, err = self.run_cli("--dry-run", "3")
        finally:
            if old is None:
                del os.environ["XDG_CONFIG_HOME"]
            else:
                os.environ["XDG_CONFIG_HOME"] = old
        self.assertEqual(code, 1)
        self.assertIn("file not found", err)

    def test_default_config_by_name(self):
        os.makedirs(os.path.join(self.dir.name, "tilepane"))
        self.write(os.path.join("tilepane", "config.json"),
                   {"layouts": [dict(TWO_COLUMNS, name="3")]})
        old = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self.dir.name
        try:
            code, out, err = self.run_cli("--dry-run", "3")
        finally:
            if old is None:
                del os.environ["XDG_CONFIG_HOME"]
            else:
                os.environ["XDG_CONFIG_HOME"] = old
        self.assertEqual(code, 0, err)
        self.assertIn('layout "3"', out)

    def test_list(self):
        path = self.write("m.json", {"layouts": [
            dict(TWO_COLUMNS, name="one"), {"name": "solo", "split": {}}]})
        code, out, _ = self.run_cli("--list", path)
        self.assertEqual(code, 0)
        lines = out.strip().splitlines()
        self.assertEqual([ln.split("\t")[:2] for ln in lines],
                         [["one", "2 panes"], ["solo", "1 panes"]])

    def test_explain(self):
        code, out, _ = self.run_cli("--explain", "on_exit")
        self.assertEqual(code, 0)
        self.assertIn("Used in:", out)
        code, out, err = self.run_cli("--explain", "onexit")
        self.assertEqual(code, 2)
        self.assertIn("did you mean", err)

    def test_usage_error_exit_code(self):
        code, out, err = self.run_cli("--bogus")
        self.assertEqual(code, 2)
        self.assertIn("unknown option", err)

    def test_help_and_version(self):
        self.assertIn("usage: tilepane", self.run_cli()[1])
        self.assertIn("tilepane 0.1.0", self.run_cli("--version")[1])


if __name__ == "__main__":
    unittest.main()
