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


class ClientMessageTest(unittest.TestCase):
    def test_negative_coordinates_are_sent_as_twos_complement(self):
        # A viewport above the current one (Compiz) is at a negative y.
        from tilepane.backends.x11 import card32
        self.assertEqual([card32(v) for v in (-2352, 0, 6528)], [0xFFFFF6D0, 0, 6528])
