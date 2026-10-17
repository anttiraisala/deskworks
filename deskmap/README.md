# deskmap

A small Python library that understands the Linux desktop: which monitors there
are, how the workspaces are arranged, where panels leave room for windows, and
what size a window must be asked for so that it ends up exactly where wanted.

It is the shared base of the tools in this repository ([`tilepane`](../tilepane/),
[`cascade-windows`](../cascade-windows/)). It is being extracted from them; see
[../docs/DESKMAP.md](../docs/DESKMAP.md) for what is already here and what is next.

## Requirements

| What | Why | Ubuntu / Mint package |
|---|---|---|
| Python 3.9 or newer | the library | `python3` |
| xrandr | finds the monitors on X11 | `x11-xserver-utils` |
| python-xlib (optional, `[x11]` extra) | talks to the X server (the X11 backend) | installed by pip |

## Numbering

- Monitors: left to right, then top to bottom (`monitors.number_monitors`).
- Workspaces: from the bottom left, left to right, then row by row upwards (`workspaces.Numbering`). The window manager's own order is converted in one place.

## Contents so far

| Module | What it does |
|---|---|
| `rect` | `Rect`, the rectangle type |
| `monitors` | detects monitors (xrandr, sway, Hyprland), numbers them, resolves names, numbers and aliases |
| `workspaces` | workspace grids, Compiz-style viewports, conversion between the window manager's index and the person's number |
| `workarea` | per-monitor work area: `_GTK_WORKAREAS`, panel struts, `_NET_WORKAREA`, whole monitor |
| `placement` | frame, shadow and size-hint arithmetic for exact window placement |
| `backends` | the backend interface: `Backend`, `WindowInfo`, `Placement`, `BackendError` |
| `backends.x11` | the X11 backend on python-xlib and EWMH: finds new windows, places them exactly, moves them between workspaces and closes them; workspace and Compiz viewport handling |

## Install and test

```
pip install -e '.[x11]'
PYTHONPATH=src:. python3 -m unittest discover -s tests -t .
```
