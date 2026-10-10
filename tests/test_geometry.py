import random
import unittest

from tilepane.geometry import GeometryError, Rect, compute

AREA = Rect(0, 0, 1000, 500)


def leaf(name="x"):
    return {"run": name}


def rects(layout, area=AREA):
    return {lr.id: lr.rect for lr in compute(layout, area)}


def outers(layout, area=AREA):
    return {lr.id: lr.outer for lr in compute(layout, area)}


def two(dir_, at, **extra):
    return {"split": {"dir": dir_, "at": at, "a": leaf("a"), "b": leaf("b")}, **extra}


class MarginTest(unittest.TestCase):
    def test_single_leaf_gets_half_margin_on_every_side(self):
        r = rects({"margin": 8, "split": leaf()})["root"]
        self.assertEqual(r, Rect(4, 4, 992, 492))

    def test_gap_between_windows_is_the_full_margin(self):
        r = rects(two("v", "50%", margin=8))
        self.assertEqual(r["0"], Rect(4, 4, 492, 492))
        self.assertEqual(r["1"], Rect(504, 4, 492, 492))
        self.assertEqual(r["1"].x - r["0"].right, 8)

    def test_odd_margin_gap_is_exact(self):
        r = rects(two("v", "50%", margin=7))
        self.assertEqual(r["1"].x - r["0"].right, 7)

    def test_zero_margin_tiles_exactly(self):
        r = rects(two("h", "50%"))
        self.assertEqual(r["0"], Rect(0, 0, 1000, 250))
        self.assertEqual(r["1"], Rect(0, 250, 1000, 250))

    def test_node_margin_overrides(self):
        layout = {"margin": 8, "split": {
            "dir": "v", "at": "50%", "margin": 0, "a": leaf(), "b": leaf()}}
        r = rects(layout)
        self.assertEqual(r["0"], Rect(0, 0, 500, 500))

    def test_leaf_margin_overrides(self):
        layout = {"margin": 8, "split": {
            "dir": "v", "at": "50%", "a": {"run": "a", "margin": 0}, "b": leaf()}}
        r = rects(layout)
        self.assertEqual(r["0"], Rect(0, 0, 500, 500))
        self.assertEqual(r["1"], Rect(504, 4, 492, 492))

    def test_offset_monitor(self):
        r = rects({"margin": 8, "split": leaf()}, Rect(1920, 240, 1920, 1200))["root"]
        self.assertEqual(r, Rect(1924, 244, 1912, 1192))


class OuterMarginTest(unittest.TestCase):
    def test_single_leaf_edge_is_exactly_outer_margin(self):
        r = rects({"margin": 8, "outer_margin": 16, "split": leaf()})["root"]
        self.assertEqual(r, Rect(16, 16, 968, 468))

    def test_edge_not_counted_twice_gap_stays_inner_margin(self):
        r = rects(two("v", "50%", margin=8, outer_margin=16))
        self.assertEqual(r["0"], Rect(16, 16, 480, 468))
        self.assertEqual(r["1"], Rect(504, 16, 480, 468))
        self.assertEqual(r["1"].x - r["0"].right, 8)
        self.assertEqual(1000 - r["1"].right, 16)
        self.assertEqual(500 - r["1"].bottom, 16)

    def test_nested_leaf_only_outer_sides_use_outer_margin(self):
        layout = {"margin": 8, "outer_margin": 16, "split": {
            "dir": "v", "at": "50%", "a": leaf("a"), "b": {
                "dir": "h", "at": "50%", "a": leaf("b"), "b": leaf("c")}}}
        r = rects(layout)
        self.assertEqual(r["1.0"].y, 16)
        self.assertEqual(r["1.1"].bottom, 484)
        self.assertEqual(r["1.1"].y - r["1.0"].bottom, 8)
        self.assertEqual(r["1.0"].x - r["0"].right, 8)

    def test_outer_margin_zero(self):
        r = rects({"margin": 8, "outer_margin": 0, "split": leaf()})["root"]
        self.assertEqual(r, Rect(0, 0, 1000, 500))

    def test_outer_margin_too_large(self):
        with self.assertRaises(GeometryError):
            compute({"outer_margin": 300, "split": leaf()}, AREA)


