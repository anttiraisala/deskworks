import io
import unittest

from tests.fakes import FakeBackend
from tilepane import cli, workspaces
from tilepane.workspaces import Desktops, grid, proposed_numbers


class GridTest(unittest.TestCase):
    def test_one_row_without_layout(self):
        cells, how = grid(4, None)
        self.assertEqual(cells, [[0, 1, 2, 3]])
        self.assertIn("one row", how)

    def test_three_by_three_from_top_left(self):
        cells, _ = grid(9, [0, 3, 3, 0])
        self.assertEqual(cells, [[0, 1, 2], [3, 4, 5], [6, 7, 8]])
        self.assertEqual(proposed_numbers(cells), {6: 0, 7: 1, 8: 2, 3: 3, 4: 4, 5: 5, 0: 6, 1: 7, 2: 8})

    def test_columns_or_rows_given_as_zero(self):
        self.assertEqual(grid(4, [0, 2, 0, 0])[0], [[0, 1], [2, 3]])
        self.assertEqual(grid(6, [0, 0, 2, 0])[0], [[0, 1, 2], [3, 4, 5]])

    def test_vertical_and_other_corners(self):
        self.assertEqual(grid(4, [1, 2, 2, 0])[0], [[0, 2], [1, 3]])
        self.assertEqual(grid(4, [0, 2, 2, 3])[0], [[2, 3], [0, 1]])
        self.assertEqual(grid(4, [0, 2, 2, 1])[0], [[1, 0], [3, 2]])

    def test_incomplete_grid_leaves_empty_cells(self):
        self.assertEqual(grid(5, [0, 3, 2, 0])[0], [[0, 1, 2], [3, 4, None]])


class RenderTest(unittest.TestCase):
    def test_render_marks_current_and_shows_both_numberings(self):
        text = workspaces.render(Desktops(9, 4, layout=[0, 3, 3, 0]))
        self.assertIn("9 workspace(s) (current: 5): 3 x 3 grid", text)
        self.assertIn("[5]", text)
        proposed = text.split("Proposed numbering")[1].splitlines()
        self.assertEqual([line.split() for line in proposed[1:4]], [["6", "7", "8"], ["3", "[4]", "5"], ["0", "1", "2"]])

    def test_names_shown_when_not_default(self):
        text = workspaces.render(Desktops(2, 0, names=["Mail", "Workspace 2"]))
        self.assertIn("1: Mail", text)
        self.assertNotIn("Names", workspaces.render(Desktops(2, 0, names=["desktop 1", "Workspace 2"])))

    def test_compiz_viewports(self):
        # The owner's machine: 2 x 2 viewports, each the whole 6528x2352 screen, in the bottom left.
        d = Desktops(1, 0, geometry=[13056, 4704], screen=(6528, 2352), viewport=(0, 2352))
        self.assertEqual(workspaces.viewport_grid(d), (2, 2, (0, 1)))
        text = workspaces.render(d)
        self.assertIn("4 workspaces as viewports of one large desktop (2 x 2", text)
        self.assertIn("column 1, row 2 from the top", text)
        now = text.split("window manager's order")[1].split("Proposed")[0].split("\n")[1:3]
        self.assertEqual([line.split() for line in now], [["1", "2"], ["[3]", "4"]])
        proposed = text.split("Proposed numbering")[1].split("\n")[1:3]
        self.assertEqual([line.split() for line in proposed], [["2", "3"], ["[0]", "1"]])
        self.assertIsNone(workspaces.viewport_grid(Desktops(1, 0, geometry=[1920, 1080], screen=(1920, 1080))))

    def test_cli(self):
        backend = FakeBackend(desktop=1)
        out, err = io.StringIO(), io.StringIO()
        self.assertEqual(cli.main(["--workspaces"], out=out, err=err, backend=backend), 0, err.getvalue())
        self.assertIn("4 workspace(s) (current: 2): one row", out.getvalue())
        backend = FakeBackend(desktop=None)
        self.assertEqual(cli.main(["--workspaces"], out=out, err=err, backend=backend), 1)
