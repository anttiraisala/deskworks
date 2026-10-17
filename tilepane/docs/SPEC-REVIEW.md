# SPEC.md review, documentation plan and ideas

Written 2026-10-10 after steps 1 and 2. **Adopted into SPEC.md on 2026-10-10** (with canonical `columns`/`rows`, `id`, `when`, `empty`, `version`, `area`; `grid` stays an idea). Where SPEC.md and this file differ, SPEC.md wins. Findings are numbered so they can be referenced and ticked off. "Proposed" is a recommendation, not a decision. Items marked **[step 3]** change the config schema and should be decided before step 3 starts.

## 1. Where to document the JSON keys

Today the keys are spread over SPEC.md sections 2, 3, 10, 11 and 14, and the spec is a design document, not a user reference. Proposed, in this order of authority:

1. **`schema/tilepane.schema.json`**, the single source of truth. Every key has a `description`, a type, a default and an `examples` entry. VS Code shows these as tooltips and completion through `$schema`. The browser editor (step 8) can embed the same schema to label its side panel and to validate before saving.
2. **`docs/CONFIG.md`**, a reference generated from the schema by a small script (`tools/gen_config_docs.py`): one table per node type (file, defaults, layout, split node, leaf) with key, type, default, inherited or not, description. A test fails when the generated file is stale or when the code uses a key the schema lacks.
3. **README.md**, a quick start with three or four annotated examples and a link to CONFIG.md. The README is not the place for the full key list, because it would drift from the schema.
4. **`tilepane --explain <key>`** (optional), prints the description of a key from the schema, for use in a terminal.

The Python side uses only the standard library, so validation is hand-written code in `config.py`. A test asserts that its key set equals the schema's key set, so the two cannot diverge silently.

### Key inventory (everything that exists in SPEC.md or code today)

- File: `$schema`, `defaults`, `monitors`, `layouts`; flat single-layout files also take the layout keys.
- Defaults: `terminal`, `margin`, `outer_margin`, `snap`, `on_exit`, `decorations`.
- Layout: `name`, `margin`, `outer_margin`, `at_basis`, `split`.
- Split node: `dir`, `at`, `a`, `b`, `children`, `sizes`, `margin`, `at_basis`.
- Leaf: `run`, `cwd`, `title`, `terminal`, `profile`, `font_size`, `snap`, `on_exit`, `restart_delay`, `env`, `mode`, `interval`, `margin`.
- Mentioned as ideas only: `extends`, `templates`, `above`, `sticky`, `workspace`, per-pane color.

Not defined anywhere yet: which of these may appear at which level (see A1).

## 2. Findings

### A. Schema and semantics **[step 3]**

**A1. Inheritance and precedence are not specified.** `margin` clearly flows down the tree, but `snap`, `on_exit`, `terminal`, `decorations`, `at_basis` are not stated. Also unstated: whether `defaults` apply when `--json` points at another file, and where `monitors` aliases come from in that case. Proposed: precedence is leaf, then ancestor split nodes, then layout, then the file's `defaults`, then built-in values. Only the file in use is read; the default config is never merged in. `monitors` aliases come from that file. A table in CONFIG.md marks each key as "inherits" or "leaf only".

**A2. Unknown keys and typos.** SPEC says the editor preserves other keys, but not what the loader does with them. A typo such as `onexit` would silently do nothing. Proposed: unknown keys give a warning with "did you mean `on_exit`?", `--strict` makes them errors, and the editor keeps them. Reserve `description` (free text on layouts, nodes and leaves, ignored by the program, since JSON has no comments) and `version` (integer, `1`) at file level so later breaking changes can be detected.

**A3. `dir` naming is still open.** SPEC says "make sure the final naming is intuitive". `v` means a vertical divider line with panes side by side; tmux and vim use the opposite convention, and "vertical split" is ambiguous in plain English. Proposed: canonical values `columns` (side by side) and `rows` (stacked); `v`/`vertical` and `h`/`horizontal` stay as aliases with the meaning SPEC defines. The editor writes the canonical form.

