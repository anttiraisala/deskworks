# tilepane

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

## About

tilepane opens terminal windows at precisely defined positions on the screen (per monitor) and starts the desired commands in them (htop, watch, nvidia-smi, and so on). Layouts are defined in JSON files and can be edited with the mouse in a browser.

The project is under construction. Implemented so far: environment check, monitor numbering and per-monitor work area, the geometry engine, configuration loading and validation, `--dry-run`, and opening windows on X11 with gnome-terminal or xterm. Window state (`--close`, `--toggle`, re-placing open layouts), `snap` and `decorations`. `--demo`, the browser editor and the Wayland backends follow the plan in [SPEC.md](SPEC.md); progress is in [PROGRESS.md](PROGRESS.md).

## Install and try

```
pip install -e .            # or: pipx install .
tilepane --doctor           # environment, monitors, recommended backend
tilepane --monitors         # monitors with tilepane's numbers (left to right)
tilepane --dry-run examples/meters.json --monitor 1   # print the rectangles only
tilepane examples/meters.json --monitor 1             # open the windows (X11)
tilepane --toggle examples/meters.json --monitor 1    # close them again (or open if closed)
tilepane --close all                                  # close everything tilepane opened
tilepane --explain on_exit  # describe any configuration key
```

Without installing: `PYTHONPATH=src python3 -m tilepane.cli --dry-run examples/meters.json`.

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
