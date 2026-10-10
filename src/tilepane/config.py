"""Configuration loading, validation and resolution.

`load_file` / `load_text` parse and validate a configuration (SPEC.md section 2)
and return a `ConfigFile`. `resolve_layout` turns one layout into the form that
`geometry.compute` takes: built-in values, `defaults`, the layout and every
ancestor node are merged into each leaf, `dir` is made canonical, and `when`
conditions can be applied. The key tables below mirror the JSON schema
(`tilepane.schema.json`); a test checks that the two agree.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Optional

from . import geometry

SUPPORTED_VERSION = 1

ENUMS: dict[str, tuple[str, ...]] = {
    "snap": ("cell", "pixel"),
    "on_exit": ("keep", "close", "restart"),
    "mode": ("sequence", "cycle", "parallel"),
    "area": ("work", "full"),
    "at_basis": ("outer", "visible"),
    "dir": ("columns", "rows", "v", "vertical", "h", "horizontal"),
}
_COLUMN_NAMES = {"columns", "v", "vertical"}

# Built-in values (SPEC.md section 2). Keys with no built-in value are absent.
BUILTIN: dict[str, Any] = {
    "terminal": "auto",
    "shell": "auto",
    "margin": 8,
    "snap": "cell",
    "on_exit": "keep",
    "restart_delay": 1,
    "max_restarts": 0,
    "stop_on_error": False,
    "decorations": True,
}
BUILTIN_AT_BASIS = "outer"
BUILTIN_AREA = "work"

_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_PATH_ID_RE = re.compile(r"^\d+(\.\d+)*$")


class ConfigError(Exception):
    """The configuration cannot be used. `errors` has one message per problem."""

    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


# --- value checks: each returns an error message or None -------------------

def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _str(v: Any) -> Optional[str]:
    return None if isinstance(v, str) and v else "must be a non-empty string"


def _text(v: Any) -> Optional[str]:
    return None if isinstance(v, str) else "must be a string"


def _bool(v: Any) -> Optional[str]:
    return None if isinstance(v, bool) else "must be true or false"


def _enum(name: str) -> Callable[[Any], Optional[str]]:
    values = ENUMS[name]

    def check(v: Any) -> Optional[str]:
        if isinstance(v, str) and v in values:
            return None
        return "must be one of " + ", ".join(repr(x) for x in values)
    return check


def _number(minimum: float, *, exclusive: bool = False) -> Callable[[Any], Optional[str]]:
    def check(v: Any) -> Optional[str]:
        if not _is_num(v):
            return "must be a number"
        if v < minimum or (exclusive and v == minimum):
            return f"must be {'greater than' if exclusive else 'at least'} {minimum:g}"
        return None
    return check


def _integer(minimum: int) -> Callable[[Any], Optional[str]]:
    def check(v: Any) -> Optional[str]:
        if isinstance(v, bool) or not isinstance(v, int):
            return "must be a whole number"
        return None if v >= minimum else f"must be at least {minimum}"
    return check


def _terminal(v: Any) -> Optional[str]:
    if isinstance(v, str):
        return None if v else "must not be empty"
    if isinstance(v, dict):
        extra = sorted(set(v) - {"cmd"})
        if extra:
            return f"unknown key(s) {extra} (only 'cmd' is supported)"
        cmd = v.get("cmd")
        if not isinstance(cmd, list) or not cmd or not all(isinstance(x, str) for x in cmd):
            return "'cmd' must be a non-empty list of strings"
        if not any("{command}" in x for x in cmd):
            return "'cmd' must contain the {command} placeholder"
        return None
    return "must be a terminal name or an object with 'cmd'"


def _env(v: Any) -> Optional[str]:
    if isinstance(v, dict) and all(isinstance(k, str) and isinstance(x, str) for k, x in v.items()):
        return None
    return "must be an object with string values"


def _run(v: Any) -> Optional[str]:
    if isinstance(v, str):
        return None if v.strip() else "must not be empty"
    if isinstance(v, list) and v and all(isinstance(x, str) and x.strip() for x in v):
        return None
    return "must be a command string or a non-empty list of command strings"


def _outer_margin(v: Any) -> Optional[str]:
    return None if v is None else _number(0)(v)


def _size(allow_negative: bool, allow_frac: bool) -> Callable[[Any], Optional[str]]:
    def check(v: Any) -> Optional[str]:
        try:
            geometry.parse_size(v, "value", allow_negative=allow_negative,
                                allow_frac=allow_frac)
        except geometry.GeometryError as exc:
            return str(exc).removeprefix("value: ")
        return None
    return check


# Settings that inherit down the tree (name -> check).
INHERITED: dict[str, Callable[[Any], Optional[str]]] = {
    "terminal": _terminal,
    "shell": _str,
    "profile": _str,
    "font_size": _number(0, exclusive=True),
    "snap": _enum("snap"),
    "on_exit": _enum("on_exit"),
    "restart_delay": _number(0),
    "max_restarts": _integer(0),
    "stop_on_error": _bool,
    "decorations": _bool,
    "cwd": _str,
    "env": _env,
    "margin": _number(0),
}

_LAYOUT_ONLY: dict[str, Callable[[Any], Optional[str]]] = {
    "name": lambda v: None,   # checked separately (string or whole number)
    "split": lambda v: None,  # checked as a node
    "outer_margin": _outer_margin,
    "area": _enum("area"),
    "at_basis": _enum("at_basis"),
    "description": _text,
}
_SPLIT_ONLY: dict[str, Callable[[Any], Optional[str]]] = {
    "dir": _enum("dir"),
    "at": _size(True, False),
    "a": lambda v: None,
    "b": lambda v: None,
    "children": lambda v: None,
    "sizes": lambda v: None,
    "at_basis": _enum("at_basis"),
    "description": _text,
}
_LEAF_ONLY: dict[str, Callable[[Any], Optional[str]]] = {
    "run": _run,
    "title": _text,
    "id": _str,
    "mode": _enum("mode"),
    "interval": _number(0, exclusive=True),
    "when": _str,
    "empty": _bool,
    "description": _text,
}

FILE_KEYS = {"$schema", "version", "description", "defaults", "monitors", "layouts"}
DEFAULTS_KEYS = set(INHERITED) | {"outer_margin", "area", "at_basis"}
LAYOUT_KEYS = set(INHERITED) | set(_LAYOUT_ONLY)
SPLIT_KEYS = set(INHERITED) | set(_SPLIT_ONLY)
LEAF_KEYS = set(INHERITED) | set(_LEAF_ONLY)
# Keys that make a node a split. A node with none of them is a leaf.
SPLIT_STRUCTURE = {"dir", "a", "b", "at", "children", "sizes"}
_ALL_KEYS = FILE_KEYS | DEFAULTS_KEYS | LAYOUT_KEYS | SPLIT_KEYS | LEAF_KEYS


# --- validation -------------------------------------------------------------

class _Problems:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, path: str, msg: str) -> None:
        self.errors.append(f"{path}: {msg}" if path else msg)

    def warn(self, path: str, msg: str) -> None:
        self.warnings.append(f"{path}: {msg}" if path else msg)


def _join(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def _check_keys(obj: dict, allowed: set[str], path: str, pb: _Problems, kind: str) -> None:
    for key in obj:
        if key in allowed:
            continue
        where = _join(path, key)
        if key in _ALL_KEYS:
            pb.error(where, f"'{key}' is not allowed on a {kind}")
            continue
        hint = difflib.get_close_matches(key, sorted(allowed), n=1, cutoff=0.6)
        suffix = f" (did you mean '{hint[0]}'?)" if hint else ""
        pb.warn(where, f"unknown key '{key}'{suffix}")


def _check_values(obj: dict, checks: dict, path: str, pb: _Problems) -> None:
    for key, value in obj.items():
        check = checks.get(key)
        if check is None:
            continue
        msg = check(value)
        if msg:
            pb.error(_join(path, key), msg)


def _validate_defaults(defaults: Any, path: str, pb: _Problems) -> None:
    if not isinstance(defaults, dict):
        pb.error(path, "must be an object")
        return
    _check_keys(defaults, DEFAULTS_KEYS, path, pb, "defaults block")
    checks = {**INHERITED, "outer_margin": _outer_margin,
              "area": _enum("area"), "at_basis": _enum("at_basis")}
    _check_values(defaults, checks, path, pb)


def _validate_monitors(monitors: Any, path: str, pb: _Problems) -> None:
    if not isinstance(monitors, dict):
        pb.error(path, "must be an object mapping alias to connector name or number")
        return
    for alias, target in monitors.items():
        ok = (isinstance(target, str) and target) or (
            isinstance(target, int) and not isinstance(target, bool) and target >= 0)
        if not ok:
            pb.error(_join(path, alias), "must be a connector name or a monitor number")


def _validate_layout(layout: dict, path: str, pb: _Problems, *, flat: bool) -> None:
    allowed = LAYOUT_KEYS | (FILE_KEYS - {"layouts", "description"} if flat else set())
    _check_keys(layout, allowed, path, pb, "layout")
    _check_values(layout, {**INHERITED, **_LAYOUT_ONLY}, path, pb)
    name = layout.get("name")
    if name is not None and not (
            (isinstance(name, str) and name)
            or (isinstance(name, int) and not isinstance(name, bool) and name >= 0)):
        pb.error(_join(path, "name"), "must be a non-empty string or a whole number")
    elif name is None and not flat:
        pb.error(path, "layout needs a 'name'")
    if "split" not in layout:
        pb.error(path, "layout needs a 'split' node")
        return
    _validate_node(layout["split"], _join(path, "split"), pb, {})


def _validate_node(node: Any, path: str, pb: _Problems, ids: dict[str, str]) -> None:
    if not isinstance(node, dict):
        pb.error(path, "must be an object")
        return
    if SPLIT_STRUCTURE & node.keys():
        _validate_split(node, path, pb, ids)
    else:
        _validate_leaf(node, path, pb, ids)


def _validate_split(node: dict, path: str, pb: _Problems, ids: dict[str, str]) -> None:
    _check_keys(node, SPLIT_KEYS, path, pb, "split node")
    _check_values(node, {**INHERITED, **_SPLIT_ONLY}, path, pb)
    if "dir" not in node:
        pb.error(path, "a split needs 'dir' ('columns' or 'rows')")
    if "children" in node:
        for key in ("a", "b", "at"):
            if key in node:
                pb.error(_join(path, key), "cannot be combined with 'children'")
        children = node["children"]
        if not isinstance(children, list) or not children:
            pb.error(_join(path, "children"), "must be a non-empty list")
            return
        sizes = node.get("sizes")
        if sizes is not None:
            if not isinstance(sizes, list) or len(sizes) != len(children):
                pb.error(_join(path, "sizes"), "must be a list with one entry per child")
            else:
                check = _size(False, True)
                for i, s in enumerate(sizes):
                    msg = check(s)
                    if msg:
                        pb.error(f"{path}.sizes[{i}]", msg)
        for i, child in enumerate(children):
            _validate_node(child, f"{path}.children[{i}]", pb, ids)
        return
    if "sizes" in node:
        pb.error(_join(path, "sizes"), "needs 'children'")
    # A missing a or b is an empty pane.
    for key in ("a", "b"):
        if key in node:
            _validate_node(node[key], _join(path, key), pb, ids)


def _validate_leaf(node: dict, path: str, pb: _Problems, ids: dict[str, str]) -> None:
    _check_keys(node, LEAF_KEYS, path, pb, "leaf")
    _check_values(node, {**INHERITED, **_LEAF_ONLY}, path, pb)
    ident = node.get("id")
    if isinstance(ident, str) and ident:
        if not _ID_RE.match(ident):
            pb.error(_join(path, "id"), "may contain only letters, digits, '_', '-' and '.'")
        elif _PATH_ID_RE.match(ident):
            pb.error(_join(path, "id"), "ids made only of digits and dots are reserved for tree paths")
        elif ident in ids:
            pb.error(_join(path, "id"), f"duplicate id '{ident}' (also at {ids[ident]})")
        else:
            ids[ident] = path
    mode = node.get("mode", "sequence")
    if mode == "cycle" and "interval" not in node:
        pb.error(path, "mode 'cycle' needs 'interval'")
    if "interval" in node and mode != "cycle":
        pb.warn(_join(path, "interval"), "ignored unless mode is 'cycle'")
    if node.get("empty") is True and "run" in node:
        pb.error(path, "'empty' cannot be combined with 'run'")


# --- loading ----------------------------------------------------------------

@dataclass
class ConfigFile:
    source: str
    defaults: dict
    monitors: dict
    layouts: list[dict]
    warnings: list[str] = field(default_factory=list)

    def names(self) -> list[str]:
        return [lay["name"] for lay in self.layouts]

    def get(self, name: str) -> Optional[dict]:
        return next((lay for lay in self.layouts if lay["name"] == name), None)


def default_config_path() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "tilepane", "config.json")


def load_text(text: str, source: str = "<text>", *, strict: bool = False) -> ConfigFile:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError([f"{source}: invalid JSON at line {exc.lineno}, "
                           f"column {exc.colno}: {exc.msg}"]) from None
    pb = _Problems()
    layouts, defaults, monitors = _validate_file(data, source, pb)
    warnings = [f"{source}: {w}" for w in pb.warnings]
    errors = [f"{source}: {e}" for e in pb.errors]
    if strict:
        errors += warnings
        warnings = []
    if errors:
        raise ConfigError(errors)
    return ConfigFile(source, defaults, monitors, layouts, warnings)


def load_file(path: str, *, strict: bool = False) -> ConfigFile:
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError:
        raise ConfigError([f"{path}: file not found"]) from None
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError([f"{path}: cannot read file: {exc}"]) from None
    return load_text(text, path, strict=strict)


def _validate_file(data: Any, source: str, pb: _Problems) -> tuple[list[dict], dict, dict]:
    if not isinstance(data, dict):
        pb.error("", "the top level must be a JSON object")
        return [], {}, {}

    if "version" in data:
        v = data["version"]
        if isinstance(v, bool) or not isinstance(v, int) or v < 1:
            pb.error("version", "must be a whole number, currently 1")
        elif v > SUPPORTED_VERSION:
            pb.error("version", f"{v} is newer than this tilepane supports ({SUPPORTED_VERSION})")
    if "$schema" in data and not isinstance(data["$schema"], str):
        pb.error("$schema", "must be a string")
    defaults = data.get("defaults", {})
    if "defaults" in data:
        _validate_defaults(defaults, "defaults", pb)
    monitors = data.get("monitors", {})
    if "monitors" in data:
        _validate_monitors(monitors, "monitors", pb)
    if not isinstance(defaults, dict):
        defaults = {}
    if not isinstance(monitors, dict):
        monitors = {}

    layouts: list[dict] = []
    if "layouts" in data:
        if "split" in data:
            pb.error("", "a file cannot have both 'layouts' and a top-level 'split'")
        _check_keys(data, FILE_KEYS, "", pb, "file")
        if "description" in data and not isinstance(data["description"], str):
            pb.error("description", "must be a string")
        raw = data["layouts"]
        if not isinstance(raw, list) or not raw:
            pb.error("layouts", "must be a non-empty list of layouts")
            return [], defaults, monitors
        seen: dict[str, int] = {}
        for i, lay in enumerate(raw):
            path = f"layouts[{i}]"
            if not isinstance(lay, dict):
                pb.error(path, "must be an object")
                continue
            _validate_layout(lay, path, pb, flat=False)
            name = lay.get("name")
            if name is None:
                continue
            key = str(name)
            if key in seen:
                pb.error(_join(path, "name"), f"duplicate layout name '{key}' (also layouts[{seen[key]}])")
            seen[key] = i
            layouts.append({**lay, "name": key})
    elif "split" in data:
        flat = {k: v for k, v in data.items()
                if k not in ("$schema", "version", "defaults", "monitors")}
        _check_keys({k: v for k, v in data.items() if k in ("$schema", "version", "defaults", "monitors")},
                    FILE_KEYS, "", pb, "file")
        _validate_layout(flat, "", pb, flat=True)
        stem = os.path.splitext(os.path.basename(source))[0] or "layout"
        layouts.append({**flat, "name": str(flat.get("name", stem))})
    else:
        pb.error("", "needs 'layouts' (a list) or a top-level 'split'")
    return layouts, defaults, monitors


# --- tree helpers -----------------------------------------------------------

def is_leaf(node: dict) -> bool:
    return not (SPLIT_STRUCTURE & node.keys())


# Leaf keys that do not ask for a window on their own: a leaf with nothing
# else (or no leaf at all, a missing a or b) is an empty pane.
_NO_WINDOW_KEYS = {"id", "description", "when", "empty"}


def wants_window(leaf: dict) -> bool:
    """Does this leaf, as written, get a terminal window?"""
    if "empty" in leaf:
        return leaf["empty"] is not True
    return bool(leaf.keys() - _NO_WINDOW_KEYS)


def children(node: dict) -> list[dict]:
    """The child nodes of a split; a missing a or b is an empty leaf."""
    if "children" in node:
        return node["children"]
    return [node.get("a", {}), node.get("b", {})]


def iter_leaves(node: dict) -> Iterator[dict]:
    if is_leaf(node):
        yield node
        return
    for child in children(node):
        yield from iter_leaves(child)


# --- resolution -------------------------------------------------------------

def _merge(inherited: dict, node: dict) -> dict:
    out = dict(inherited)
    for key in INHERITED:
        if key not in node:
            continue
        if key == "env":
            out["env"] = {**inherited.get("env", {}), **node["env"]}
        else:
            out[key] = node[key]
    return out


def path_id(path: tuple[int, ...]) -> str:
    """Tree-path id of a leaf in the written layout: "root", "0", "1.0", ..."""
    return ".".join(map(str, path)) if path else "root"


def _resolve_node(node: dict, inherited: dict, at_basis: str, path: tuple[int, ...]) -> dict:
    eff = _merge(inherited, node)
    if is_leaf(node):
        leaf = dict(eff)
        leaf.setdefault("env", {})
        leaf["mode"] = node.get("mode", "sequence")
        for key in ("run", "title", "interval", "when", "description"):
            if key in node:
                leaf[key] = node[key]
        if not wants_window(node):
            leaf["empty"] = True
        # Every resolved leaf has an id: the explicit one, or its path in the
        # written tree. The path is taken before `when` removes panes, so ids
        # stay the same whether or not a sibling is left out.
        leaf["id"] = node.get("id", path_id(path))
        return leaf

    basis = node.get("at_basis", at_basis)
    out: dict[str, Any] = {
        "dir": "columns" if node["dir"] in _COLUMN_NAMES else "rows",
        "margin": eff["margin"],
        "at_basis": basis,
    }
    if "children" in node:
        out["children"] = [_resolve_node(c, eff, basis, path + (i,))
                           for i, c in enumerate(node["children"])]
        if "sizes" in node:
            out["sizes"] = list(node["sizes"])
    else:
        out["at"] = node.get("at", "50%")
        a, b = children(node)
        out["a"] = _resolve_node(a, eff, basis, path + (0,))
        out["b"] = _resolve_node(b, eff, basis, path + (1,))
    return out


def _collapse(node: dict, when_eval: Callable[[str], bool]) -> Optional[dict]:
    """Remove panes whose `when` fails; a split left with one child is replaced by it."""
    if is_leaf(node):
        cond = node.get("when")
        return node if cond is None or when_eval(cond) else None
    if "children" in node:
        sizes = node.get("sizes")
        kept, kept_sizes = [], []
        for i, child in enumerate(node["children"]):
            res = _collapse(child, when_eval)
            if res is not None:
                kept.append(res)
                if sizes is not None:
                    kept_sizes.append(sizes[i])
        if len(kept) <= 1:
            return kept[0] if kept else None
        out = dict(node, children=kept)
        if sizes is not None:
            out["sizes"] = kept_sizes
        return out
    a, b = _collapse(node["a"], when_eval), _collapse(node["b"], when_eval)
    if a is None or b is None:
        return a if b is None else b
    return dict(node, a=a, b=b)


def run_when(command: str) -> bool:
    """Evaluate a `when` condition: true when the shell command exits with 0."""
    try:
        return subprocess.run(command, shell=True, capture_output=True,
                              timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def resolve_layout(cfg: ConfigFile, layout: dict, *,
                   when_eval: Optional[Callable[[str], bool]] = None) -> dict:
    """Merge defaults and inheritance into `layout`; ready for `geometry.compute`.

    `when_eval` decides `when` conditions. With None, conditions are not
    evaluated and every pane is kept.
    """
    base = _merge(dict(BUILTIN), cfg.defaults)
    base = _merge(base, layout)

    def pick(key: str, builtin: Any) -> Any:
        if key in layout:
            return layout[key]
        return cfg.defaults.get(key, builtin)

    at_basis = pick("at_basis", BUILTIN_AT_BASIS)
    split = _resolve_node(layout["split"], base, at_basis, ())
    if when_eval is not None:
        split = _collapse(split, when_eval)
        if split is None:
            raise ConfigError([f"{cfg.source}: layout '{layout['name']}': "
                               "every pane was removed by its 'when' condition"])
    return {
        "name": layout["name"],
        "margin": base["margin"],
        "outer_margin": pick("outer_margin", None),
        "at_basis": at_basis,
        "area": pick("area", BUILTIN_AREA),
        "split": split,
    }
