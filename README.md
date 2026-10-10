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
tilepane --explain on_exit                            # describe any configuration key
```

Without installing: `PYTHONPATH=src python3 -m tilepane.cli --dry-run examples/meters.json`.

## Status

The project is under construction. Implemented so far: environment check, monitor numbering and per-monitor work area, the geometry engine, configuration loading and validation, `--dry-run`, opening windows on X11 with gnome-terminal or xterm, window state (`--close`, `--toggle`, re-placing open layouts), `snap`, `decorations` and `--demo`. The browser editor and the Wayland backends follow the plan in [SPEC.md](SPEC.md); progress is in [PROGRESS.md](PROGRESS.md).

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

`dir` is `columns` (panes side by side) or `rows` (stacked). Every key, with type, default and inheritance, is listed in [docs/CONFIG.md](docs/CONFIG.md). That file is generated from the JSON schema in [src/tilepane/tilepane.schema.json](src/tilepane/tilepane.schema.json); add `"$schema"` to your file to get completion and tooltips in VS Code (see [examples/meters.json](examples/meters.json)).

A layout file is a program: opening it runs the commands in it. Only open files you trust. `--dry-run` shows the commands without running anything.

## Development

```
PYTHONPATH=src:. python3 -m unittest discover -s tests -t .
TILEPANE_LIVE=1 TILEPANE_MONITOR=3 PYTHONPATH=src:. python3 -m unittest tests.test_x11_live   # opens real windows
PYTHONPATH=src python3 -m tilepane.docgen      # regenerate docs/CONFIG.md after editing the schema
```

The key tables in `src/tilepane/config.py`, the schema and `docs/CONFIG.md` are checked against each other by the tests.
