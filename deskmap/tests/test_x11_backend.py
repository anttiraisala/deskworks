import unittest


class ClientMessageTest(unittest.TestCase):
    def test_negative_coordinates_are_sent_as_twos_complement(self):
        # A viewport above the current one (Compiz) is at a negative y.
        from deskmap.backends.x11 import card32
        self.assertEqual([card32(v) for v in (-2352, 0, 6528)], [0xFFFFF6D0, 0, 6528])
