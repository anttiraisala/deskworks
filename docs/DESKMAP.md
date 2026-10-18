# deskmap

The shared library. This document is the plan for extracting it; update it as
the extraction proceeds, and move finished facts into the library's own README.

## Source of each part

| Part | Comes from | Notes |
|---|---|---|
| `Rect` | `tilepane/src/tilepane/geometry.py` | tilepane's `Rect`; cascade's extra helpers (`intersect`, `contains`, `distance_sq`, `to_list`, `from_list`, `__str__`) were added; both tools use it |
| Monitor detection and numbering | `tilepane/.../monitors.py` | xrandr, sway, hyprland parsing; `resolve` (numbers, connectors, aliases, `primary`, `all`) moved along unchanged, separating it from detection is open |
| Work area | `tilepane/.../workarea.py` | `_GTK_WORKAREAS`, struts, `_NET_WORKAREA` |
| Workspace model and numbering | `tilepane/.../workspaces.py` | the numbering of README.md |
| Placement maths | `tilepane/.../placement.py` | frame extents, size hints, cell snap |
| X11 backend | `tilepane/.../backends/x11.py` (moved to `deskmap/src/deskmap/backends/x11.py`) | placement, find new window, close, desktops; window listing and the cascade operations come from `cascade-windows/cascade_windows/x11_backend.py` |
| Window listing, kinds, flags | `cascade-windows/.../model.py`, `x11_backend.py` | dialog, minimized, fullscreen, sticky, stacking order |
| GNOME backend and protocol | `cascade-windows/.../gnome_backend.py`, `shell_protocol.py`, `gnome-extension/` | moved last |
| Environment report | `tilepane/.../doctor.py`, `cascade-windows/.../environment.py` | merged |
| Fake window manager for tests | `cascade-windows/tests/fake_wm.py`, `fake_backend.py` | |

## Extraction order

State on 2026-10-18: the X11 backend also lists the open windows (`open_windows`: visible rectangle on the window's own workspace, class, process, title, kind, minimized, bottom-to-top order), the active window and the pointer, which tilepane's `--analyze` uses; cascade-windows has its own, richer listing that is not merged yet.

State on 2026-10-17: steps 1 and 2 are done and tilepane uses the pure parts and the X11 backend from the library (part of step 3). cascade-windows uses `Rect` and the workspace numbering rule from the library (start of step 4); its own X11 backend, which is richer in some places (dock windows, struts per monitor), is not merged yet because that needs live comparison on Mint and Unity. See `PROGRESS.md`.

1. Create the `deskmap` package with the pure parts and their tests (`Rect`, monitors, workspaces, work area, placement maths). Keep the tests that exist.
2. Move the X11 backend; keep tilepane's live tests green.
3. Make tilepane import `deskmap` and delete its copies. All tilepane tests must pass unchanged in meaning; verify live on Mint.
4. Add window listing and the cascade operations; make cascade-windows import `deskmap` and delete its copies.
5. Move the GNOME backend and design the extension protocol so that it also offers "new window" events and close, which tilepane needs.

## Rules

- No behaviour change while moving code. A move and a change are separate commits.
- Every moved module takes its tests with it.
- The tools' documented behaviour must stay true after each step.
