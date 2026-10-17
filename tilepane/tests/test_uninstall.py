import importlib.metadata
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from tests.fakes import FakeBackend
from deskmap import monitors
from tilepane import cli, uninstall
from tilepane.invocation import UsageError, parse
from tilepane.state import Record, StateStore

MONS = monitors.number_monitors([monitors.Monitor(0, "DP-1", 0, 0, 1920, 1080)])


class FakeDist:
    def __init__(self, direct=None):
        self.direct = direct

    def read_text(self, name):
        return self.direct


class DetectTest(unittest.TestCase):
    def test_pipx(self):
        with tempfile.TemporaryDirectory() as venv:
            open(os.path.join(venv, "pipx_metadata.json"), "w").close()
            cmd, how = uninstall.installed_how(venv, lambda n: FakeDist(), lambda b: "/usr/bin/pipx")
            self.assertEqual((cmd, how), (["/usr/bin/pipx", "uninstall", "tilepane"], "pipx"))
            cmd, how = uninstall.installed_how(venv, lambda n: FakeDist(), lambda b: None)
            self.assertIsNone(cmd)
            self.assertIn("pipx uninstall tilepane", how)

    def test_pip_editable(self):
        cmd, how = uninstall.installed_how("/home/a/venv", lambda n: FakeDist('{"dir_info": {"editable": true}}'),
                                           lambda b: None)
        self.assertEqual(cmd[-4:], ["pip", "uninstall", "-y", "tilepane"])
        self.assertEqual(how, "pip (editable)")

    def test_not_installed(self):
        def missing(n):
            raise importlib.metadata.PackageNotFoundError(n)
        cmd, how = uninstall.installed_how("/usr", missing, lambda b: None)
        self.assertIsNone(cmd)
        self.assertIn("not installed", how)


class ParseTest(unittest.TestCase):
    def test_options(self):
        inv = parse(["--uninstall", "--purge", "--yes"])
        self.assertEqual((inv.action, inv.purge, inv.yes), ("uninstall", True, True))
        for argv in (["--purge"], ["--yes", "a.json"], ["--uninstall", "a.json"], ["--uninstall", "--close", "all"]):
            with self.subTest(argv=argv), self.assertRaises(UsageError):
                parse(argv)


class UninstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = {"XDG_STATE_HOME": os.path.join(self.tmp.name, "state"),
               "XDG_CONFIG_HOME": os.path.join(self.tmp.name, "config")}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cfg_dir = os.path.join(self.tmp.name, "config", "tilepane")
        os.makedirs(self.cfg_dir)
        with open(os.path.join(self.cfg_dir, "config.json"), "w") as fh:
            json.dump({"name": "a", "split": {}}, fh)
        self.store = StateStore()
        self.backend = FakeBackend()
        self.backend._open.update({1, 2})
        with self.store.transaction() as recs:
            recs += [Record(1, "/a.json", "a", "DP-1", "0"), Record(2, "/a.json", "a", "DP-1", "1")]
        self.ran = []
        for name, value in (("installed_how", lambda: (["pipx", "uninstall", "tilepane"], "pipx")),
                            ("run_command", lambda cmd: (self.ran.append(cmd), (0, "uninstalled tilepane"))[1])):
            p = mock.patch.object(uninstall, name, value)
            p.start()
            self.addCleanup(p.stop)

    def run_cli(self, *argv, answer="y"):
        out, err = io.StringIO(), io.StringIO()
        code = cli.main(list(argv), out=out, err=err, detected=MONS, backend=self.backend,
                        store=self.store, ask=lambda prompt: answer)
        return code, out.getvalue(), err.getvalue()

    def test_uninstall_keeps_layouts(self):
        code, out, err = self.run_cli("--uninstall")
        self.assertEqual(code, 0, err)
        self.assertIn("closes the 2 window(s)", out)
        self.assertIn("Your layouts are kept", out)
        self.assertEqual(self.backend._open, set())
        self.assertFalse(os.path.exists(self.store.dir))
        self.assertTrue(os.path.exists(os.path.join(self.cfg_dir, "config.json")))
        self.assertEqual(self.ran, [["pipx", "uninstall", "tilepane"]])
        self.assertIn("tilepane was removed", out)

    def test_purge_also_deletes_layouts(self):
        code, out, _ = self.run_cli("--uninstall", "--purge", "--yes", answer="n")
        self.assertEqual(code, 0)
        self.assertIn("deletes your layouts", out)
        self.assertIn("config.json", out)
        self.assertFalse(os.path.exists(self.cfg_dir))

    def test_no_answer_removes_nothing(self):
        code, out, _ = self.run_cli("--uninstall", "--purge", answer="")
        self.assertEqual(code, 1)
        self.assertIn("nothing was removed", out)
        self.assertEqual(self.ran, [])
        self.assertEqual(self.backend._open, {1, 2})
        self.assertTrue(os.path.exists(self.cfg_dir))

    def test_failed_program_removal_is_reported(self):
        with mock.patch.object(uninstall, "run_command", lambda cmd: (1, "permission denied")):
            code, _, err = self.run_cli("--uninstall", "--yes")
        self.assertEqual(code, 1)
        self.assertIn("removing the program failed", err)
        self.assertTrue(os.path.exists(self.store.dir), "state kept when the program stays")