**A4. Leaf identity.** SPEC says `title` identifies a window, but programs overwrite terminal titles (htop and the shell prompt both do). Tree-path ids (`1.0`) change when the tree is edited, which breaks state matching. Proposed: optional `id` on a leaf (stable, unique within the layout). Without one, the path id is used. Windows are identified by class/instance and PID, not by title (see B3).

**A5. Empty, optional and conditional panes.** Not specified: a leaf without `run` (open a plain shell, proposed), a pane that should be a hole (`"empty": true`, no window), and a pane that exists only when a command is available. Proposed: `when` (a shell test such as `command -v nvidia-smi`); when it fails the pane is removed and its sibling takes the space, so one layout works on machines without a GPU.

**A6. The tree cannot express every layout.** A binary or N-way tree makes guillotine layouts only; a pinwheel or a pane spanning two rows of an otherwise irregular grid is impossible. Proposed (later): an alternative `grid` node with CSS-style areas, for example `"areas": ["cpu cpu net", "cpu cpu gpu"]` with `sizes` for columns and rows. `compute` would return the same `LeafRect`s.

**A7. Numeric edge cases, to be written into section 3.**
- Margins are rounded to integers; an odd margin is split floor/start, ceil/end so the gap is exact (implemented, not yet in SPEC).
- Each leaf uses its own margin; the gap between a margin-0 pane and a margin-8 pane is 4.
- `at_basis: "visible"` uses the margin of the split node; descendants with another margin make the window differ by the difference.
- `at` of `0`, `100%`, `-100%`, or larger than the area is an error. Decimals such as `33.3%` are allowed.
- A bare number means pixels. Without any `frac` entry in `sizes`, the last child takes the leftover.
- SPEC rule 6 says "floats or integers"; the decision is integer pixels with shared boundaries.

**A8. Command line resolution.** Section 1 shows `--layout three`; section 11 also says "or as the second argument". The groups idea (`tilepane 3 5`) collides with that. A file named `3` collides with layout `3`. Proposed: an argument that is an existing file or ends in `.json` is a file; any non-file arguments after a file are layout names from that file; non-file arguments with no file before them are layout names from the default config. `--layout` forces a name explicitly. Options before the first `--json` apply to every task. `--dry-run`, `--close` and `--toggle` apply to all tasks.

**A9. State key and `--close`/`--toggle` semantics.** Proposed key: (absolute config path, layout name, monitor connector). `--close 3` closes every instance of layout 3 on every monitor unless `--monitor` narrows it. `--toggle` is per task: a task is "open" when at least one of its windows is alive. `--close all` closes everything tilepane opened. Stale state (reboot, crash, windows closed by hand) is detected by checking that the recorded windows still exist.

**A10. Exit codes, output and logging.** Only the multi-task failure case is specified. Proposed: 0 success, 1 at least one task failed, 2 usage or config error. `--list` prints `name`, number of panes and source file, one per line. `-v`/`--verbose` prints decisions (chosen terminal, monitor, rectangles); a log file in `~/.local/state/tilepane/` records window placement failures.

### B. Backend and platform risks (step 4 onward)

**B1. Work area per monitor.** SPEC says to subtract panels if the system reports the work area. On the dev machine `_NET_WORKAREA` is a single rectangle (`65, 30, 6463x2322`) covering the whole virtual screen, not one per monitor, and the Unity launcher and top bar are only on some monitors. Per-monitor work area has to be computed from the strut hints of panel windows (`_NET_WM_STRUT_PARTIAL`) or `_GTK_WORKAREAS`, intersected with each monitor. Proposed: a layout key `area` with `"work"` (default) or `"full"` (ignore panels).

**B2. Client-side decorations.** GTK3 terminals with client-side decorations usually report invisible shadow borders through `_GTK_FRAME_EXTENTS`, not `_NET_FRAME_EXTENTS`. Without correcting for them the visible windows will not line up with the computed rectangles, which breaks the exact margins. To verify in step 4 with gnome-terminal 3.52 on this machine. `decorations: false` needs Motif hints (`_MOTIF_WM_HINTS`) on X11 and may be impossible with CSD terminals; xterm is the fallback.

**B3. gnome-terminal server model.** gnome-terminal runs one server process; new windows are requests to it, so the PID and exit status of the launched command are not the window's. Identification by `--class`/`--name`, readiness detection and `--wait` behaviour need a spike. Title handling: terminals let programs override titles; gnome-terminal needs its profile's title mode set to "keep initial title" for a static title.