class SplitPointTest(unittest.TestCase):
    def test_percent(self):
        o = outers(two("v", "60%"))
        self.assertEqual((o["0"].width, o["1"].x, o["1"].width), (600, 600, 400))

    def test_pixels_from_left(self):
        o = outers(two("v", "300px"))
        self.assertEqual((o["0"].width, o["1"].x), (300, 300))

    def test_negative_pixels_from_right(self):
        o = outers(two("v", "-300px"))
        self.assertEqual((o["0"].width, o["1"].x, o["1"].width), (700, 700, 300))

    def test_negative_percent(self):
        o = outers(two("v", "-40%"))
        self.assertEqual((o["1"].x, o["1"].width), (600, 400))

    def test_horizontal_is_top_and_bottom(self):
        o = outers(two("h", "40%"))
        self.assertEqual((o["0"].y, o["0"].height), (0, 200))
        self.assertEqual((o["1"].y, o["1"].height), (200, 300))

    def test_dir_aliases(self):
        self.assertEqual(outers(two("vertical", "50%")), outers(two("v", "50%")))
        self.assertEqual(outers(two("horizontal", "50%")), outers(two("h", "50%")))

    def test_default_at_is_half(self):
        layout = {"split": {"dir": "v", "a": leaf(), "b": leaf()}}
        self.assertEqual(outers(layout)["1"].x, 500)

    def test_numeric_at_means_pixels(self):
        self.assertEqual(outers(two("v", 300))["0"].width, 300)
        self.assertEqual(outers(two("v", -300))["1"].width, 300)

    def test_split_uses_area_before_margin(self):
        # 60% of 1000 is 600 regardless of margin
        o = outers(two("v", "60%", margin=20, outer_margin=0))
        self.assertEqual(o["1"].x, 600)


class AtBasisTest(unittest.TestCase):
    def test_outer_basis_is_default(self):
        r = rects(two("v", "300px", margin=8))
        self.assertEqual(r["0"].width, 292)

    def test_visible_basis_gives_exact_window_width(self):
        r = rects(two("v", "300px", margin=8, at_basis="visible"))
        self.assertEqual(r["0"].width, 300)

    def test_visible_basis_with_outer_margin(self):
        r = rects(two("v", "300px", margin=8, outer_margin=16, at_basis="visible"))
        self.assertEqual(r["0"].width, 300)
        self.assertEqual(r["0"].x, 16)

    def test_visible_basis_from_right(self):
        r = rects(two("v", "-300px", margin=8, outer_margin=16, at_basis="visible"))
        self.assertEqual(r["1"].width, 300)
        self.assertEqual(r["1"].right, 984)

    def test_visible_basis_on_node(self):
        layout = {"margin": 8, "split": {
            "dir": "v", "at": "300px", "at_basis": "visible", "a": leaf(), "b": leaf()}}
        self.assertEqual(rects(layout)["0"].width, 300)

    def test_bad_basis(self):
        with self.assertRaises(GeometryError):
            compute(two("v", "50%", at_basis="inner"), AREA)


