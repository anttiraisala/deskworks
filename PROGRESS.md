# Progress log

Implementation follows the order in SPEC.md section 7. Newest entries last.

## Status

| Step | Description | State |
|---|---|---|
| 1 | `--doctor`, `--monitors`, project skeleton | done |
| 2 | Geometry core + unit tests | next |
| 3 | Config loading, validation, `--dry-run` | pending |
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
