# Progress log

Implementation follows the order in SPEC.md section 7. Newest entries last.

## Status

| Step | Description | State |
|---|---|---|
| 1 | `--doctor`, `--monitors`, project skeleton | done |
| 2 | Geometry core + unit tests | done |
| 3 | Config loading, validation, schema, CONFIG.md, task parsing, `--dry-run` | done |
| 4 | One backend end to end (X11 / python-xlib, gnome-terminal, xterm) | done |
| 5 | Aliases and hotplug, multi-task execution polish | next (largely covered by steps 3, 4 and 6) |
| 6 | `on_exit`, `snap`, state management, `--close` / `--toggle` | done |
| 7 | `--demo` | done |
| 8 | Browser editor | next |
| 9 | README, installation, example configuration | pending |

## Log

### 2026-10-10: step 1
- Environment on the dev machine: Ubuntu 24.04, X11, Unity 7 / Compiz, python-xlib 0.33, gnome-terminal 3.52, xterm; no xdotool/wmctrl/kitty/alacritty.
- Four monitors; tilepane numbering (left to right, then top to bottom) differs from xrandr's.
- Backend decision: swappable backends. X11 via python-xlib first. Wayland backends (sway/Hyprland IPC, KWin script, GNOME Shell extension) are recognised by `--doctor` but not yet implemented. Goal: work across window managers.
- Sway and Hyprland monitor parsing is tested only against synthetic JSON.
- Run tests: `PYTHONPATH=src python3 -m unittest discover -s tests`.

### 2026-10-10: step 2
- `src/tilepane/geometry.py`: `compute(layout, area) -> list[LeafRect]`, pure, takes the layout as a parsed JSON dict. Binary `a`/`b`/`at` and N-way `children`/`sizes` share one code path (binary is converted to a two-entry sizes list).
- Odd margins are split floor/ceil (start side gets the floor) so the gap between neighbours is exactly `margin`.
- `outer_margin` shrinks the area first; leaves on the outer edge get no extra inset (tested: edge is not counted twice).
- Boundaries are rounded once and shared by neighbours; a random-tree property test checks exact tiling, no overlaps and exact gaps.
- Choices not fixed by the spec: without an `frac` entry the last child absorbs leftover space; oversize sizes, empty panes and panes smaller than their margins raise `GeometryError`; `at_basis: "visible"` uses the split node's margin.
- `dir` follows the spec: `v` = children side by side, `h` = stacked. This is the opposite of tmux's `-h`/`-v` naming, so the README must state it clearly.
- Defaults (`defaults.margin` etc.) are not applied inside `compute`; step 3 merges them into the layout before calling.
- 67 tests pass.

### 2026-10-10: rename
- The fraction size unit is now `frac` instead of `fr` (`"sizes": ["1frac", "2frac", "300px"]`) in SPEC.md, geometry.py and tests.

### 2026-10-10: spec review
- `docs/SPEC-REVIEW.md`: plan for documenting JSON keys (schema as source of truth, generated `docs/CONFIG.md`, README quick start), 30+ numbered findings (A: schema decisions before step 3, B: backend risks, C: behaviour gaps, D: editor security, E: wording), and a list of extra feature ideas.
- Decisions pending from the user: `dir` naming (A3), unknown-key policy (A2), leaf `id` and `when` panes (A4, A5), whether SPEC.md is updated with the proposals before step 3.

### 2026-10-10: spec adopted, step 3
- Review proposals adopted into SPEC.md (canonical `columns`/`rows`, `id`, `when`, `empty`, `version`, `area`, inheritance, unknown-key policy, argument rules, state key, process model, editor security). Exit code 2 is for usage errors only; invalid files and unknown monitors are task failures (1).
- `config.py`: loading, validation (all problems at once, with key paths), flat and multi-layout files, inheritance resolution, `when` collapse. Resolved leaves always carry an `id` (explicit, or the path in the written tree), taken before `when` removes panes so ids stay stable.
- `tilepane.schema.json` is the single source of truth for keys; `docgen.py` writes `docs/CONFIG.md` and backs `--explain`. Tests check that the schema, the validator tables and the generated document agree.
- `invocation.py`: ordered task parsing (files, layout names, `--monitor` belonging to the task, default monitor before the first task). `--close`, `--toggle`, `--demo`, `--edit` etc. are recognised and report "not implemented yet".
- `monitors.resolve`: number, connector, alias, `primary`, `all`, comma lists. `--wait-monitors` retries detection.
- `--dry-run` prints rectangles per task; it runs nothing, and `when` conditions only with `--eval-when`. Several tasks work; a failing task does not stop the others.
- Known gap: `area: "work"` (the default) is not yet reduced by panels, so dry-run uses the full monitor and says so. Per-monitor work area is step 5 (on this machine `_NET_WORKAREA` is one rectangle for the whole screen).
- Verified a real install (`pip install` into a scratch virtualenv): the `tilepane` command works and the schema file is packaged.
- 174 tests pass.