class FrSizesTest(unittest.TestCase):
    @staticmethod
    def cols(sizes, width=1000, **extra):
        layout = {"split": {"dir": "v", "sizes": sizes,
                            "children": [leaf(str(i)) for i in range(len(sizes))]},
                  **extra}
        return [lr.outer for lr in compute(layout, Rect(0, 0, width, 100))]

    def test_fr_and_px(self):
        c = self.cols(["1fr", "2fr", "300px"])
        self.assertEqual([r.width for r in c], [233, 467, 300])
        self.assertEqual(c[2].right, 1000)

    def test_equal_children_default(self):
        layout = {"split": {"dir": "h", "children": [leaf(), leaf(), leaf(), leaf()]}}
        self.assertEqual([r.height for r in outers(layout).values()], [125] * 4)

    def test_rounding_shares_boundaries(self):
        c = self.cols(["1fr", "1fr", "1fr"], width=100)
        self.assertEqual([r.width for r in c], [33, 34, 33])
        self.assertEqual(c[0].right, c[1].x)
        self.assertEqual(c[1].right, c[2].x)
        self.assertEqual(c[2].right, 100)

    def test_percent_entry(self):
        c = self.cols(["25%", "1fr"])
        self.assertEqual([r.width for r in c], [250, 750])

    def test_without_fr_last_child_absorbs_leftover(self):
        c = self.cols(["200px", "300px"])
        self.assertEqual([r.width for r in c], [200, 800])

    def test_fr_with_visible_basis(self):
        c = self.cols(["300px", "1fr"], margin=8, at_basis="visible")
        self.assertEqual(c[0].width, 308)

    def test_sizes_exceed_area(self):
        with self.assertRaises(GeometryError):
            self.cols(["800px", "800px", "1fr"])

    def test_sizes_length_mismatch(self):
        layout = {"split": {"dir": "v", "sizes": ["1fr"], "children": [leaf(), leaf()]}}
        with self.assertRaises(GeometryError):
            compute(layout, AREA)


class TreeTest(unittest.TestCase):
    layout = {"margin": 8, "outer_margin": 16, "split": {
        "dir": "v", "at": "60%",
        "a": {"run": "htop"},
        "b": {"dir": "h", "at": "300px",
              "a": {"run": "watch -n1 sensors"},
              "b": {"run": "nvidia-smi -l 1"}}}}

    def test_ids_and_order(self):
        self.assertEqual([lr.id for lr in compute(self.layout, AREA)], ["0", "1.0", "1.1"])

    def test_leaf_data_is_carried(self):
        self.assertEqual(compute(self.layout, AREA)[0].leaf["run"], "htop")

    def test_example_from_spec(self):
        r = rects(self.layout)
        # 60% of the 968px inner width is 580.8, rounded once to boundary x=597
        self.assertEqual(r["0"], Rect(16, 16, 577, 468))
        self.assertEqual(r["1.0"], Rect(601, 16, 383, 296))
        self.assertEqual(r["1.1"], Rect(601, 320, 383, 164))

    def test_deep_tree(self):
        node = leaf("end")
        for _ in range(5):
            node = {"dir": "v", "at": "50%", "a": leaf(), "b": node}
        got = compute({"split": node}, Rect(0, 0, 1024, 100))
        self.assertEqual(len(got), 6)
        self.assertEqual(got[-1].id, "1.1.1.1.1")
        self.assertEqual(got[-1].rect.width, 32)

    def test_mixed_binary_and_nway(self):
        layout = {"split": {"dir": "h", "at": "50%", "a": leaf(), "b": {
            "dir": "v", "children": [leaf(), leaf()]}}}
        self.assertEqual(sorted(rects(layout)), ["0", "1.0", "1.1"])


