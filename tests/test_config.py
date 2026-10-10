import json
import os
import tempfile
import unittest

from tilepane import config, geometry
from tilepane.config import ConfigError, load_text, resolve_layout

SAMPLE = {
    "version": 1,
    "defaults": {"margin": 8, "snap": "cell", "on_exit": "keep"},
    "monitors": {"left": "DP-1", "main": 1},
    "layouts": [{
        "name": "3",
        "outer_margin": 16,
        "split": {
            "dir": "columns", "at": "60%",
            "a": {"run": "htop", "cwd": "~", "title": "htop"},
            "b": {"dir": "rows", "at": "300px",
                  "a": {"run": "watch -n1 sensors"},
                  "b": {"run": "nvidia-smi -l 1", "on_exit": "restart",
                        "when": "command -v nvidia-smi"}},
        },
    }],
}


def load(data, **kw):
    return load_text(json.dumps(data), "t.json", **kw)


def errors_of(data, **kw):
    try:
        load(data, **kw)
    except ConfigError as exc:
        return exc.errors
    return []


def leaf_layout(**extra):
    return {"layouts": [{"name": "x", "split": {"run": "htop", **extra}}]}


class LoadTest(unittest.TestCase):
    def test_sample_loads(self):
        cfg = load(SAMPLE)
        self.assertEqual(cfg.names(), ["3"])
        self.assertEqual(cfg.warnings, [])
        self.assertEqual(cfg.monitors["main"], 1)

    def test_flat_file_name_defaults_to_stem(self):
        cfg = load_text(json.dumps({"split": {"run": "htop"}}), "/x/meters.json")
        self.assertEqual(cfg.names(), ["meters"])

    def test_flat_file_with_name_and_file_keys(self):
        cfg = load({"version": 1, "name": "a", "margin": 4, "defaults": {"snap": "pixel"},
                    "split": {"run": "htop"}})
        self.assertEqual(cfg.names(), ["a"])
        self.assertEqual(cfg.defaults["snap"], "pixel")

    def test_numeric_layout_name_becomes_string(self):
        cfg = load({"layouts": [{"name": 3, "split": {}}]})
        self.assertEqual(cfg.names(), ["3"])
        self.assertIsNotNone(cfg.get("3"))

    def test_invalid_json_reports_position(self):
        with self.assertRaises(ConfigError) as cm:
            load_text('{\n  "layouts": [,]\n}', "bad.json")
        self.assertIn("line 2", cm.exception.errors[0])
        self.assertIn("bad.json", cm.exception.errors[0])

    def test_missing_file(self):
        with self.assertRaises(ConfigError) as cm:
            config.load_file("/nonexistent/x.json")
        self.assertIn("file not found", cm.exception.errors[0])

    def test_load_file_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "c.json")
            with open(path, "w") as fh:
                json.dump(SAMPLE, fh)
            self.assertEqual(config.load_file(path).names(), ["3"])

    def test_default_path_uses_xdg(self):
        old = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = "/tmp/xdg"
        try:
            self.assertEqual(config.default_config_path(), "/tmp/xdg/tilepane/config.json")
        finally:
            if old is None:
                del os.environ["XDG_CONFIG_HOME"]
            else:
                os.environ["XDG_CONFIG_HOME"] = old


