# Architecture

```
deskworks/
  deskmap/           library: the desktop model and the window system backends
  tilepane/          tool: terminal windows at exact positions
  cascade-windows/   tool: Windows-style cascade
  docs/              repository level documents
  scripts/           repository level scripts (test-all.sh)
```

## Layers

```
 tilepane          cascade-windows        (future tools)
     \                  |                  /
      +-------------- deskmap ------------+
                          |
        X11 (EWMH, python-xlib)    GNOME Shell extension (D-Bus)
```

- **Tools** hold what is specific to them: tilepane's layouts, terminals and
  state; cascade's ordering and exclusion rules, menus and shortcuts.
- **deskmap** holds what every tool needs to know about the desktop. It has no
  knowledge of any tool.
- **Backends** are the only code that talks to a window system.

## Dependency rules

1. A tool may import `deskmap`. `deskmap` never imports a tool.
2. Tools never import each other.
3. Pure logic (geometry, numbering, planning) must not import python-xlib, so it stays unit-testable.
4. Window system access sits behind one backend interface. Tests use a fake backend.
5. The standard library is enough for everything except the X11 backend, which needs the optional `python-xlib`.

## What belongs in deskmap

- `Rect`, `Monitor`, the numbering rules for monitors and workspaces.
- Per-monitor work area (monitor minus panels and docks).
- Workspace model: sequence, grid, Compiz-style viewports, conversion between the window manager's index and the person's number.
- Window information and operations: list, move, resize, raise, unmaximize, close, find new windows.
- Frame, shadow and size-hint handling that makes placement exact.
- Environment report (`--doctor` style) that explains why something does not work.
- The backends: X11 first, then the GNOME Shell extension protocol.

## What stays in the tools

- tilepane: layout JSON, splits, terminal adapters, `runner.py`, state file, editor.
- cascade-windows: cascade geometry, scopes, undo, exclusions, Nemo actions, shortcut installation, the GNOME extension's panel menu.

## Coordinates

The coordinate model is the one tilepane uses today: desktop coordinates with
`workspace_offset(desktop)` for window managers that lay workspaces out as
viewports of one large desktop. cascade-windows currently uses coordinates
relative to one workspace cell; it keeps that model on top of the library.
See [DECISIONS.md](DECISIONS.md), decision 3.