class PropertyTest(unittest.TestCase):
    """Random trees: panes tile the area exactly and gaps equal the margin."""

    @staticmethod
    def random_node(rng, depth):
        if depth == 0 or rng.random() < 0.25:
            return leaf()
        d = rng.choice(["v", "h"])
        if rng.random() < 0.4:
            n = rng.randint(2, 4)
            return {"dir": d, "sizes": [rng.choice(["1fr", "2fr", "25%"]) for _ in range(n - 1)]
                    + ["1fr"],
                    "children": [PropertyTest.random_node(rng, depth - 1) for _ in range(n)]}
        at = rng.choice([f"{rng.randint(30, 70)}%", f"-{rng.randint(30, 70)}%"])
        return {"dir": d, "at": at,
                "a": PropertyTest.random_node(rng, depth - 1),
                "b": PropertyTest.random_node(rng, depth - 1)}

    def test_random_layouts(self):
        rng = random.Random(12345)
        area = Rect(100, 50, 2400, 1400)
        checked = 0
        for _ in range(400):
            margin = rng.randint(0, 9)
            outer = rng.choice([None, 0, 5, 16])
            layout = {"margin": margin, "split": self.random_node(rng, 3)}
            if outer is not None:
                layout["outer_margin"] = outer
            try:
                got = compute(layout, area)
            except GeometryError:
                continue  # a very unbalanced random tree left a pane too small
            checked += 1

            inner = area if outer is None else Rect(
                area.x + outer, area.y + outer, area.width - 2 * outer, area.height - 2 * outer)
            self.assertEqual(sum(g.outer.width * g.outer.height for g in got),
                             inner.width * inner.height)
            for i, a in enumerate(got):
                for b in got[i + 1:]:
                    self.assertTrue(
                        a.outer.right <= b.outer.x or b.outer.right <= a.outer.x
                        or a.outer.bottom <= b.outer.y or b.outer.bottom <= a.outer.y,
                        f"{a.id} overlaps {b.id}")
                    self._check_gap(a, b, margin)
            for g in got:
                self.assertGreaterEqual(g.rect.x, g.outer.x)
                self.assertLessEqual(g.rect.right, g.outer.right)
            edge = margin // 2 if outer is None else outer
            self.assertEqual(min(g.rect.x for g in got), area.x + edge)
        self.assertGreater(checked, 300)

    def _check_gap(self, a, b, margin):
        for p, q in ((a, b), (b, a)):
            if p.outer.right == q.outer.x and self._span(p.outer, q.outer, "y"):
                self.assertEqual(q.rect.x - p.rect.right, margin)
            if p.outer.bottom == q.outer.y and self._span(p.outer, q.outer, "x"):
                self.assertEqual(q.rect.y - p.rect.bottom, margin)

    @staticmethod
    def _span(p, q, axis):
        if axis == "y":
            return p.y < q.bottom and q.y < p.bottom
        return p.x < q.right and q.x < p.right


class ErrorTest(unittest.TestCase):
    def check(self, layout, area=AREA):
        with self.assertRaises(GeometryError):
            compute(layout, area)

    def test_missing_split(self):
        self.check({"margin": 8})

    def test_unknown_dir(self):
        self.check({"split": {"dir": "x", "a": leaf(), "b": leaf()}})

    def test_missing_dir(self):
        self.check({"split": {"a": leaf(), "b": leaf()}})

    def test_missing_child(self):
        self.check({"split": {"dir": "v", "a": leaf()}})

    def test_children_with_a_b(self):
        self.check({"split": {"dir": "v", "a": leaf(), "b": leaf(), "children": [leaf()]}})

    def test_empty_children(self):
        self.check({"split": {"dir": "v", "children": []}})

    def test_bad_at(self):
        for at in ("abc", "50 %%", "1fr", "0%", "0px", True, None, "--5px"):
            with self.subTest(at=at):
                self.check({"split": {"dir": "v", "at": at, "a": leaf(), "b": leaf()}})

    def test_pixels_exceed_area(self):
        self.check(two("v", "1200px"))
        self.check(two("v", "-1200px"))

    def test_percent_over_100(self):
        self.check(two("v", "120%"))

    def test_full_percent_leaves_empty_pane(self):
        self.check(two("v", "100%"))

    def test_negative_margin(self):
        self.check({"margin": -1, "split": leaf()})

    def test_margin_wrong_type(self):
        self.check({"margin": "8", "split": leaf()})

    def test_pane_too_small(self):
        self.check({"margin": 8, "split": leaf()}, Rect(0, 0, 8, 100))

    def test_non_object_node(self):
        self.check({"split": {"dir": "v", "a": "htop", "b": leaf()}})


if __name__ == "__main__":
    unittest.main()
