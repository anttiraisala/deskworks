"""Write tests/vectors/geometry.json: layouts and the rectangles geometry.py gives.

The editor's JavaScript geometry is checked against the same file
(tests/test_editor.py), so the two implementations cannot drift apart.
Regenerate after a deliberate change to geometry.py:

    PYTHONPATH=src:. python3 -m tests.make_vectors
"""

import json
import random
from pathlib import Path

from tilepane import geometry
from tilepane.geometry import Rect

OUT = Path(__file__).with_name("vectors") / "geometry.json"

HANDWRITTEN = [
    ("two columns", {"margin": 8, "split": {"dir": "columns", "at": "60%", "a": {}, "b": {}}}),
    ("odd margin", {"margin": 7, "split": {"dir": "rows", "at": "300px", "a": {}, "b": {}}}),
    ("from the end", {"margin": 8, "split": {"dir": "columns", "at": "-300px", "a": {}, "b": {}}}),
    ("negative percent", {"margin": 4, "split": {"dir": "rows", "at": "-25%", "a": {}, "b": {}}}),
    ("outer margin", {"margin": 8, "outer_margin": 16,
                      "split": {"dir": "columns", "a": {}, "b": {"dir": "rows", "a": {}, "b": {}}}}),
    ("visible basis", {"margin": 10, "at_basis": "visible",
                       "split": {"dir": "columns", "at": "400px", "a": {}, "b": {}}}),
    ("node margin", {"margin": 8, "split": {"dir": "columns", "a": {"margin": 0},
                                            "b": {"margin": 20, "dir": "rows", "a": {}, "b": {}}}}),
    ("n-way", {"margin": 6, "split": {"dir": "columns", "sizes": ["1frac", "2frac", "300px"],
                                      "children": [{}, {}, {}]}}),
    ("n-way no frac", {"margin": 6, "split": {"dir": "rows", "sizes": ["20%", "100px"],
                                              "children": [{}, {}]}}),
    ("aliases", {"margin": 8, "split": {"dir": "v", "a": {}, "b": {"dir": "h", "a": {}, "b": {}}}}),
    ("bare number at", {"margin": 8, "split": {"dir": "columns", "at": 250, "a": {}, "b": {}}}),
    ("single leaf", {"margin": 12, "split": {}}),
    ("too big", {"margin": 8, "split": {"dir": "columns", "at": "5000px", "a": {}, "b": {}}}),
    ("too small", {"margin": 40, "split": {"dir": "columns", "at": "30px", "a": {}, "b": {}}}),
    ("oversize sizes", {"split": {"dir": "rows", "sizes": ["70%", "40%"], "children": [{}, {}]}}),
    ("frac in at", {"split": {"dir": "rows", "at": "1frac", "a": {}, "b": {}}}),
    ("bad dir", {"split": {"dir": "diagonal", "a": {}, "b": {}}}),
]


def random_size(rng, allow_negative):
    kind = rng.choice(["%", "px", "frac"] if not allow_negative else ["%", "px", "-%", "-px"])
    if kind.endswith("%"):
        value = rng.choice([rng.randint(10, 90), round(rng.uniform(10, 90), 2)])
        return f"-{value}%" if kind.startswith("-") else f"{value}%"
    if kind.endswith("px"):
        value = rng.randint(40, 700)
        return f"-{value}px" if kind.startswith("-") else rng.choice([f"{value}px", value])
    return f"{rng.choice([1, 2, 3, 0.5, 1.5])}frac"


def random_node(rng, depth):
    if depth == 0 or rng.random() < 0.3:
        node = {}
        if rng.random() < 0.15:
            node["margin"] = rng.randint(0, 21)
        return node
    node = {"dir": rng.choice(["columns", "rows", "v", "h"])}
    if rng.random() < 0.1:
        node["margin"] = rng.randint(0, 21)
    if rng.random() < 0.1:
        node["at_basis"] = rng.choice(["outer", "visible"])
    if rng.random() < 0.35:
        n = rng.randint(2, 4)
        node["children"] = [random_node(rng, depth - 1) for _ in range(n)]
        if rng.random() < 0.8:
            node["sizes"] = [random_size(rng, False) for _ in range(n)]
    else:
        if rng.random() < 0.9:
            node["at"] = random_size(rng, True)
        node["a"] = random_node(rng, depth - 1)
        node["b"] = random_node(rng, depth - 1)
    return node


def case(name, layout, area):
    try:
        leaves = geometry.compute(layout, area)
    except geometry.GeometryError:
        expected = None
    else:
        expected = [[lr.id, lr.rect.x, lr.rect.y, lr.rect.width, lr.rect.height,
                     lr.outer.x, lr.outer.y, lr.outer.width, lr.outer.height] for lr in leaves]
    return {"name": name, "layout": layout,
            "area": [area.x, area.y, area.width, area.height], "expected": expected}


def build():
    rng = random.Random(20261010)
    cases = [case(name, layout, Rect(0, 0, 1920, 1080)) for name, layout in HANDWRITTEN]
    areas = [Rect(0, 0, 1920, 1080), Rect(1920, 0, 2560, 1440), Rect(65, 27, 1855, 1053),
             Rect(0, 0, 1366, 768), Rect(3840, 1080, 1080, 1920)]
    for i in range(400):
        layout = {"split": random_node(rng, rng.randint(1, 5))}
        if rng.random() < 0.9:
            layout["margin"] = rng.randint(0, 21)
        if rng.random() < 0.25:
            layout["outer_margin"] = rng.randint(0, 40)
        if rng.random() < 0.15:
            layout["at_basis"] = "visible"
        cases.append(case(f"random {i}", layout, rng.choice(areas)))
    return cases


def main():
    cases = build()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(cases, separators=(",", ":")) + "\n")
    ok = sum(1 for c in cases if c["expected"] is not None)
    print(f"wrote {OUT}: {len(cases)} cases ({ok} laid out, {len(cases) - ok} errors)")


if __name__ == "__main__":
    main()
