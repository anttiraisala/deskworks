# tilepane

tilepane opens terminal windows at precisely defined positions on the screen (per monitor) and starts the desired commands in them (htop, watch, nvidia-smi, and so on). Layouts are defined in JSON files and can be edited with the mouse in a browser.

Quickest way to see what it does: `tilepane --demo` (see [Try the demo](#try-the-demo)).

## Requirements

| What | Why | Ubuntu / Mint package |
|---|---|---|
| Linux with an **X11** session | windows are placed through X11 (Wayland is not supported yet; choose "Ubuntu on Xorg" at login) | - |
| Python 3.9 or newer | tilepane is a Python program | `python3` (preinstalled) |
| pipx (or pip in a virtualenv) | installs tilepane | `pipx` (or `python3-venv`) |
| python-xlib | talks to the X server; installed by the `[x11]` extra below | (installed by pipx/pip) |
| deskmap | the shared library that reads monitors, workspaces and work areas (folder `deskmap/` in this repository) | (installed by pipx/pip from this repository) |
| xrandr | finds the monitors | `x11-xserver-utils` |
| gnome-terminal or xterm | the terminal windows | `gnome-terminal` (preinstalled on Ubuntu) or `xterm` |
| git | gets the source | `git` |

Everything in one go on Ubuntu or Mint:

```
sudo apt install git pipx x11-xserver-utils xterm
pipx ensurepath             # once; puts ~/.local/bin on PATH in new terminals
export PATH="$HOME/.local/bin:$PATH"   # the same for this terminal, so you need not open a new one
```

Optional, only for a more colourful `--demo`: `htop`, `cmatrix`, `sl`, `figlet`, `fortune`, `cowsay`, `sensors` (`sudo apt install htop cmatrix sl figlet fortune-mod cowsay lm-sensors`). The demo works without them; every missing command is replaced by a plain shell loop.

## Get the repository

tilepane lives in the `tilepane/` folder of the [deskworks](https://github.com/anttiraisala/deskworks) repository. Clone with HTTPS:

```
git clone https://github.com/anttiraisala/deskworks.git
cd deskworks/tilepane
```

Or with SSH:

```
git clone git@github.com:anttiraisala/deskworks.git
cd deskworks/tilepane
```

Update an existing clone:

```
git pull
```

## Install

In the `tilepane` directory of the clone:

```
pipx install -e '.[x11]'
```

`[x11]` pulls in python-xlib; without it tilepane can compute layouts (`--dry-run`) but cannot open windows. `-e` makes `git pull` take effect for tilepane without reinstalling. The `deskmap` library is fetched from this repository's `master` branch as a dependency, as a snapshot that does not follow `git pull`. To make tilepane use the `deskmap` folder of the clone, so that the two always match, run `pipx runpip tilepane install -e ~/deskworks/deskmap` (the full path; use your clone's) after the installation. To work on `deskmap` and tilepane together, you can also use the virtualenv install below.

Without pipx, in a virtualenv:

```
python3 -m venv .venv
. .venv/bin/activate
pip install -e ../deskmap -e '.[x11]'
```

Check the result:

```
tilepane --doctor           # environment, monitors, terminal, recommended backend
tilepane --monitors         # monitors with tilepane's numbers (0 = leftmost)
```

`--doctor` says what is missing, if anything.

### Uninstall

```
tilepane --uninstall           # removes the program; your layouts stay
tilepane --uninstall --purge   # also deletes your layouts in ~/.config/tilepane
```

It shows what it will do and asks first (`--yes` skips the question). It closes the windows tilepane opened, deletes its state in `~/.local/state/tilepane`, and removes the program with the tool it was installed with (pipx or pip). Layout files you keep elsewhere and the cloned repository folder are not touched. The clone (`~/deskworks`) also holds `cascade-windows` and `deskmap`, so delete it only when you no longer need them (`rm -rf ~/deskworks`). By hand, the same is `pipx uninstall tilepane` (or `pip uninstall tilepane`) plus deleting those folders.

### Where tilepane keeps its files

| What | Location |
|---|---|
| The program (pipx) | `~/.local/share/pipx/venvs/tilepane`, command `~/.local/bin/tilepane` |
| Layouts and settings | `~/.config/tilepane/config.json` (`tilepane --edit` edits it in the browser; a layout file can also be anywhere, give its path; a bare name like `tilepane metering.json` is looked up in the current directory first and then in `~/.config/tilepane`) |
| State (which windows are open) | `~/.local/state/tilepane/` |

`XDG_CONFIG_HOME` and `XDG_STATE_HOME` replace `~/.config` and `~/.local/state` when they are set.

## Try the demo

```
tilepane --demo
```

The demo splits monitor 0 at random into 3 to 6 panes and runs a fun command in each (htop, a clock, cmatrix, fortune | cowsay, ...). The windows stay open until you close them. Every run prints its seed, so a demo you like can be repeated and kept:

```
tilepane --demo --monitor 1                    # on another monitor (see tilepane --monitors)
tilepane --demo 5                              # exactly 5 panes
tilepane --demo --seed 42                      # repeat the demo that printed "seed 42"
tilepane --demo --seed 42 --save demo.json     # keep it as an editable layout file
tilepane demo.json                             # open the saved layout later
tilepane --demo --for 30s                      # windows close by themselves after 30 seconds
tilepane --demo --dry-run                      # only print the rectangles and commands
tilepane --close all                           # close the demo (and everything else tilepane opened)
```

A new demo on the same monitor replaces the previous one.

## Use your own layouts

```
tilepane --dry-run examples/meters.json --monitor 1   # print the rectangles only
tilepane examples/meters.json --monitor 1             # open the windows
tilepane --toggle examples/meters.json --monitor 1    # close them again (or open if closed)
tilepane --close all                                  # close everything tilepane opened
tilepane examples/meters.json -x                      # open, then close this terminal (only if all went well)
tilepane --edit examples/meters.json                  # edit it in the browser (see below)
tilepane --explain on_exit                            # describe any configuration key
```

Without installing: `PYTHONPATH=src:../deskmap/src python3 -m tilepane.cli --dry-run examples/meters.json`.

## Make a layout of the windows that are open (`--analyze`)

Opening a layout makes windows from a file. `--analyze` goes the other way: it looks at the windows that are open on a monitor and writes the layout they make.

```
tilepane --analyze                      # the current monitor -> analyzed-layout.json
tilepane --analyze mine.json            # write it to mine.json
tilepane --analyze mine.json --edit     # ... and open it in the browser editor right away
tilepane --analyze --monitor 1          # another monitor (a number, a connector name, or "all")
tilepane --analyze --workspace all      # every workspace (a number or "current" also work)
tilepane --analyze --terminals-only     # leave out windows that are not terminals
tilepane --analyze --dry-run            # print the layout, write nothing
```

- **Which monitor:** the one the active window is on (the terminal where you typed the command), or, if there is no active window, the one with the mouse pointer. `--monitor` chooses others; with several monitors or workspaces the file holds one layout for each, and a layout for a workspace remembers its workspace.
- **Which windows:** the normal windows that are shown (not minimized) on that workspace and monitor; windows that are on every workspace count for the current one. Each becomes a pane. A terminal gets the command that runs in it, when that can be read (a window that tilepane opened gets its own commands, directory and title back; a plain `xterm` or `gnome-terminal` with a program running gets that program; several `gnome-terminal` windows share one process, so there the panes are just shells). Other windows become a shell titled with the name of the program (`Firefox: ...`), which keeps their place in the layout.
- **The splits:** they are made so that the panes tile the work area without overlapping. The gap between windows becomes `margin` (and the distance to the edge `outer_margin`, if it is not the half of the margin); screen that no window covers becomes empty panes. Where windows lie on top of each other (a cascade) the layout cannot be the same as the screen: the windows are separated by cutting between their centres, each keeps the part on its side of the cut, and the command tells how much the panes differ from the windows.
- **Result:** run `tilepane FILE --monitor N` to open it, or edit it first. An existing file is not replaced unless you give `--yes`.

## Edit layouts in the browser

```
tilepane --edit examples/meters.json     # or: tilepane --edit   (your default config)
```

The editor opens in your browser and shows the layout on a picture of the monitor, to scale:

- **Click a pane** to edit it: its command (one per line for several commands), title, working directory, shell, terminal and the rest. Every setting has its explanation next to it.
- **✂ Cut pane ─ / ✂ Cut pane │**: cut the selected pane with a horizontal line (a top and a bottom piece) or a vertical line (a left and a right piece). It halves the pane at once (the first piece keeps the contents and the new second one is selected); in an empty editor, where nothing is selected, the whole screen is the first rectangle and it is cut in half. To choose the place of the cut, use **Cut screen** below. **Add a pane** next to it, **make it empty** or **remove** it.
- **Drag the line** between two panes to resize them; the line **snaps** by itself to a nearby line that runs the same way, so the panes line up exactly and the panes beside it can be merged; a tooltip at the cursor says that holding **Alt** turns the snapping off. Hold **Shift** while dragging (also if you press it halfway) to leave the line where it is and make a new, parallel one where you drop it; between the two lines there is a new empty pane. Dropped too close to the old line, nothing is made. Shift-dragging from the edge of the monitor (the first 12 screen pixels inside the work area, shown while Shift is held) makes a new empty pane between that edge and the line, in front of the one pane you grabbed; the other panes at that edge stay as they are. Esc cancels. Click a line to set its exact value, in % or px, measured from the start or from the end.
- **Drag a pane onto another** to swap them: a copy of the pane follows the mouse and shows where it lands; the contents change places, the sizes stay.
- **✂ Cut screen ─ / ✂ Cut screen │** (keys H and V): a line across the whole monitor follows the mouse; a click cuts every pane it goes through. The contents stay in the top or left piece.
- **Merge** two neighbouring panes into one: select a pane and click an arrow on its edge, or click the line between two panes and press Delete. An empty pane merges at once; if both have commands, you are asked which one stays.
- **Drag the monitor's edges or corners** to try the layout on another screen size; the size is shown in pixels. The margin (gap between windows) is set right under the picture.
- Settings you give every pane (a shell, a working directory, ...) are moved up the tree automatically, so they are written once; splitting a pane passes its settings to both halves.
- **Commands** (and the top of the layout panel) shows the command lines that open, toggle or close this layout from a terminal, with Copy buttons; the monitor can be written as a number or as its name.
- **JSON…** opens a box with the layout as JSON: copy it to export. To import, paste JSON over the text (a whole file, one layout, or just a split/pane tree) and choose *Replace this layout*, *Add as new layout* or *Replace whole file*. Mistakes are shown in the box; each import is one undo step.
- Click outside the monitor picture (or press Esc) to unselect.
- **Undo / Redo** (Ctrl+Z, Ctrl+Y) for edits of the layout and for the preview too: dragging the monitor's edges to another size, choosing another monitor or custom size in the list, and "Reset size" can all be undone and redone, even in a fresh, empty editor. The preview is not saved in the file, so these steps do not mark it as changed. Several layouts per file (New, Copy, Delete), and the monitor to preview on.
- Problems are listed at the bottom and marked on the pane; the file cannot be saved until they are fixed.
- **Save** (Ctrl+S) writes the file. **Open on screen** saves and opens the layout on the chosen monitor for real; **Close on screen** closes it again.

The editor only runs on your own machine (127.0.0.1), with a secret address, and stops when you close its tab. Keys it does not know are kept as they are.

Without tilepane installed, open `src/tilepane/editor/editor.html` straight in the browser: everything works except opening on screen, and files are opened and saved through the browser.

## Workspaces

tilepane keeps each workspace separate. Open a layout on workspace 0, switch to workspace 1 and open it again: workspace 1 gets its own windows, and the ones on workspace 0 stay where they are.

Workspaces are numbered from 0 in the bottom left corner, along the row to the right, then the next row up. On a 2 x 2 grid:

```
2 3
0 1
```

With all workspaces in one row, 0 is the first (leftmost). `tilepane --workspaces` draws your own grid with its numbers. This works with ordinary workspaces (Cinnamon, GNOME, Xfce, KDE, Openbox) and with Compiz/Unity, whose workspaces are parts of one large desktop.

```
tilepane examples/meters.json                  # opens on the current workspace
tilepane --workspaces                          # shows your workspaces and their numbers
tilepane --identify                            # a window on every monitor of every workspace,
                                               # saying which workspace and monitor it should be on
tilepane examples/meters.json --workspace 3    # opens on workspace 3
tilepane --close all                           # closes tilepane's windows on this workspace only
tilepane --close all --workspace 2             # ... on workspace 2
tilepane --close all --workspace all           # ... on every workspace
```

A layout can also name its own workspace, so it always opens there:

```json
{ "name": "meters", "workspace": 3, "split": { ... } }
```

`--workspace` on the command line overrides it. In the editor, pick it from the **Workspace** list at the top. `--toggle` and `--demo` also work per workspace. You can close any window normally with its close button; tilepane notices it the next time it runs, and opening the layout again brings back just that pane. A window you move to another workspace by hand counts as part of that workspace from then on.

## Status

The project is under construction. Implemented so far: environment check, monitor numbering and per-monitor work area, the geometry engine, configuration loading and validation, `--dry-run`, opening windows on X11 with gnome-terminal or xterm, window state (`--close`, `--toggle`, re-placing open layouts), workspaces, `snap`, `decorations`, `--demo` and the browser editor (`--edit`). The Wayland backends follow the plan in [SPEC.md](SPEC.md); progress is in [PROGRESS.md](PROGRESS.md).

## Configuration

A layout is a tree of splits and panes, written in JSON:

```json
{
  "name": "meters",
  "margin": 8,
  "split": {
    "dir": "columns", "at": "60%",
    "a": { "run": "htop" },
    "b": { "run": "watch -n1 sensors" }
  }
}
```

Every pane can choose its own terminal (the window: `"terminal": "xterm"`) and its own shell (the program that understands the commands: `"shell": "zsh"`). Both default to `"auto"`: the first terminal found, and your own login shell (bash on Ubuntu and Mint). Set either on one pane, on a split (for everything below it), on the layout or in `defaults`; `tilepane --doctor` lists the terminals and shells installed.

`dir` is `columns` (panes side by side) or `rows` (stacked). A pane you leave out, or write as `{}`, stays empty: no window opens there. Here the left 40 % is left empty:

```json
{ "name": "right-side", "split": {
    "dir": "columns", "at": "40%",
    "b": { "dir": "rows", "a": { "run": "htop" }, "b": { "run": "watch -n1 sensors" } } } }
```

### Several commands in one pane

Give `run` a list, and the commands run one after another in the same terminal window. Each starts when the previous one ends:

```json
{ "name": "info", "split": {
    "dir": "columns",
    "a": { "run": ["date", "whoami", "ls -la"], "cwd": "~" },
    "b": { "run": "htop" } } }
```

The left window prints the date, then your user name, then the files in your home directory. When the list is done the window stays open with a command prompt (`"on_exit": "close"` closes it instead, `"restart"` runs the list again). The next command starts even if the previous one failed; `"stop_on_error": true` stops at the first failure. To time a command, write it as one entry: `"time ls -la"`.

Every key, with type, default and inheritance, is listed in [docs/CONFIG.md](docs/CONFIG.md). That file is generated from the JSON schema in [src/tilepane/tilepane.schema.json](src/tilepane/tilepane.schema.json); add `"$schema"` to your file to get completion and tooltips in VS Code (see [examples/meters.json](examples/meters.json)).

A layout file is a program: opening it runs the commands in it. Only open files you trust. `--dry-run` shows the commands without running anything.

## Development

```
export PYTHONPATH=src:.:../deskmap/src         # run from the tilepane directory; or pip install -e ../deskmap
python3 -m unittest discover -s tests -t .
TILEPANE_LIVE=1 TILEPANE_MONITOR=3 python3 -m unittest tests.test_x11_live   # opens real windows
python3 -m tilepane.docgen      # after editing the schema: docs/CONFIG.md and the editor's copy
python3 -m tests.make_vectors   # after a deliberate change to geometry.py
```

The key tables in `src/tilepane/config.py`, the schema, `docs/CONFIG.md` and the schema embedded in the editor are checked against each other by the tests. The editor's JavaScript geometry is checked against `tests/vectors/geometry.json` when `node` is installed, and the editor is driven in Chromium (`tests/js/editor.e2e.mjs`) when Playwright is installed too; both are skipped otherwise.