### 2026-10-10: step 4 (X11 backend)
Spikes on this machine (Compiz/Unity, gnome-terminal 3.52, xterm) settled the open questions:
- Ubuntu's gnome-terminal starts a dedicated server for `--class=tilepane` (own PID, WM_CLASS class `tilepane`, instance stays `gnome-terminal-server`), so windows are recognised by class and found as "new in the window list". xterm honors `-class`/`-name` and its PID is the window's.
- Cell size is read from `WM_NORMAL_HINTS` (gnome-terminal base 14x2, increments 10x22; xterm base 4x4, increments 6x13). No measuring needed.
- `_NET_MOVERESIZE_WINDOW` places the frame's top-left corner and takes the client size; the frame's 32 px title bar (`_NET_FRAME_EXTENTS` 0,0,32,0) is subtracted from the height. No `_GTK_FRAME_EXTENTS` on this machine; the code handles it but it is untested.
- Compiz keeps windows inside the work area. A first run with the full monitor was pushed in by the 65 px launcher and 30 px top bar. `_GTK_WORKAREAS_D0` holds the per-monitor work areas, so the per-monitor work area (planned for step 5) was done now: `_GTK_WORKAREAS`, then panel struts, then `_NET_WORKAREA`, then the full monitor.
Implemented:
- `placement.py` (pure: frame extents, shadow extents, size hints, cell snap), `backends/x11.py` (python-xlib, EWMH), `terminals.py` (gnome-terminal, xterm, custom `cmd` templates; kitty and alacritty adapters are not written yet), `runner.py` (stdlib-only script that runs inside each window: command lists, cwd, env, `stop_on_error`, `on_exit` keep/close/restart with delay and max restarts), `opener.py` (start terminal, find the new window, place it, report), `workarea.py`.
- `tilepane FILE --monitor N` now opens windows; `when` conditions are evaluated; a pane that fails does not stop the others; exit code 1 if any pane failed.
- Verified live on monitor 3 (eDP-1): placement was exact for both terminals (planned rectangle equals the window manager's result), screenshot checked. `tests/test_x11_live.py` repeats this when `TILEPANE_LIVE=1`.
- Not yet: state file and `--close`/`--toggle`/reconcile (step 6), `snap: "pixel"` for terminals with size increments, `decorations: false`, `profile`/`font_size`, `mode: cycle/parallel`, parallel window start, kitty/alacritty.
- Run all tests: `PYTHONPATH=src:. python3 -m unittest discover -s tests -t .` (231 pass, 2 live tests skipped).

### 2026-10-10: step 6 (state, close, toggle, snap, decorations)
- `state.py`: one JSON file in `$XDG_STATE_HOME/tilepane/`, updated under a file lock and written atomically. A record is (window id, config path, layout, monitor connector, leaf id). Dead windows (no longer in the window list with class `tilepane`) are dropped whenever the state is touched.
- `manager.py`: opening an open layout reconciles. Windows are matched to panes by leaf id and moved; missing panes are opened; windows whose pane is gone are listed and closed only with `--prune`. A window closed by hand is reopened.
- `--close NAME...` (layout names, a file, or `all`), narrowed by `--monitor`; without `--monitor` it closes every instance on every monitor. `--toggle` is per layout and monitor. Both use the normal task syntax.
- `snap: "pixel"`: the window's resize increments are removed before placing, and gnome-terminal and xterm then take the exact pixel size (verified live: planned equals actual).
- `decorations: false`: Motif hints; frame extents drop to zero and the window fills its rectangle exactly (verified live on Compiz).
- `on_exit` (keep, close, restart with delay and max restarts) was done in step 4 in the runner.
- Tests are isolated from the real state file (`XDG_STATE_HOME`). A stray test record that an earlier run wrote to the real state directory was removed.
- Live tests (`TILEPANE_LIVE=1`): cell and pixel snap, undecorated, reopen/close; they run on monitor 3 and close their windows.
- 262 tests pass, 5 live tests pass when enabled.
- Still open: `profile`/`font_size`, `mode: cycle/parallel`, parallel window start, kitty/alacritty adapters, hotplug handling, Wayland backends.

### 2026-10-10: tests without terminals
- Development continues on branch `claude-personal` (from `master`).
- Nine CLI tests failed on machines without gnome-terminal or xterm (for example a cloud container) because the terminal is looked up with `shutil.which` even with the fake backend. `tests/fakes.py: fake_terminals_on_path` puts a stub `xterm` first on `PATH` for those tests.

### 2026-10-10: step 7 (`--demo`)
- `demo.py` (pure apart from `shutil.which`): a random split tree for the monitor's work area, margin 4-16, split points 20-80 % written as `%`, `-%`, `px` or `-px`, the long side cut more often. Every pane is at least 240x120 px; the generator only makes splits that leave room for the panes on each side, so 1-12 panes always tile without errors.
- Command pool from SPEC.md section 10, each with an `sh`/`/proc` fallback and its own title. Streaming commands that may be installed but unusable (`dmesg -w`, `journalctl -f`, `ping`, `sensors`, `nvidia-smi`) fall back when they exit within a second. Fallbacks are checked with `sh -n` and all of them were run under plain `sh`.
- The demo goes through the normal loader (`config.load_text`, strict), so it is an ordinary layout: dry-run, state, reconcile and `--close all` work unchanged. Seed always printed; `--save` writes a flat file (or one with `layouts` for several monitors) that reopens with the same rectangles.
- `--for DURATION` lives in the runner (`lifetime` in the spec) and works with any layout. At the deadline the runner signals its process group (ignoring the signal itself), hangs up an interactive shell's own group, and exits so the window closes. Checked with a real process in its own session: stopped after 1.1 s, nothing left running.
- Dry-run shows a pane's title in brackets before its command.
- Not checked live: this was built in a container without an X server or terminals, so the demo has not been opened on a real screen yet. `tilepane --demo --monitor 3` on the development machine is the check.
- 294 tests pass (5 live tests skipped).

### 2026-10-10: workspaces
- Requested by the user: windows opened on one workspace must survive opening the same layout on another workspace, and `--close` closes on the current workspace by default.
- State records carry the workspace (EWMH `_NET_WM_DESKTOP`, refreshed from the window on every run; sticky windows match every workspace). Reconcile, `--toggle`, demo replacement and `--close` (including `--close all`) work on the current workspace. `--workspace N` (1-based, as desktops number them) picks another; `--workspace all` (with `--close` only) closes everywhere. New windows opened with `--workspace N` are moved there.
- Closing now checks that windows went away and asks once more; a window that stays open is reported (exit code 1) and kept in the state. Found while testing: under Openbox two runs left windows open after `--close` and the cause could not be pinned down (40 later attempts were clean). Terminals are never killed, because one gnome-terminal server owns every tilepane window.
- Closing a window with its close button was already handled (dead windows are dropped on every run; reopening opens just that pane).
- Tested live for the first time in a container: Xvfb + Openbox (4 workspaces) + xterm. Demo, workspace separation, `--workspace 3`, `--close` per workspace and `--workspace all`, `--toggle --workspace 1` all behaved as described; the xterm live tests pass there too. Not tested: Cinnamon itself, gnome-terminal, Compiz viewports (not told apart yet).
- 311 tests pass.

### 2026-10-10: empty panes by default
- Decided with the user: a pane that is left out (missing `a`/`b`) or written as `{}` stays empty; a split with neither child is allowed and opens nothing. A leaf gets a window when it has any setting of its own other than `id`, `description` and `when` (so `{"cwd": "~"}` is a shell); inherited settings do not count. `empty: true` stays as the explicit form, `empty: false` asks for a shell.
- Before this, `{}` opened an interactive shell and a missing `a`/`b` was an error.
- Workspaces confirmed working by the user on Linux Mint (Cinnamon).
- 318 tests pass.

### 2026-10-10: `shell` per pane
- New inheriting key `shell` (default `"auto"` = `$SHELL`): a name on `PATH` or a path. The runner uses it for the commands (`-lc`) and for the interactive prompt, and sets `SHELL` in the pane. A missing shell fails only that pane. `{"shell": "zsh"}` alone opens zsh. `--doctor` lists installed shells; dry-run `-v` shows the shell.
- Default chosen as the user's own shell rather than a fixed bash, so zsh/fish users keep their aliases and PATH; on Ubuntu and Mint it is bash.
- Fixed on the way: the interactive prompt after a pane's commands did not get the pane's `env` variables (it inherited the runner's environment); it now gets the same environment as the commands.
- Checked live (Xvfb + Openbox + xterm): dash pane ran dash for the command and the prompt, default pane bash, a pane asking for zsh (not installed) failed alone.
- 325 tests pass.
