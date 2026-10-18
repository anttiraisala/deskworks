# Progress

Newest log entries last. See `CLAUDE.md` for how this file is kept.

## Status

| Step | Description | State |
|---|---|---|
| 1 | Repository created; tilepane and cascade-windows imported with history | done |
| 2 | Repository level documents, test script, language exceptions | done |
| 3 | `deskmap` package: pure parts (`Rect`, monitors, workspaces, work area, placement maths) with tests | done |
| 4 | `deskmap` X11 backend moved from tilepane | done |
| 5 | tilepane uses `deskmap` | done |
| 6 | Window listing and cascade operations in `deskmap`; cascade-windows uses `deskmap` | started: `Rect`, workspace numbering and installation done; X11 backend merge open |
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

### 2026-10-17: dependency check
- Verified after the push: `pip install './tilepane[x11]'` in a fresh virtualenv fetches `deskmap` from this repository's `master` through the git URL, and `tilepane --version` runs. This closes the "not verified" item about the git URL dependency in the previous entry.

### 2026-10-17: schema URLs and project brief
- The `$schema` / `$id` URLs in tilepane's schema, generated `docs/CONFIG.md`, the editor's embedded schema, `demo.py`, `docgen.py`, `SPEC.md` and `examples/meters.json` now point to `anttiraisala/deskworks/master/tilepane/src/tilepane/tilepane.schema.json`. Before this they pointed to the original `anttiraisala/tilepane` repository (see the "Open" note two entries up, which this closes). `docgen` was re-run so the generated files agree.
- `tilepane/docs/YHTEENVETO.md` (Finnish) was translated into English and renamed `tilepane/docs/PROJECT-BRIEF.md`; the content was also updated to mention the new repository layout. `.language-exceptions` now has no entries. Decisions 8 and 9 in `docs/DECISIONS.md` record this.
- Note: the schema URL only resolves once this commit is on `master`; editors that fetch the schema over the network will get a 404 before that.

### 2026-10-17: X11 backend moved into deskmap (step 4)
- `tilepane/src/tilepane/backends/x11.py` is now `deskmap/src/deskmap/backends/x11.py` (moved with `git mv`, so history follows), and the backend interface (`Backend`, `WindowInfo`, `Placement`, `BackendError`) is `deskmap/src/deskmap/backends/__init__.py`. No behaviour change. tilepane keeps `backends/__init__.py` only for `choose()`, which depends on tilepane's `--doctor` logic, and re-exports the types so existing imports work.
- The `card32` test moved to `deskmap/tests/test_x11_backend.py`. Tests: tilepane 344 + deskmap 40 = 384, the same total as before. Live X11 tests (Xvfb + openbox, 5 run, 2 pass, 3 skipped because gnome-terminal is missing) and a `tilepane --demo` run opened and placed xterm windows through the installed package. Not verified on the owner's Mint machine.
- Open: the window listing and cascade operations (`unmaximize`, `raise`, window kinds and flags) are not in `deskmap` yet; cascade-windows has no `pyproject.toml` so it cannot declare the dependency; `choose()` should move into `deskmap` once cascade-windows needs it too.

### 2026-10-17: cascade-windows on deskmap (step 6, first part)
- Two commits, as the repository rules require. First, no behaviour change: `deskmap.Rect` got cascade-windows' helpers (`center`, `contains`, `distance_sq`, `intersect`, `to_list`, `from_list`, `__str__`), and `cascade_windows/model.py` re-exports it, so there is one `Rect` class in the system. `install.sh` copies `deskmap/src/deskmap` next to `cascade_windows` in `~/.local/share/cascade-windows/lib` (and stops with a clear message when it is not there, for example after downloading only the cascade folder); `bin/cascade-windows` and the tests (`tests/__init__.py`, `tests/fake_shell_service.py`) add `../deskmap/src` to the path. The documented test command is now `python3 -m unittest discover -s tests -t .`, because the path set-up lives in `tests/__init__.py`.
- Second, a deliberate behaviour change: workspace numbers and `"x,y"` positions in cascade-windows' `exclude` rules and `--list-targets` now follow the common numbering (bottom left is 0, `y` counts from the bottom). They were in reading order from the top left. `WorkspaceGrid` uses `deskmap.workspaces.user_numbers`; the old tests were rewritten for the new numbering and two new tests cover the bottom-row-first rule and a short last row. Existing `exclude` rules that name a workspace must be updated by the user; see decision 11 and the CHANGELOG.
- Tests: cascade-windows 219 pass with no display (21 skipped). With Xvfb + openbox and the installed python-xlib all 218 tests that existed before ran and passed with none skipped, including the real X11 integration tests (run before the numbering change; the numbering change touches only the pure `exclusions` module). `install.sh` into a throw-away home (X11 backend) produced a command that runs without `PYTHONPATH` and `uninstall.sh` removed it. Not verified: a run on the owner's Mint or Unity machine, GNOME on Wayland.
- Decision not fixed earlier: cascade-windows keeps its own X11 backend for now. It has dock window and per-monitor strut handling that `deskmap.workarea` lacks, and the two work-area implementations differ in details; merging them needs side-by-side live comparison on real hardware (Mint, Unity 7), so it is left open.
- Open: merge the work-area and monitor code; move window listing and the cascade operations into `deskmap`; move the GNOME backend and extension protocol; `choose()` into `deskmap`.

