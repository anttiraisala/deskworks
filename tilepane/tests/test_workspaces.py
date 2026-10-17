import io
import unittest

from tests.fakes import FakeBackend
from tilepane import cli


class WorkspacesCliTest(unittest.TestCase):
    def test_cli(self):
        backend = FakeBackend(desktop=1)
        out, err = io.StringIO(), io.StringIO()
        self.assertEqual(cli.main(["--workspaces"], out=out, err=err, backend=backend), 0, err.getvalue())
        self.assertIn("4 workspace(s) (current: 1): one row", out.getvalue())
        backend = FakeBackend(desktop=None)
        self.assertEqual(cli.main(["--workspaces"], out=out, err=err, backend=backend), 1)