class ValidationTest(unittest.TestCase):
    def assert_error(self, data, *fragments, **kw):
        errs = errors_of(data, **kw)
        self.assertTrue(errs, f"expected an error for {data}")
        text = "\n".join(errs)
        for f in fragments:
            self.assertIn(f, text)

    def test_top_level_must_be_object(self):
        self.assert_error([], "JSON object")

    def test_needs_layouts_or_split(self):
        self.assert_error({"margin": 8}, "needs 'layouts'")

    def test_layouts_and_split_conflict(self):
        self.assert_error({"layouts": [{"name": "a", "split": {}}], "split": {}}, "both")

    def test_empty_layouts(self):
        self.assert_error({"layouts": []}, "non-empty list")

    def test_layout_needs_name_and_split(self):
        self.assert_error({"layouts": [{"split": {}}]}, "needs a 'name'")
        self.assert_error({"layouts": [{"name": "a"}]}, "needs a 'split'")

    def test_duplicate_layout_names(self):
        self.assert_error({"layouts": [{"name": "a", "split": {}}, {"name": "a", "split": {}}]},
                          "duplicate layout name 'a'")

    def test_version(self):
        self.assert_error({"version": 2, "split": {}}, "newer")
        self.assert_error({"version": "1", "split": {}}, "whole number")
        self.assertEqual(errors_of({"version": 1, "split": {}}), [])

    def test_error_paths(self):
        data = {"layouts": [{"name": "a", "split": {
            "dir": "columns", "a": {"run": 5}, "b": {"snap": "huge"}}}]}
        self.assert_error(data, "layouts[0].split.a.run", "layouts[0].split.b.snap")

    def test_all_problems_reported_together(self):
        data = {"layouts": [{"name": "a", "margin": -1, "split": {
            "dir": "x", "a": {"run": ""}, "b": {"on_exit": "never"}}}]}
        self.assertGreaterEqual(len(errors_of(data)), 4)

    def test_value_types(self):
        for key, bad in [("margin", "8"), ("margin", -1), ("margin", True), ("font_size", 0),
                         ("snap", "x"), ("on_exit", 1), ("restart_delay", -1),
                         ("max_restarts", 1.5), ("stop_on_error", "yes"),
                         ("decorations", 1), ("cwd", ""), ("env", {"A": 1}),
                         ("terminal", 5), ("profile", ""), ("title", 3), ("id", ""),
                         ("when", ""), ("empty", "true"), ("mode", "loop"),
                         ("interval", 0), ("run", []), ("run", [1])]:
            with self.subTest(key=key, bad=bad):
                self.assertTrue(errors_of(leaf_layout(**{key: bad})))

    def test_valid_values(self):
        for key, good in [("margin", 0), ("margin", 7.5), ("font_size", 11), ("snap", "pixel"),
                          ("on_exit", "close"), ("restart_delay", 0), ("max_restarts", 3),
                          ("env", {"A": "b"}), ("terminal", "xterm"),
                          ("terminal", {"cmd": ["foot", "--", "{command}"]}),
                          ("run", ["a", "b"]), ("title", "t")]:
            with self.subTest(key=key):
                self.assertEqual(errors_of(leaf_layout(**{key: good})), [])

    def test_terminal_template_needs_command_placeholder(self):
        self.assert_error(leaf_layout(terminal={"cmd": ["foot"]}), "{command}")
        self.assert_error(leaf_layout(terminal={"cmd": ["foot", "{command}"], "x": 1}), "only 'cmd'")

    def test_at_and_sizes(self):
        node = lambda **kw: {"layouts": [{"name": "a", "split": {"dir": "columns", **kw}}]}
        self.assert_error(node(a={}, b={}, at="1frac"), "'frac'")
        self.assert_error(node(a={}, b={}, at="abc"), "invalid size")
        self.assert_error(node(a={}, b={}, at="0%"), "positive")
        self.assertEqual(errors_of(node(a={}, b={}, at="-300px")), [])
        self.assert_error(node(children=[{}, {}], sizes=["1frac"]), "one entry per child")
        self.assert_error(node(children=[{}, {}], sizes=["1frac", "-5px"]), "sizes[1]")
        self.assertEqual(errors_of(node(children=[{}, {}], sizes=["1frac", "300px"])), [])

    def test_split_structure(self):
        node = lambda **kw: {"layouts": [{"name": "a", "split": kw}]}
        self.assert_error(node(a={}, b={}), "needs 'dir'")
        self.assert_error(node(dir="columns", children=[]), "non-empty")
        self.assert_error(node(dir="columns", children=[{}], a={}), "cannot be combined")
        self.assert_error(node(dir="columns", a={}, b={}, sizes=["1frac"]), "needs 'children'")
        self.assert_error(node(dir="diagonal", a={}, b={}), "one of")

    def test_missing_children_are_allowed(self):
        node = lambda **kw: {"layouts": [{"name": "a", "split": kw}]}
        for split in (node(dir="columns", a={"run": "x"}), node(dir="columns", b={"run": "x"}),
                      node(dir="columns"), node(dir="columns", at="40%")):
            self.assertEqual(errors_of(split), [], split)

    def test_dir_aliases_validate(self):
        for d in ("columns", "rows", "v", "vertical", "h", "horizontal"):
            node = {"layouts": [{"name": "a", "split": {"dir": d, "a": {}, "b": {}}}]}
            self.assertEqual(errors_of(node), [], d)

    def test_key_on_wrong_level(self):
        self.assert_error({"layouts": [{"name": "a", "split": {
            "dir": "columns", "run": "x", "a": {}, "b": {}}}]}, "'run' is not allowed on a split node")
        self.assert_error(leaf_layout(at_basis="visible"), "not allowed on a leaf")
        self.assert_error({"defaults": {"run": "x"}, "split": {}}, "not allowed on a defaults block")

    def test_unknown_key_warns_with_suggestion(self):
        cfg = load(leaf_layout(onexit="close"))
        self.assertEqual(len(cfg.warnings), 1)
        self.assertIn("did you mean 'on_exit'", cfg.warnings[0])

    def test_unknown_key_is_error_when_strict(self):
        self.assert_error(leaf_layout(onexit="close"), "unknown key 'onexit'", strict=True)

    def test_unknown_key_without_suggestion(self):
        cfg = load(leaf_layout(zzzzzz=1))
        self.assertNotIn("did you mean", cfg.warnings[0])

    def test_duplicate_and_reserved_ids(self):
        two = {"layouts": [{"name": "a", "split": {"dir": "columns",
               "a": {"id": "x"}, "b": {"id": "x"}}}]}
        self.assert_error(two, "duplicate id 'x'")
        self.assert_error(leaf_layout(id="1.0"), "reserved for tree paths")
        self.assert_error(leaf_layout(id="a b"), "letters, digits")
        self.assertEqual(errors_of(leaf_layout(id="htop-1")), [])

    def test_cycle_mode_needs_interval(self):
        self.assert_error(leaf_layout(mode="cycle"), "needs 'interval'")
        self.assertEqual(errors_of(leaf_layout(mode="cycle", interval=10)), [])
        self.assertIn("ignored", load(leaf_layout(interval=5)).warnings[0])

    def test_empty_with_run(self):
        self.assert_error(leaf_layout(empty=True), "cannot be combined")
        self.assertEqual(errors_of({"layouts": [{"name": "a", "split": {"empty": True}}]}), [])

    def test_monitors_block(self):
        self.assert_error({"monitors": {"a": ""}, "split": {}}, "monitors.a")
        self.assert_error({"monitors": [], "split": {}}, "mapping")


