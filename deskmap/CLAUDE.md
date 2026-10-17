# CLAUDE.md (deskmap)

The repository rules in `../CLAUDE.md` apply. This file adds only what is specific to the library.

- `deskmap` never imports a tool (`tilepane`, `cascade-windows`).
- Pure modules (`rect`, `monitors` parsing, `workspaces`, `workarea` calculations, `placement`) must not import python-xlib. Only the future `backends/x11.py` may.
- The numbering rules in `README.md` are fixed by the owner; do not change them.
- Code arrives here by being moved from the tools, together with its tests, without a behaviour change; the tool is switched to the library in the same step. Track the progress in `../PROGRESS.md` and `../docs/DESKMAP.md`.
- Tests: `PYTHONPATH=src:. python3 -m unittest discover -s tests -t .`
