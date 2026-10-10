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

The project is under construction. Implemented so far: environment check, monitor numbering, the geometry engine, configuration loading and validation, and `--dry-run`. Opening real windows (step 4), the browser editor and the rest follow the plan in [SPEC.md](SPEC.md); progress is in [PROGRESS.md](PROGRESS.md).

## Install and try

```
pip install -e .            # or: pipx install .
tilepane --doctor           # environment, monitors, recommended backend
tilepane --monitors         # monitors with tilepane's numbers (left to right)
tilepane --dry-run examples/meters.json --monitor 1
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
PYTHONPATH=src python3 -m unittest discover -s tests
PYTHONPATH=src python3 -m tilepane.docgen      # regenerate docs/CONFIG.md after editing the schema
```

The key tables in `src/tilepane/config.py`, the schema and `docs/CONFIG.md` are checked against each other by the tests.