class ResolveTest(unittest.TestCase):
    @staticmethod
    def resolved(data, name=None, **kw):
        cfg = load(data)
        layout = cfg.get(name) if name else cfg.layouts[0]
        return resolve_layout(cfg, layout, **kw)

    def test_builtin_values(self):
        r = self.resolved({"split": {"run": "htop"}})
        leaf = r["split"]
        self.assertEqual((leaf["terminal"], leaf["snap"], leaf["on_exit"], leaf["margin"]),
                         ("auto", "cell", "keep", 8))
        self.assertEqual((leaf["restart_delay"], leaf["max_restarts"], leaf["mode"]), (1, 0, "sequence"))
        self.assertEqual((r["margin"], r["outer_margin"], r["at_basis"], r["area"]),
                         (8, None, "outer", "work"))
        self.assertEqual(leaf["env"], {})

    def test_precedence_leaf_over_node_over_layout_over_defaults(self):
        data = {"defaults": {"snap": "cell", "on_exit": "keep", "margin": 1, "cwd": "/d"},
                "layouts": [{"name": "a", "on_exit": "close", "margin": 2, "split": {
                    "dir": "columns", "on_exit": "restart", "margin": 3,
                    "a": {"on_exit": "keep", "margin": 4},
                    "b": {}}}]}
        r = self.resolved(data)["split"]
        a, b = r["a"], r["b"]
        self.assertEqual((a["on_exit"], a["margin"]), ("keep", 4))
        self.assertEqual((b["on_exit"], b["margin"]), ("restart", 3))
        self.assertEqual((a["snap"], a["cwd"]), ("cell", "/d"))
        self.assertEqual(self.resolved(data)["margin"], 2)

    def test_env_merges_key_by_key(self):
        data = {"defaults": {"env": {"A": "1", "B": "d"}},
                "layouts": [{"name": "a", "env": {"B": "l", "C": "l"}, "split": {
                    "dir": "columns", "env": {"C": "n"},
                    "a": {"env": {"D": "leaf"}}, "b": {}}}]}
        r = self.resolved(data)["split"]
        self.assertEqual(r["a"]["env"], {"A": "1", "B": "l", "C": "n", "D": "leaf"})
        self.assertEqual(r["b"]["env"], {"A": "1", "B": "l", "C": "n"})

    def test_outer_margin_and_area_precedence(self):
        data = {"defaults": {"outer_margin": 10, "area": "full"},
                "layouts": [{"name": "a", "split": {}},
                            {"name": "b", "outer_margin": None, "area": "work", "split": {}}]}
        a = self.resolved(data, "a")
        b = self.resolved(data, "b")
        self.assertEqual((a["outer_margin"], a["area"]), (10, "full"))
        self.assertEqual((b["outer_margin"], b["area"]), (None, "work"))

    def test_at_basis_inherits_through_split_nodes(self):
        data = {"layouts": [{"name": "a", "at_basis": "visible", "split": {
            "dir": "columns", "a": {}, "b": {
                "dir": "rows", "at_basis": "outer", "a": {}, "b": {}}}}]}
        r = self.resolved(data)
        self.assertEqual(r["at_basis"], "visible")
        self.assertEqual(r["split"]["at_basis"], "visible")
        self.assertEqual(r["split"]["b"]["at_basis"], "outer")

    def test_dir_is_made_canonical(self):
        data = {"layouts": [{"name": "a", "split": {
            "dir": "v", "a": {}, "b": {"dir": "horizontal", "a": {}, "b": {}}}}]}
        r = self.resolved(data)["split"]
        self.assertEqual((r["dir"], r["b"]["dir"]), ("columns", "rows"))

    def test_leaf_ids_explicit_or_path(self):
        data = {"layouts": [{"name": "a", "split": {
            "dir": "columns", "a": {"id": "cpu"}, "b": {"dir": "rows", "a": {}, "b": {}}}}]}
        ids = [x["id"] for x in config.iter_leaves(self.resolved(data)["split"])]
        self.assertEqual(ids, ["cpu", "1.0", "1.1"])
        self.assertEqual(self.resolved({"split": {}})["split"]["id"], "root")

    def test_leaf_keys_are_carried(self):
        data = {"layouts": [{"name": "a", "split": {
            "run": ["a", "b"], "title": "T", "id": "x", "mode": "cycle", "interval": 5,
            "when": "true", "description": "d"}}]}
        leaf = self.resolved(data)["split"]
        for key, val in [("run", ["a", "b"]), ("title", "T"), ("id", "x"), ("mode", "cycle"),
                         ("interval", 5), ("when", "true"), ("description", "d")]:
            self.assertEqual(leaf[key], val)

    def test_result_feeds_geometry(self):
        cfg = load(SAMPLE)
        r = resolve_layout(cfg, cfg.layouts[0])
        got = geometry.compute(r, geometry.Rect(0, 0, 1000, 500))
        self.assertEqual([g.id for g in got], ["0", "1.0", "1.1"])
        self.assertEqual(got[0].rect, geometry.Rect(16, 16, 577, 468))
        self.assertEqual(got[2].leaf["on_exit"], "restart")

    def test_n_way_sizes_and_default_at(self):
        data = {"layouts": [{"name": "a", "split": {
            "dir": "columns", "sizes": ["1frac", "2frac"], "children": [{}, {}]}},
            {"name": "b", "split": {"dir": "rows", "a": {}, "b": {}}}]}
        self.assertEqual(self.resolved(data, "a")["split"]["sizes"], ["1frac", "2frac"])
        self.assertEqual(self.resolved(data, "b")["split"]["at"], "50%")


