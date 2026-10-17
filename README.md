# deskworks

Small Linux desktop tools that share one understanding of the desktop: which
monitors there are, how the workspaces are arranged, and where windows may go.

| Folder | What it is | State |
|---|---|---|
| [`deskmap/`](deskmap/) | Library. Reads monitors, workspaces, work areas and windows, and moves and sizes windows. Both tools below are built on it. | pure parts and X11 backend done (`Rect`, monitors, workspaces, work area, placement maths, placing and closing windows), used by tilepane; window listing for cascade-windows next (see [PROGRESS.md](PROGRESS.md)) |
| [`tilepane/`](tilepane/) | Opens terminal windows at exact positions per monitor and workspace and runs commands in them. Layouts are JSON trees of splits and panes, editable in a browser. | working (X11) |
| [`cascade-windows/`](cascade-windows/) | Windows-style "Cascade windows" for Linux: stacks the windows of a monitor or workspace in a neat cascade. | working (X11, GNOME Shell extension) |

The tools are independent programs with their own installation and their own
README. They live in one repository because they change together with the
library. Room is left for more tools that use `deskmap`.

## Why one repository

`tilepane` and `cascade-windows` both had their own code for finding monitors,
numbering workspaces, subtracting panels from the work area and placing windows
exactly. That code is hard to get right, so it should exist once. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Numbering (the same in every tool)

- **Monitors** are numbered left to right, then top to bottom. Monitor 0 is the leftmost.
- **Workspaces** are numbered from the bottom left corner, left to right along each row, then row by row upwards. Workspace 0 is bottom left. In a 3 x 2 grid:

```
3 4 5
0 1 2
```

Window managers number workspaces in their own order (usually from the top
left). `deskmap` converts between that order and the numbers a person uses; the
tools only ever show and accept the person's numbers.

## Requirements

Each tool lists its own requirements first in its README. In short: Linux with
an X11 session, Python 3.9 or newer, `python-xlib`, `xrandr`
(`x11-xserver-utils`). GNOME on Wayland is reached through the GNOME Shell
extension in `cascade-windows/`.

## Get the repository

```
git clone https://github.com/anttiraisala/deskworks.git
cd deskworks
```

## Run the tests

```
./scripts/test-all.sh
```

This runs the tests of every project. The live X11 tests of `tilepane` need a
display; see [CLAUDE.md](CLAUDE.md).

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): layers, folders and dependency rules
- [docs/DESKMAP.md](docs/DESKMAP.md): what the library contains and how it is extracted
- [docs/DECISIONS.md](docs/DECISIONS.md): decisions and the reasons for them
- [PROGRESS.md](PROGRESS.md): what is done, what is open, and a dated log

## License

GPL-3.0-or-later, see [LICENSE](LICENSE).
