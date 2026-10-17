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
| xrandr | finds the monitors | `x11-xserver-utils` |
| gnome-terminal or xterm | the terminal windows | `gnome-terminal` (preinstalled on Ubuntu) or `xterm` |
| git | gets the source | `git` |

Everything in one go on Ubuntu or Mint:

```
sudo apt install git pipx x11-xserver-utils xterm
pipx ensurepath             # once; then open a new terminal so ~/.local/bin is on PATH
```

Optional, only for a more colourful `--demo`: `htop`, `cmatrix`, `sl`, `figlet`, `fortune`, `cowsay`, `sensors` (`sudo apt install htop cmatrix sl figlet fortune-mod cowsay lm-sensors`). The demo works without them; every missing command is replaced by a plain shell loop.

## Get the repository

Clone with HTTPS:

```
git clone https://github.com/anttiraisala/tilepane.git
cd tilepane
```

Or with SSH:

```
git clone git@github.com:anttiraisala/tilepane.git
cd tilepane
```

Update an existing clone:

```
git pull
```

## Install

In the cloned directory:

```
pipx install -e '.[x11]'
```

`[x11]` pulls in python-xlib; without it tilepane can compute layouts (`--dry-run`) but cannot open windows. `-e` makes `git pull` take effect without reinstalling.

Without pipx, in a virtualenv:

```
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[x11]'
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

It shows what it will do and asks first (`--yes` skips the question). It closes the windows tilepane opened, deletes its state in `~/.local/state/tilepane`, and removes the program with the tool it was installed with (pipx or pip). Layout files you keep elsewhere and the cloned repository folder are not touched; delete the folder yourself (`rm -rf ~/tilepane`). By hand, the same is `pipx uninstall tilepane` (or `pip uninstall tilepane`) plus deleting those folders.

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

Without installing: `PYTHONPATH=src python3 -m tilepane.cli --dry-run examples/meters.json`.

## Edit layouts in the browser

```
tilepane --edit examples/meters.json     # or: tilepane --edit   (your default config)
```

The editor opens in your browser and shows the layout on a picture of the monitor, to scale:

- **Click a pane** to edit it: its command (one per line for several commands), title, working directory, shell, terminal and the rest. Every setting has its explanation next to it.
- **Split** a pane into left | right or top / bottom, **add a pane** next to it, **make it empty** or **remove** it.
- **Drag the line** between two panes to resize them; hold **Shift** to line it up exactly with another line (then the panes beside it can be merged). Click a line to set its exact value, in % or px, measured from the start or from the end.
- **Drag a pane onto another** to swap them: a copy of the pane follows the mouse and shows where it lands; the contents change places, the sizes stay.
- **✂ Cut ─ / ✂ Cut │** (keys H and V): a line across the whole monitor follows the mouse; a click cuts every pane it goes through. The contents stay in the top or left piece.
- **Merge** two neighbouring panes into one: select a pane and click an arrow on its edge, or click the line between two panes and press Delete. An empty pane merges at once; if both have commands, you are asked which one stays.
- **Drag the monitor's edges or corners** to try the layout on another screen size; the size is shown in pixels. The margin (gap between windows) is set right under the picture.
- Settings you give every pane (a shell, a working directory, ...) are moved up the tree automatically, so they are written once; splitting a pane passes its settings to both halves.
- **Commands** (and the top of the layout panel) shows the command lines that open, toggle or close this layout from a terminal, with Copy buttons; the monitor can be written as a number or as its name.
- Click outside the monitor picture (or press Esc) to unselect.
- **Undo / Redo** (Ctrl+Z, Ctrl+Y), several layouts per file (New, Copy, Delete), and the monitor to preview on.
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
PYTHONPATH=src:. python3 -m unittest discover -s tests -t .
TILEPANE_LIVE=1 TILEPANE_MONITOR=3 PYTHONPATH=src:. python3 -m unittest tests.test_x11_live   # opens real windows
PYTHONPATH=src python3 -m tilepane.docgen      # after editing the schema: docs/CONFIG.md and the editor's copy
PYTHONPATH=src:. python3 -m tests.make_vectors # after a deliberate change to geometry.py
```

The key tables in `src/tilepane/config.py`, the schema, `docs/CONFIG.md` and the schema embedded in the editor are checked against each other by the tests. The editor's JavaScript geometry is checked against `tests/vectors/geometry.json` when `node` is installed, and the editor is driven in Chromium (`tests/js/editor.e2e.mjs`) when Playwright is installed too; both are skipped otherwise.