class WhenTest(unittest.TestCase):
    @staticmethod
    def resolved(data, ok):
        cfg = load(data)
        return resolve_layout(cfg, cfg.layouts[0], when_eval=lambda c: c in ok)

    def tree(self):
        return {"layouts": [{"name": "a", "split": {
            "dir": "columns", "at": "60%",
            "a": {"run": "a"},
            "b": {"dir": "rows", "a": {"run": "b"}, "b": {"run": "c", "when": "gpu"}}}}]}

    def test_not_evaluated_by_default(self):
        cfg = load(self.tree())
        r = resolve_layout(cfg, cfg.layouts[0])
        self.assertEqual(len(list(config.iter_leaves(r["split"]))), 3)

    def test_true_keeps_pane(self):
        r = self.resolved(self.tree(), {"gpu"})
        self.assertEqual(len(list(config.iter_leaves(r["split"]))), 3)

    def test_false_collapses_parent_split(self):
        r = self.resolved(self.tree(), set())
        self.assertEqual([x["run"] for x in config.iter_leaves(r["split"])], ["a", "b"])
        self.assertNotIn("when", r["split"]["b"])
        self.assertEqual(r["split"]["b"]["run"], "b")

    def test_ids_come_from_the_written_tree_not_the_collapsed_one(self):
        cfg = load(self.tree())
        full = resolve_layout(cfg, cfg.layouts[0], when_eval=lambda c: True)
        cut = resolve_layout(cfg, cfg.layouts[0], when_eval=lambda c: False)
        self.assertEqual([x["id"] for x in config.iter_leaves(full["split"])], ["0", "1.0", "1.1"])
        self.assertEqual([x["id"] for x in config.iter_leaves(cut["split"])], ["0", "1.0"])

    def test_sibling_takes_the_space(self):
        r = self.resolved(self.tree(), set())
        got = geometry.compute(r, geometry.Rect(0, 0, 1000, 500))
        self.assertEqual(got[1].outer, geometry.Rect(600, 0, 400, 500))

    def test_n_way_drops_child_and_its_size(self):
        data = {"layouts": [{"name": "a", "split": {
            "dir": "columns", "sizes": ["1frac", "300px", "1frac"],
            "children": [{"run": "x"}, {"run": "y", "when": "no"}, {"run": "z"}]}}]}
        r = self.resolved(data, set())["split"]
        self.assertEqual(r["sizes"], ["1frac", "1frac"])
        self.assertEqual(len(r["children"]), 2)

    def test_n_way_with_one_child_left_is_replaced(self):
        data = {"layouts": [{"name": "a", "split": {
            "dir": "columns", "children": [{"run": "x", "when": "no"}, {"run": "z"}]}}]}
        self.assertEqual(self.resolved(data, set())["split"]["run"], "z")

    def test_all_removed_is_an_error(self):
        data = {"layouts": [{"name": "a", "split": {"run": "x", "when": "no"}}]}
        with self.assertRaises(ConfigError):
            self.resolved(data, set())

    def test_run_when_uses_exit_status(self):
        self.assertTrue(config.run_when("true"))
        self.assertFalse(config.run_when("false"))
        self.assertFalse(config.run_when("command -v definitely-not-a-command-xyz"))