**B4. `snap: "cell"`.** SPEC says the cell size is "obtained from the terminal/font or measured after the first window opens" but not how. Proposed: open the window with `--geometry=COLSxROWS` computed from an estimate, read back the real pixel size and compare, then adjust once. Terminals have a minimum size (and window padding), so a tiny pane may not be reachable; this must produce a warning and not an exception. The leftover (up to one cell) stays on the right and bottom, which makes the right and bottom gaps wider than the left and top; proposed option `snap_align` (`start`, `center`) to spread it.

**B5. Window lifecycle.** Unspecified: how readiness is detected (wait for the map event, timeout proposed 5 s per window), what happens when a window never appears (report the task as failed, continue), stacking order (task order, last on top), focus (which window ends up focused; proposed: none changed, or `focus` on one leaf), workspace placement, and whether windows are started in parallel for speed. Maximized and fullscreen state must be cleared before moving.

**B6. HiDPI and scaling.** SPEC's default is "logical, scaled pixels", but X11 reports physical pixels and has no per-monitor logical size. Proposed: on X11 all values are X pixels; on Wayland logical pixels from the compositor. Documented in CONFIG.md.

**B7. Wayland.** The decision from step 1 is swappable backends. An untested idea that would cover GNOME and KDE Wayland cheaply: start terminals as X11 clients (`GDK_BACKEND=x11`, xterm) and place them with the X11 backend through XWayland. This needs a spike on a GNOME Wayland session, which this machine is not. Until then, GNOME Wayland remains "not ready" in `--doctor`.

**B8. Process model.** Not stated whether `tilepane` stays running. Proposed: no resident process. Each pane runs a small wrapper (`python -m tilepane.runner <spec>`), which handles `run` lists, `on_exit`, restart delays, `cycle` mode and `--for`; this avoids shell quoting problems. Only `--watch`, the editor and a possible hotplug daemon stay resident.

**B9. Terminal capability matrix.** Title, class, geometry, font, profile and exit behaviour differ per terminal. `profile` and `font_size` are not available as command-line options in every terminal. Proposed: a table in CONFIG.md, a warning (not an error) when a requested feature is unsupported, and custom terminals through a template, for example `"terminal": {"cmd": ["foot", "--title", "{title}", "--", "{command}"]}`.

**B10. Hotplug and login race.** At login the monitors or panels may not be ready yet, and `monitors` aliases may point at a connector that is not connected. Proposed: an unknown alias is a task error; `--wait-monitors N` retries for up to N seconds; the GNOME autostart example uses it.

### C. Behaviour gaps

**C1. Command execution.** "Executed through the shell" does not say which shell, whether it is interactive or login (aliases, virtualenv, `nvm`), how `cwd` and `env` values expand (`~`, `$VAR`), or what happens when `cwd` does not exist. Proposed: `$SHELL -lc` for strings (a list stays a sequence of shell commands, as in SPEC), `~` and `$VAR` expanded in `cwd` and `env`, and a missing `cwd` is an error shown in the pane.

**C2. `on_exit` details.** `keep` should be defined: print the exit status, then keep an interactive shell (proposed) or wait for a key. `restart` needs protection against a crash loop: a minimum `restart_delay` (default 1 s), `max_restarts`, and backoff. `sequence` needs a failure policy: proposed `stop_on_error` (default `false`, matching "next command starts when the previous ends"). `cycle` needs a rule for commands that never exit (kill on interval) and for interactive ones.

**C3. Demo mode.** The pool covers commands that are missing, but not commands that exist and fail: `dmesg -w` is restricted on Ubuntu, `journalctl -f` shows only the user's own messages without the right group, and `ping` needs a network. On the dev machine most of the fun commands are absent, so shell-loop fallbacks do the work; they should be good-looking.

**C4. Reconciliation.** "Move/rearrange instead of opening new windows" does not cover a layout that is partly open, a layout edited since it was opened (leaf ids changed), or windows the user has moved on purpose. Proposed: match recorded windows by leaf id, open the missing ones, close the extras only with `--prune`, and always re-place the matched ones.

