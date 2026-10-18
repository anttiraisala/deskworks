# tilepane: project brief

A top-level description of tilepane: what it is, how it is used, what has been
decided and where the project stands. The details are in the repository (see
the end). This document is meant to be added to the knowledge of a Claude
project, so that the conversations in that project know what the project is
about. It is not a log file: keep it current when tilepane changes.

## What tilepane is

tilepane opens terminal windows at precisely defined places on the screen and
starts the wanted commands in them, for example htop, watch or nvidia-smi. A
layout is written in a JSON file as a tree: the screen is split in two, the
parts are split further, and every final rectangle (a pane) becomes one window.
A layout can also be edited with the mouse in a browser.

The program is for Linux and an X11 session (Ubuntu, Mint and others). It is
written in Python without external libraries; the only add-on is python-xlib,
which moves the windows into place. The project is public (GPL-3.0):
https://github.com/anttiraisala/deskworks (folder `tilepane/`).

tilepane lives in the same repository as `cascade-windows` (a Windows-style
"cascade windows" command) and `deskmap`, the shared library both are built on.
Monitor detection and numbering, workspace numbering, the per-monitor work area
and window placement arithmetic are in `deskmap`; tilepane uses them from there.
The numbering is unchanged.

## Usage

```
tilepane --demo                          # a random layout with fun commands
tilepane meters.json --monitor 1         # open a layout on monitor 1
tilepane --close all                     # close tilepane's windows (of this workspace)
tilepane --toggle meters.json            # open, or close if already open
tilepane --edit meters.json              # edit in the browser
tilepane meters.json -x                  # open, then close this terminal (only if all went well)
tilepane --uninstall                     # remove the program (layouts stay)
tilepane --uninstall --purge             # remove the program and the layouts in ~/.config/tilepane
tilepane --dry-run meters.json           # print the rectangles without opening anything
tilepane --doctor                        # check the environment
tilepane --monitors                      # monitor numbers
tilepane --workspaces                    # workspaces as a grid with their numbers
tilepane --identify                      # one window on every monitor of every workspace; tells where it should be
```

A small example: htop on the left (60 %), the right side split in two.

```json
{
  "name": "meters",
  "margin": 8,
  "split": {
    "dir": "columns", "at": "60%",
    "a": { "run": "htop" },
    "b": { "dir": "rows",
           "a": { "run": "watch -n1 sensors" },
           "b": { "run": ["date", "whoami", "ls -la"] } }
  }
}
```

## Main principles and decisions

- **Splits:** `dir` is `columns` (side by side) or `rows` (stacked). The split
  point `at` is given in percent or pixels, from the start or from the end
  (`-300px`). A split into more parts uses `children` and `sizes` (`1frac`,
  `300px`, `20%`).
- **Margin** is the total gap between windows; at the edge it is half of that.
- **Empty pane:** a pane that is not written or is `{}` stays empty. A pane gets
  a window when it has a setting of its own (command, directory, title, ...).
- **Several commands:** `run` can be a list; the commands run one after
  another in the same window. At the end the window stays open at a prompt
  (`on_exit`: `keep`, `close` or `restart`).
- **Terminal and shell** are chosen per pane (`terminal`, `shell`). The default
  is `auto`: the first terminal found and the user's own shell (bash on Mint).
  Settings are inherited down the tree.
- **Monitors** are numbered by position from left to right, then top to bottom,
  starting from zero.
- **Workspaces** are kept apart: the same layout can be opened on different
  workspaces and each gets its own windows. A layout can store its own
  workspace (`"workspace": 3`) and then always opens there; `--workspace N` on
  the command line overrides it. Workspaces are numbered from zero: 0 is the
  bottom left corner, the numbers grow to the right along a row and continue
  from the next row up (2x2: bottom row 0 1, top row 2 3). The same works on
  Compiz, where the workspaces are parts of one large desktop. `--close` closes
  from the layout's own workspace or the current one; `--workspace all` closes
  from all of them.
- **Reopening** does not create duplicates: windows that are open are moved into
  place and missing ones are opened. A window closed by hand is opened again.
- **Security:** a layout file is a program, because it runs commands. The
  editor's server runs only on the local machine at a secret address.
- **The source of the settings** is the JSON schema; the settings documentation,
  `--explain` and the editor's help texts are generated from it.

## Where things stand

Done and tested:

- environment check, monitor numbering and work area (panels taken into account)
- geometry, reading and validating settings, `--dry-run`
- opening windows on X11 with gnome-terminal and xterm, exact placement
- remembering windows, `--close`, `--toggle`, reopening, workspaces (also
  Compiz workspaces)
- `snap` (character grid or exact pixel size), removing the window decoration
- `--demo` and `--for` (the windows close after the given time)
- `--analyze`: makes a layout file of the windows that are open on a monitor (the opposite of opening a layout; commands of terminals are read back, overlapping windows are separated by cuts), optionally opens it in the editor (`--edit`)
- shell choice per pane
- the browser editor (`--edit`): splitting panes and resizing by dragging (Shift-drag leaves the old line and makes a new empty pane, also from the edge of the monitor),
  swapping panes by dragging, a cut line across the whole screen (Cut screen) and halving the selected pane (Cut pane), merging
  panes (arrows or the split line + Delete), setting the screen size by
  dragging, choosing the desktop, command lines that can be copied, common
  settings move up the tree automatically

Tested on the owner's machines: workspaces and their numbering (`--identify`)
on Linux Mint (Cinnamon) and on Ubuntu (Unity/Compiz, 2x2 workspaces, 4
monitors). In the development environment it is tested on a virtual display
(Xvfb, Openbox, xterm): the demo, workspaces, the editor's "Open on screen".

Missing or unfinished:

- `--watch`: windows update as soon as the file is saved
- Wayland support (GNOME, KDE, sway, Hyprland)
- ready-made support for the kitty and alacritty terminals
- `mode: cycle` (commands take turns in the same pane)
- a character grid preview in the editor

Proposals for new features and the recommended order are in SPEC.md, section 6
("Open work and proposals"). Recommended next: `--watch` and a log file, then
`--install-autostart` and `--install-shortcut`, then `--dry-run --ascii`.

Development is done directly on the `master` branch.

## More details in the repository

- `README.md`: installation, requirements and usage
- `SPEC.md`: the whole specification and the decisions
- `PROGRESS.md`: the development log and the status table
- `docs/CONFIG.md`: every setting with its type and default
- `CLAUDE.md`: instructions for Claude sessions
