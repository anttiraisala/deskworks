import io
import unittest

from tests.fakes import FakeBackend
from tilepane import cli, workspaces
from tilepane.workspaces import Desktops, Numbering, grid, user_numbers


class GridTest(unittest.TestCase):
    def test_one_row_without_layout(self):
        cells, how = grid(4, None)
        self.assertEqual(cells, [[0, 1, 2, 3]])
        self.assertIn("one row", how)

    def test_three_by_three_from_top_left(self):
        cells, _ = grid(9, [0, 3, 3, 0])
        self.assertEqual(cells, [[0, 1, 2], [3, 4, 5], [6, 7, 8]])
        self.assertEqual(user_numbers(cells), {6: 0, 7: 1, 8: 2, 3: 3, 4: 4, 5: 5, 0: 6, 1: 7, 2: 8})

    def test_columns_or_rows_given_as_zero(self):
        self.assertEqual(grid(4, [0, 2, 0, 0])[0], [[0, 1], [2, 3]])
        self.assertEqual(grid(6, [0, 0, 2, 0])[0], [[0, 1, 2], [3, 4, 5]])

    def test_vertical_and_other_corners(self):
        self.assertEqual(grid(4, [1, 2, 2, 0])[0], [[0, 2], [1, 3]])
        self.assertEqual(grid(4, [0, 2, 2, 3])[0], [[2, 3], [0, 1]])
        self.assertEqual(grid(4, [0, 2, 2, 1])[0], [[1, 0], [3, 2]])

    def test_incomplete_grid_leaves_empty_cells(self):
        self.assertEqual(grid(5, [0, 3, 2, 0])[0], [[0, 1, 2], [3, 4, None]])


class NumberingTest(unittest.TestCase):
    def test_one_row_counts_from_zero(self):
        num = Numbering.of(Desktops(4, 1))
        self.assertEqual((num.count, num.number(1), num.index(0), num.index(4)), (4, 1, 0, None))

    def test_grid_counts_from_the_bottom_left(self):
        num = Numbering.of(Desktops(4, 0, layout=[0, 2, 2, 0]))
        self.assertEqual([num.index(n) for n in range(4)], [2, 3, 0, 1])
        self.assertEqual(num.number(0), 2)

    def test_compiz_viewports_are_workspaces(self):
        # The owner's machine: 2 x 2 viewports, each the whole 6528x2352 screen, in the bottom left.
        d = Desktops(1, 0, geometry=[13056, 4704], screen=(6528, 2352), viewport=(0, 2352))
        self.assertEqual(workspaces.viewport_grid(d), (2, 2, (0, 1)))
        num = Numbering.of(d)
        self.assertEqual((num.count, num.current, num.number(num.current)), (4, 2, 0))
        self.assertEqual([num.index(n) for n in range(4)], [2, 3, 0, 1])
        self.assertIsNone(workspaces.viewport_grid(Desktops(1, 0, geometry=[1920, 1080], screen=(1920, 1080))))

    def test_no_workspaces(self):
        self.assertEqual(Numbering.of(None).count, 0)


def numbers_drawn(text):
    rows = text.split("rows upward):")[1].split("\n\n")[0].strip("\n").split("\n")
    return [line.split() for line in rows]


class RenderTest(unittest.TestCase):
    def test_render_marks_current_with_the_numbers_from_the_bottom_left(self):
        text = workspaces.render(Desktops(9, 4, layout=[0, 3, 3, 0]))
        self.assertIn("9 workspace(s) (current: 4): 3 x 3 grid", text)
        self.assertEqual(numbers_drawn(text), [["6", "7", "8"], ["3", "[4]", "5"], ["0", "1", "2"]])
        self.assertNotIn("own order", text)
        self.assertIn("own order", workspaces.render(Desktops(9, 4, layout=[0, 3, 3, 0]), verbose=True))

    def test_names_shown_when_not_default(self):
        text = workspaces.render(Desktops(2, 0, names=["Mail", "Workspace 2"]))
        self.assertIn("0: Mail", text)
        self.assertNotIn("Names", workspaces.render(Desktops(2, 0, names=["desktop 1", "Workspace 2"])))

    def test_compiz_viewports(self):
        d = Desktops(1, 0, geometry=[13056, 4704], screen=(6528, 2352), viewport=(0, 2352))
        text = workspaces.render(d)
        self.assertIn("4 workspace(s) (current: 0): viewports of one large desktop, 2 x 2, each 6528x2352", text)
        self.assertEqual(numbers_drawn(text), [["2", "3"], ["[0]", "1"]])
        self.assertIn("_NET_DESKTOP_GEOMETRY: [13056, 4704]", workspaces.render(d, verbose=True))

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
