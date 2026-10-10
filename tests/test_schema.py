import json
import unittest
from pathlib import Path

from tilepane import config, docgen

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = docgen.load_schema()
DEFS = SCHEMA["definitions"]


def props(level):
    return set(DEFS[level]["properties"])


class SchemaMatchesValidatorTest(unittest.TestCase):
    """The hand-written validator and the JSON schema must know the same keys."""

    def test_root_keys(self):
        self.assertEqual(set(SCHEMA["properties"]), config.FILE_KEYS | config.LAYOUT_KEYS)

    def test_defaults_keys(self):
        self.assertEqual(props("defaults"), config.DEFAULTS_KEYS)

    def test_layout_keys(self):
        self.assertEqual(props("layout"), config.LAYOUT_KEYS)

    def test_split_keys(self):
        self.assertEqual(props("split"), config.SPLIT_KEYS)

    def test_leaf_keys(self):
        self.assertEqual(props("leaf"), config.LEAF_KEYS)

    def test_split_structure_keys_match_node_condition(self):
        cond = {next(iter(c["required"])) for c in DEFS["node"]["if"]["anyOf"]}
        self.assertEqual(cond, config.SPLIT_STRUCTURE)

    def test_every_property_has_description(self):
        for level in ("defaults", "layout", "split", "leaf"):
            for key, prop in DEFS[level]["properties"].items():
                kd = docgen._key_def(SCHEMA, prop)
                self.assertTrue(kd.get("description"), f"{level}.{key} has no description")
        for key, prop in SCHEMA["properties"].items():
            kd = docgen._key_def(SCHEMA, prop)
            self.assertTrue(kd.get("description"), f"root {key} has no description")

    def test_enums_match(self):
        for name, values in config.ENUMS.items():
            self.assertEqual(tuple(DEFS[f"key-{name}"]["enum"]), values, name)

    def test_inherits_flag_matches(self):
        flagged = {k for k, v in DEFS.items()
                   if k.startswith("key-") and v.get("x-inherits") is True}
        self.assertEqual(flagged, {f"key-{k}" for k in config.INHERITED})

    def test_defaults_match_builtin_values(self):
        for key, value in config.BUILTIN.items():
            self.assertEqual(DEFS[f"key-{key}"].get("default"), value, key)
        self.assertEqual(DEFS["key-at_basis"]["default"], config.BUILTIN_AT_BASIS)
        self.assertEqual(DEFS["key-area"]["default"], config.BUILTIN_AREA)
        self.assertIsNone(DEFS["key-outer_margin"]["default"])
        self.assertEqual(DEFS["key-mode"]["default"], "sequence")
        self.assertEqual(DEFS["key-at"]["default"], "50%")

    def test_version_matches(self):
        self.assertEqual(DEFS["key-version"]["enum"], [config.SUPPORTED_VERSION])

    def test_all_refs_resolve(self):
        text = json.dumps(SCHEMA)
        for ref in {part.split('"')[0] for part in text.split('"$ref": "')[1:]}:
            target = SCHEMA
            for part in ref.removeprefix("#/").split("/"):
                target = target[part]

    def test_schema_examples_validate(self):
        # Every example value of a leaf-level key passes the validator.
        for key in config.LEAF_KEYS:
            kd = DEFS.get(f"key-{key}")
            for example in (kd or {}).get("examples", []):
                data = {"layouts": [{"name": "x", "split": {key: example}}]}
                if key == "interval":
                    data["layouts"][0]["split"]["mode"] = "cycle"
                if key == "empty":
                    continue
                config.load_text(json.dumps(data), "example")


class DocsTest(unittest.TestCase):
    def test_config_md_is_up_to_date(self):
        path = ROOT / "docs" / "CONFIG.md"
        self.assertTrue(path.exists(), "run: python -m tilepane.docgen")
        self.assertEqual(path.read_text(encoding="utf-8"), docgen.render(),
                         "docs/CONFIG.md is stale; run: python -m tilepane.docgen")

    def test_every_key_is_documented(self):
        text = docgen.render()
        for key in docgen.all_keys():
            self.assertIn(f"| `{key}` |", text, key)
        self.assertEqual(set(docgen.all_keys()),
                         config.FILE_KEYS | config.LAYOUT_KEYS | config.SPLIT_KEYS | config.LEAF_KEYS
                         | config.DEFAULTS_KEYS)

    def test_explain_known_key(self):
        out = docgen.explain("on_exit")
        self.assertIn("Used in:", out)
        self.assertIn("leaf", out)
        self.assertIn('"keep"', out)
        self.assertIn("Inherits:  yes", out)

    def test_explain_unknown_key(self):
        self.assertIsNone(docgen.explain("nonsense"))
        self.assertIn("on_exit", docgen.suggest("onexit"))


if __name__ == "__main__":
    unittest.main()
