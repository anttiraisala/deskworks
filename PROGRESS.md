# Progress

Newest log entries last. See `CLAUDE.md` for how this file is kept.

## Status

| Step | Description | State |
|---|---|---|
| 1 | Repository created; tilepane and cascade-windows imported with history | done |
| 2 | Repository level documents, test script, language exceptions | done |
| 3 | `deskmap` package: pure parts (`Rect`, monitors, workspaces, work area, placement maths) with tests | done |
| 4 | `deskmap` X11 backend moved from tilepane | next |
| 5 | tilepane uses `deskmap` | done for the pure parts; the X11 backend follows step 4 |
| 6 | Window listing and cascade operations in `deskmap`; cascade-windows uses `deskmap` | open |
| 7 | GNOME backend and extension protocol moved into `deskmap` | open |

## Log

### 2026-10-17: repository created
- Created from the maintainer's decision to share the desktop-reading code between tilepane and cascade-windows. Context: both projects had their own monitor detection, workspace numbering, work area and X11 placement code.
- `tilepane` (47 commits) and `cascade-windows` (22 commits) were added with `git subtree add`, so their history is kept in the subfolders. The original repositories were not touched.
- Tests at import: tilepane 384 pass (5 skipped: live X11 and browser tests that need a display), cascade-windows 218 pass (21 skipped).
- Not yet changed: no code was edited by the import. The projects still use their own copies of the shared logic.
- Open: confirm the repository license for cascade-windows (it had none), and name of the repository's Python distribution if `deskmap` should be published.

### 2026-10-17: deskmap pure parts, tilepane switched over (steps 3 and 5, partly)
- `deskmap/` created with `rect.py`, `monitors.py`, `workspaces.py`, `workarea.py` and `placement.py`, moved from tilepane without behaviour change. Their tests moved with them: `test_monitors` (parsing), `test_workspaces` (grid and numbering), `test_workarea`, `test_placement` (39 tests). What stayed in tilepane because it tests tilepane code: the `--workspaces` CLI test, `doctor.recommend` tests, the x11 client-message test, and the other placement users.
- tilepane imports these from `deskmap` and no longer has its own copies; `geometry.Rect` is now `deskmap.rect.Rect`, so there is one `Rect` class in the system. tilepane depends on `deskmap` through a git URL with `#subdirectory=deskmap` in `pyproject.toml`. This needs the `master` branch of this repository on GitHub, so the dependency resolves only after this commit is pushed.
- Tests: tilepane 345 + deskmap 39 = 384, the same count as before the move (5 skipped, as before). cascade-windows 218 pass (21 skipped), untouched. Live X11 tests under Xvfb + openbox with the installed package: 5 run, 2 pass, 3 skipped because gnome-terminal is not installed in the container. Not verified: a live run on the owner's Mint machine; the dependency install through the git URL (`pip install` from GitHub).
- Decisions not fixed earlier: `monitors.resolve` and the alias handling moved with `monitors.py` unchanged; separating them from detection is left for later. The `$schema` URLs in tilepane's schema, docs and editor still point to the original `anttiraisala/tilepane` repository because they are generated and checked by tests; they keep working while that repository exists and must be changed together with the generated files when it is archived.
- Open: move the X11 backend (step 4); `cascade-windows` has no `pyproject.toml` yet, so it cannot declare the `deskmap` dependency; licence for cascade-windows.
