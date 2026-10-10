# Progress log

Implementation follows the order in SPEC.md section 7. Newest entries last.

## Status

| Step | Description | State |
|---|---|---|
| 1 | `--doctor`, `--monitors`, project skeleton | done |
| 2 | Geometry core + unit tests | done |
| 3 | Config loading, validation, `--dry-run` | next |
| 4 | One backend end to end (X11 / python-xlib, gnome-terminal) | pending |
| 5 | Monitor support, multi-task command lines | pending |
| 6 | `on_exit`, `snap`, state management, `--close` / `--toggle` | pending |
| 7 | `--demo` | pending |
| 8 | Browser editor | pending |
| 9 | README, installation, example configuration | pending |

## Log

### 2026-10-10: step 1
- Environment on the dev machine: Ubuntu 24.04, X11, Unity 7 / Compiz, python-xlib 0.33, gnome-terminal 3.52, xterm; no xdotool/wmctrl/kitty/alacritty.
- Four monitors; tilepane numbering (left to right, then top to bottom) differs from xrandr's.
- Backend decision: swappable backends. X11 via python-xlib first. Wayland backends (sway/Hyprland IPC, KWin script, GNOME Shell extension) are recognised by `--doctor` but not yet implemented. Goal: work across window managers.
- Sway and Hyprland monitor parsing is tested only against synthetic JSON.
- Run tests: `PYTHONPATH=src python3 -m unittest discover -s tests`.

### 2026-10-10: step 2
- `src/tilepane/geometry.py`: `compute(layout, area) -> list[LeafRect]`, pure, takes the layout as a parsed JSON dict. Binary `a`/`b`/`at` and N-way `children`/`sizes` share one code path (binary is converted to a two-entry sizes list).
- Odd margins are split floor/ceil (start side gets the floor) so the gap between neighbours is exactly `margin`.
- `outer_margin` shrinks the area first; leaves on the outer edge get no extra inset (tested: edge is not counted twice).
- Boundaries are rounded once and shared by neighbours; a random-tree property test checks exact tiling, no overlaps and exact gaps.
- Choices not fixed by the spec: without an `fr` entry the last child absorbs leftover space; oversize sizes, empty panes and panes smaller than their margins raise `GeometryError`; `at_basis: "visible"` uses the split node's margin.
- `dir` follows the spec: `v` = children side by side, `h` = stacked. This is the opposite of tmux's `-h`/`-v` naming, so the README must state it clearly.
- Defaults (`defaults.margin` etc.) are not applied inside `compute`; step 3 merges them into the layout before calling.
- 67 tests pass.