class HelpersTest(unittest.TestCase):
    def test_iter_leaves_order(self):
        cfg = load(SAMPLE)
        runs = [x.get("run") for x in config.iter_leaves(cfg.layouts[0]["split"])]
        self.assertEqual(runs, ["htop", "watch -n1 sensors", "nvidia-smi -l 1"])


if __name__ == "__main__":
    unittest.main()


class EmptyPaneTest(unittest.TestCase):
    def resolved_leaves(self, split):
        cfg = config.load_text(json.dumps({"name": "e", "split": split}), "e.json")
        r = config.resolve_layout(cfg, cfg.layouts[0])
        return list(config.iter_leaves(r["split"]))

    def test_missing_or_bare_pane_is_empty(self):
        leaves = self.resolved_leaves({"dir": "columns", "b": {"run": "htop"}})
        self.assertEqual([(lf["id"], lf.get("empty", False)) for lf in leaves],
                         [("0", True), ("1", False)])
        leaves = self.resolved_leaves({"dir": "columns", "a": {}, "b": {"run": "htop"}})
        self.assertTrue(leaves[0]["empty"])

    def test_split_without_children_is_all_empty(self):
        leaves = self.resolved_leaves({"dir": "rows"})
        self.assertEqual([lf.get("empty") for lf in leaves], [True, True])
        self.assertEqual(self.resolved_leaves({})[0].get("empty"), True)

    def test_any_window_setting_asks_for_a_window(self):
        for leaf in ({"cwd": "~"}, {"title": "t"}, {"terminal": "xterm"}, {"empty": False},
                     {"env": {"A": "1"}}):
            with self.subTest(leaf=leaf):
                leaves = self.resolved_leaves({"dir": "rows", "a": leaf, "b": {}})
                self.assertNotIn("empty", leaves[0])

    def test_id_description_and_when_alone_stay_empty(self):
        for leaf in ({"id": "x"}, {"description": "spare"}, {"when": "true"}, {"empty": True},
                     {"empty": True, "title": "t"}):
            with self.subTest(leaf=leaf):
                leaves = self.resolved_leaves({"dir": "rows", "a": leaf, "b": {"run": "x"}})
                self.assertTrue(leaves[0]["empty"])

    def test_inherited_settings_do_not_fill_an_empty_pane(self):
        leaves = self.resolved_leaves({"dir": "rows", "terminal": "xterm", "cwd": "/tmp",
                                       "b": {"run": "x"}})
        self.assertTrue(leaves[0]["empty"])