### 2026-10-18: live verification by the owner
- Reported by the owner after installing from this repository (`pipx install -e '.[x11]'` in `tilepane/`): on the Linux Mint virtual machine (Cinnamon/Muffin, X11, one monitor, four workspaces in one row) `tilepane --doctor`, `--monitors`, `--workspaces`, `--demo` and `--close all` work. On the host (Ubuntu with Unity 7/Compiz, four monitors, 2 x 2 viewport workspaces) the same commands work and `tilepane --identify` opened one correctly labelled window on every monitor of every workspace (16 windows), so monitor numbering, workspace numbering (bottom left is 0) and exact placement through `deskmap` are confirmed live on the real machine.
- Seen but not explained: in one `--demo` run (seed 303351) on the host, two panes in the first column were reported as "window manager gave a different size". It is not yet known whether the previous tilepane version did the same for that seed; the owner was given commands to compare (clone of the original repository, same seed).
- Not yet verified live: `cascade-windows` from this repository on either machine, and the `exclude` workspace renumbering.

### 2026-10-18: cascade-windows `--edit-config` opens a text editor
- Found by the owner on the host: `cascade-windows --edit-config` opened the file in Firefox (the default handler of the JSON type) and Firefox answered "Access to the file was denied" (a sandboxed browser cannot read `~/.config`). The command now looks up the default `text/plain` application with `xdg-mime query default` and starts it with `gtk-launch`; `xdg-open` stays as the fallback. 5 new tests in `cascade-windows/tests/test_edit_config.py` (cascade-windows: 224 pass, 21 skipped without a display). Not verified on the owner's machine yet.
- Also seen: the host still had the old cascade-windows installed (its `--help` had no `--list-targets`), so the earlier host cascade tests ran on the old version; the owner was told to run `uninstall.sh` and `install.sh` again.

### 2026-10-18: cascade-windows `--editor`
- New option `--editor COMMAND` for `--edit-config`, requested by the owner, to choose the editor. The value is split like a shell command line (so `"code --wait"` works), must name an executable that exists (otherwise exit code 1 with a message), and runs in the foreground so terminal editors (nano, vim) work. `--editor` without `--edit-config` is a usage error (exit code 2). 5 new tests in `tests/test_edit_config.py` (cascade-windows: 229 pass, 21 skipped without a display). Not verified on the owner's machine yet.

### 2026-10-18: exclusion notice for Cascade Workspace and Cascade All Workspaces
- Reported by the owner after testing exclusions on the host: the "This monitor is excluded" notice appeared for Cascade Windows (monitor scope) but not for Cascade Workspace and Cascade All Workspaces started on an excluded monitor. Cause: only the monitor scope compared the monitor under the pointer with the rules (`Plan.target_excluded`); the other scopes only counted the excluded windows and told the user nothing when something else was still moved.
- Fix: a new `Plan.pointer_excluded` flag, set in `build_plan` for the workspace and all scopes when the monitor under the pointer on the current workspace is excluded. It is computed from the same rules and does not touch the grouping or the moves (a test checks that the moved windows and their rectangles are identical with the pointer on an excluded and on an allowed monitor). `cli.py` prints the note and sends the notification after such a cascade, or, when nothing else moved, the message "This monitor is excluded ... and nothing else was cascaded". `notify.excluded` and `--ignore-exclusions` work as before; README, `docs/CONFIGURATION.md`, the setting description and CHANGELOG were updated.
- Behaviour change in one existing test: the partial-exclusion CLI test used a pointer on the excluded monitor and expected no notification; it now expects the notice. 7 new tests; cascade-windows 236 pass, 21 skipped without a display. Not verified live yet.

### 2026-10-18: `editor` setting in the cascade-windows configuration
- Requested by the owner: the editor choice must also be configurable in the JSON. New top-level key `editor` (text, default empty). Order of precedence for `--edit-config`: `--editor` option, then the `editor` setting, then the desktop's default text editor, then `xdg-open`. `configured_editor()` reads the setting even when other values in the file are invalid (it falls back to plain JSON), because `--edit-config` is how a broken file gets repaired.
- The legacy-default recognition (`remove_legacy_default_config`) treats a missing `editor` like the default, so installs of older versions still remove an untouched old default file. Written default files now contain `"editor": ""` with an explanatory comment.
- 8 new tests (cascade-windows: 244 pass, 21 skipped without a display). Not verified on the owner's machine yet.