**C5. Scope and testing.** Not stated: Linux-only (proposed, X11 first), minimum Python (3.9 set in `pyproject.toml`), dependencies (`python-xlib` optional extra), and how to test the backends. Proposed: geometry and config in plain unit tests (done and to come), backend tests under Xvfb with xterm in CI.

### D. Editor and security

**D1. The local server is an attack surface.** "127.0.0.1 only" is not enough: any web page the user visits can send requests to `localhost` (including DNS rebinding), and the server can save files and, through "Open on screen" and "Test here", start arbitrary commands from JSON. Required: a random per-session token in the URL and in every request, `Host` and `Origin` header checks, writes only to the files that were opened, and no endpoint that takes a path or a command from the request. This belongs in section 5.

**D2. Layout files are programs.** Opening a JSON file runs its `run` commands. Proposed: README warning; `tilepane --dry-run` lists the commands; remote import (if added) requires showing the commands and a confirmation.

**D3. Editor behaviour not specified.** Editing N-way `children`/`sizes` (or converting between binary and N-way), undo and redo, minimum pane size warnings, preview of cell snapping, how validation errors are shown, whether unknown keys survive a save (proposed: yes, in original order), JSON formatting (two-space indent, stable key order).

**D4. Standalone parity.** The standalone HTML must embed the schema and the geometry logic, so the JavaScript geometry must match `geometry.py`. Proposed: share test vectors (a JSON file of layouts and expected rectangles) between Python and JS tests.

### E. Wording and consistency fixes to SPEC.md

- Section 8 (open questions) and section 9 (decisions) should record what is now decided: X11 first with swappable backends, position-based monitor numbering, integer pixels, `frac`, the odd-margin rule.
- Add a glossary: layout (a named tree), pane (a leaf rectangle), window (the terminal window in a pane), task (layout plus monitors).
- Section 1 and section 11 disagree on the second positional argument (A8).
- The project is public on GitHub under GPL-3.0, so section 8's question "is it shared with others" is answered: yes. Packaging and documentation should assume other users.

## 3. Ideas

Beyond section 6 of SPEC.md.

**Layout power**
- `grid` areas as an alternative to trees (A6).
- `when`/`optional` panes that collapse when a command is missing (A5).
- Variants chosen by monitor size or count, for example portrait versus landscape, or three-monitor versus laptop-only, in one file.
- `repeat`: generate panes from a list, `tilepane ssh.json --var hosts=a,b,c` makes one pane per host, with an automatic grid.
- `host` on a leaf: run the command over ssh, with reconnect.

**Pane content**
- Built-in meters, `tilepane-widget cpu|mem|net|disk|gpu|clock`, pure Python reading `/proc`, drawn with ANSI colours and sparklines. Dashboards and `--demo` then work with no external packages.
- Non-terminal panes: place any application window (browser in app mode, `mpv`, a log viewer), launched by command or adopted by matching class or title.
- Attach a pane to a tmux or zellij session.
- Per-pane colour, theme, font and background opacity.

**Behaviour**
- `--daemon`: follow monitor hotplug and resolution changes, pick and apply the matching layout automatically.
- `--zoom <pane>`: toggle one pane to fill the monitor and back, like tmux zoom.
- `--cycle 3,5,7 --interval 60`: rotate layouts on a wall display.
- Failure indication: desktop notification and a title marker when a pane's command exits non-zero.
- Broadcast typing to selected panes (X11 XTEST), for administering several servers at once.
- Wallboard options: `below`, `skip_taskbar`, `sticky`, and a slow pixel shift against burn-in on OLED screens.

**Tooling**
- `--dry-run --ascii`: draw the layout as boxes in the terminal, with no image dependency; also useful in tests and the README.
- Editor "capture" button: pick a window with the mouse, record its rectangle as a pane.
- `tilepane --new`: a small interactive wizard (rows, columns, commands) that writes a first layout.
- `tilepane --install-autostart <layout>` and `--install-shortcut`: write the `.desktop` file or GNOME keybinding.
- Shell completion for layouts, monitors and options (already in SPEC section 6).
- Gallery of example layouts in `examples/`, each with an ASCII preview in its README.
- Import of a layout from a URL or gist, with the confirmation from D2.
