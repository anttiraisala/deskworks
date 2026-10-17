"""Documentation generated from the JSON schema.

`python -m tilepane.docgen` writes docs/CONFIG.md and the copy of the schema
embedded in the editor (editor/editor.html); `--check` fails when either is out
of date. `explain(key)` backs `tilepane --explain KEY`.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

SCHEMA_PATH = Path(__file__).with_name("tilepane.schema.json")
EDITOR_PATH = Path(__file__).parent / "editor" / "editor.html"
_EDITOR_SCHEMA = re.compile(r'(<script id="schema" type="application/json">\n).*?(\n</script>)', re.S)
LEVELS = [
    ("defaults", "defaults block"),
    ("layout", "layout"),
    ("split", "split node"),
    ("leaf", "leaf"),
]
_TYPE_NAMES = {"integer": "whole number", "number": "number", "string": "string",
               "boolean": "true or false", "object": "object", "array": "list",
               "null": "null"}


def load_schema() -> dict:
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _deref(schema: dict, node: dict) -> dict:
    ref = node.get("$ref")
    if not ref:
        return node
    target: Any = schema
    for part in ref.removeprefix("#/").split("/"):
        target = target[part]
    return target


def _key_def(schema: dict, prop: dict) -> dict:
    """The key definition behind a property (follows the shared key-* reference)."""
    return _deref(schema, prop)


def _type_of(schema: dict, s: dict) -> str:
    if "$ref" in s:
        name = s["$ref"].rsplit("/", 1)[-1]
        return {"node": "node (split or leaf)", "layout": "layout", "defaults": "object"}.get(name, name)
    if "enum" in s:
        return ", ".join(f'`{json.dumps(v)}`' for v in s["enum"])
    if "oneOf" in s:
        return " or ".join(_type_of(schema, o) for o in s["oneOf"])
    t = s.get("type")
    if isinstance(t, list):
        return " or ".join(_TYPE_NAMES.get(x, x) for x in t)
    if t == "array":
        items = s.get("items")
        inner = _type_of(schema, items) if items else "values"
        return f"list of {inner}"
    if t == "object":
        return "object"
    return _TYPE_NAMES.get(t, str(t))


def _default(kd: dict) -> str:
    return f"`{json.dumps(kd['default'])}`" if "default" in kd else "none"


def _inherits(kd: dict) -> str:
    v = kd.get("x-inherits")
    if v is True:
        return "yes"
    return str(v) if v else "no"


def _examples(kd: dict) -> str:
    return ", ".join(f"`{json.dumps(e)}`" for e in kd.get("examples", []))


def _level_props(schema: dict, level: str) -> dict:
    return _deref(schema, {"$ref": f"#/definitions/{level}"})["properties"]


def _file_keys(schema: dict) -> list[str]:
    layout = _level_props(schema, "layout")
    keys = [k for k in schema["properties"] if k not in layout]
    keys.insert(keys.index("version") + 1, "description")
    return keys


def _row(schema: dict, key: str, prop: dict) -> str:
    kd = _key_def(schema, prop)
    desc = kd["description"].replace("|", "\\|")
    ex = _examples(kd)
    if ex:
        desc += f" Examples: {ex}."
    typ = _type_of(schema, kd).replace("|", "\\|")
    return f"| `{key}` | {typ} | {_default(kd)} | {_inherits(kd)} | {desc} |"


def _table(schema: dict, keys_props: list[tuple[str, dict]]) -> list[str]:
    out = ["| Key | Type | Default | Inherits | Description |", "|---|---|---|---|---|"]
    out += [_row(schema, k, p) for k, p in keys_props]
    return out


def render() -> str:
    schema = load_schema()
    root = schema["properties"]
    out: list[str] = []
    add = out.append

    add("# Configuration reference")
    add("")
    add("<!-- Generated from src/tilepane/tilepane.schema.json by `python -m tilepane.docgen`. Do not edit by hand. -->")
    add("")
    add("Every key tilepane understands, by level. The JSON schema is the source of truth; "
        "`tilepane --explain KEY` prints the same description in a terminal, and editors "
        "such as VS Code show it as a tooltip when the file has a `$schema` key. "
        "Behavior is described in [SPEC.md](../SPEC.md).")
    add("")
    add("## How a file is organised")
    add("")
    add("A file holds one or more **layouts**. A layout is a tree: a **split node** divides "
        "its area between children, a **leaf** is one rectangle (a pane) that normally gets "
        "one terminal window.")
    add("")
    add("- A file with a `layouts` list holds several layouts; choose one with `--layout NAME` "
        "or by naming it after the file.")
    add("- A file with a top-level `split` is a single layout. The layout keys (`name`, "
        "`margin`, `split`, ...) then go at the top level, and `name` defaults to the file name.")
    add("- A file cannot have both `layouts` and a top-level `split`.")
    add("")
    add("```json")
    add('{')
    add('  "$schema": "https://raw.githubusercontent.com/anttiraisala/tilepane/master/src/tilepane/tilepane.schema.json",')
    add('  "name": "cpu-dash",')
    add('  "margin": 8,')
    add('  "split": {')
    add('    "dir": "columns", "at": "60%",')
    add('    "a": { "run": "htop", "title": "htop" },')
    add('    "b": { "run": "watch -n1 sensors", "when": "command -v sensors" }')
    add('  }')
    add('}')
    add("```")
    add("")
    add("## Inheritance and precedence")
    add("")
    add("Keys marked **Inherits** apply down the tree. The effective value for a leaf is the "
        "first one found in this order: the leaf, its ancestor split nodes (nearest first), "
        "the layout, the file's `defaults`, the built-in value. `env` is merged key by key "
        "instead of replaced. `at_basis` inherits through split nodes only. `outer_margin` "
        "and `area` are set on the layout or in `defaults`. Keys that are not marked never "
        "inherit.")
    add("")
    add("## Size values")
    add("")
    add("`at` and the entries of `sizes` use these forms:")
    add("")
    add("- `\"60%\"`: a percentage of the area being split (before margins).")
    add("- `\"300px\"` or `300`: pixels. A bare number means pixels.")
    add("- `\"2frac\"`: a share of the space left after the fixed sizes, divided in proportion "
        "(`sizes` only).")
    add("- A negative `at` (`\"-300px\"`, `\"-40%\"`) is measured from the right or bottom.")
    add("")
    add("## Validation")
    add("")
    add("A file is validated when it is loaded; all problems are reported together with "
        "their key path (for example `layouts[0].split.b.run`). An unknown key is a warning "
        "with a suggestion; `--strict` makes it an error. A key on the wrong level (for "
        "example `run` on a split node) is an error.")

    add("")
    add("## File")
    add("")
    add("Top level of the file. " + schema["description"])
    add("")
    out += _table(schema, [(k, root[k]) for k in _file_keys(schema)])

    descriptions = {
        "defaults": "The `defaults` block. Values here apply when nothing nearer sets them.",
        "layout": "One layout (an entry of `layouts`, or the top level of a single-layout file).",
        "split": "A split node: a node that has `dir`.",
        "leaf": "A leaf: a node with none of the split keys.",
    }
    titles = {"defaults": "Defaults", "layout": "Layout", "split": "Split node", "leaf": "Leaf"}
    for level, _ in LEVELS:
        add("")
        add(f"## {titles[level]}")
        add("")
        add(descriptions[level])
        add("")
        out += _table(schema, list(_level_props(schema, level).items()))

    mon = schema["definitions"]["monitors"]
    add("")
    add("## Monitors")
    add("")
    add(mon["description"] + " Example: " + _examples(mon) + ".")
    return "\n".join(out) + "\n"


def explain(key: str) -> Optional[str]:
    """Describe `key` for `tilepane --explain`, or None if the key is unknown."""
    schema = load_schema()
    where: list[str] = []
    prop: Optional[dict] = None
    if key in _file_keys(schema):
        where.append("file")
        prop = schema["properties"][key]
    for level, label in LEVELS:
        props = _level_props(schema, level)
        if key in props:
            where.append(label)
            prop = prop or props[key]
    if prop is None:
        return None
    kd = _key_def(schema, prop)
    lines = [key, f"  Used in:   {', '.join(where)}"]
    lines.append(f"  Type:      {_type_of(schema, kd)}".replace("`", ""))
    lines.append(f"  Default:   {_default(kd)}".replace("`", ""))
    lines.append(f"  Inherits:  {_inherits(kd)}")
    lines.append("")
    lines.append("  " + kd["description"])
    if kd.get("examples"):
        lines.append("")
        lines.append("  Examples:  " + _examples(kd).replace("`", ""))
    return "\n".join(lines)


def all_keys() -> list[str]:
    schema = load_schema()
    keys = set(_file_keys(schema))
    for level, _ in LEVELS:
        keys |= set(_level_props(schema, level))
    return sorted(keys)


def suggest(key: str) -> list[str]:
    return difflib.get_close_matches(key, all_keys(), n=3, cutoff=0.5)


def editor_html() -> str:
    """editor.html with the current schema embedded."""
    html = EDITOR_PATH.read_text(encoding="utf-8")
    schema = SCHEMA_PATH.read_text(encoding="utf-8").rstrip().replace("</", "<\\/")
    new, n = _EDITOR_SCHEMA.subn(lambda m: m.group(1) + schema + m.group(2), html, count=1)
    if n != 1:
        raise RuntimeError(f"{EDITOR_PATH}: schema block not found")
    return new


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="python -m tilepane.docgen",
                                description="Generate docs/CONFIG.md from the JSON schema.")
    p.add_argument("--output", default="docs/CONFIG.md")
    p.add_argument("--check", action="store_true",
                   help="exit 1 if the output file is missing or out of date")
    args = p.parse_args(argv)
    outputs = [(Path(args.output), render()), (EDITOR_PATH, editor_html())]
    if args.check:
        stale = [p for p, text in outputs if not p.exists() or p.read_text(encoding="utf-8") != text]
        for p in stale:
            print(f"{p} is out of date; run: python -m tilepane.docgen", file=sys.stderr)
        return 1 if stale else 0
    for path, text in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
