# tilepane: specification

A tool that opens terminal windows at precisely defined positions on the screen (per monitor) and starts the desired commands in them (htop, watch, nvidia-smi, and so on). Layouts are defined in JSON files and can be edited with the mouse in a browser.

Repo: `tilepane`, default branch `master`. Language: Python 3 (3.9 or newer), standard library only; `python-xlib` is an optional dependency for the X11 backend. Platform: Linux, X11 first (see section 4).

The authority for configuration keys is the JSON schema (`src/tilepane/tilepane.schema.json`). `docs/CONFIG.md` is generated from it and lists every key with type, default, inheritance and description. This document describes behavior; it does not repeat every key. `docs/SPEC-REVIEW.md` records the review behind several decisions below.

## Glossary

- **layout**: a named tree that describes how a monitor is divided.
- **split**: a tree node that divides its area into two or more children.
- **leaf** or **pane**: a rectangle of the layout. Every non-empty leaf gets one terminal window.
- **window**: the terminal window that tilepane opens for a pane.
- **task**: one layout (from a file or the default config) plus its target monitor(s).

## 1. Goal and usage

```
tilepane --json meters.json                    # open the layout described by a JSON file (monitor 0)
tilepane --json meters.json --monitor 2        # same, on monitor 2
tilepane --json meters.json --layout three     # a specific layout, if the file contains several
tilepane --json a.json --monitor 0 --json b.json --monitor 1   # several tasks (see section 14)
tilepane meters.json                           # short form: same as --json meters.json
tilepane meters.json three                     # short form: layout "three" from the file
tilepane 3                                     # layout named "3" from the default config
tilepane 3 5                                   # layouts 3 and 5 from the default config
tilepane --list [file.json]                    # list layouts (default config if no file is given)
tilepane --close 3                             # close the windows of layout 3
tilepane --close all                           # close everything tilepane opened
tilepane --toggle 3                            # open if closed, close if open
tilepane --edit                                # start the browser editor (localhost)
tilepane --doctor                              # print environment info (session type, monitors, terminal)
tilepane --monitors                            # list monitors with their numbers, names, sizes and positions
tilepane --dry-run 3                           # print the computed rectangles without opening anything
tilepane --explain on_exit                     # print the description of a configuration key
tilepane --demo                                # random split with fun commands (see section 10)
```

Other options: `--for DURATION` (close the windows opened in this run after that long, see section 10), `-v`/`--verbose` (print decisions: chosen terminal, monitor, rectangles), `--strict` (unknown configuration keys are errors), `--wait-monitors N` (retry monitor detection for up to N seconds, for use at login), `--eval-when` (with `--dry-run`: evaluate `when` conditions; by default dry-run runs nothing), `--version`, `-h`/`--help`.

### Argument interpretation

An argument is a **file** if it is an existing file or ends with `.json`. Otherwise it is a **layout name**.

- A file starts a new task. Layout names that follow a file, and `--layout NAME` options, select layouts from that file. Several names in one task open each layout.
- Layout names with no file before them select layouts from the default configuration (`tilepane 3 5`).
- `--layout NAME` with no task yet starts a default-config task.
- `--monitor` belongs to the task being built. Before the first task, `--monitor` is the default for all tasks that do not set their own.
- If a file contains exactly one layout, it is used when none is named. If it contains several and none is named, it is an error that lists the names.
- A file named like a layout (for example a file called `3`) wins over the layout. Use `--layout 3` to force the name.
- `--dry-run`, `--close`, `--toggle`, `-v`, `--strict` apply to all tasks.

Layout names can be numbers or words ("3", "cpu-dash").

### Exit codes and output

- `0`: success. `1`: at least one task failed, including an invalid configuration file or an unknown monitor (the other tasks were still run). `2`: usage error (unknown option, missing value, a feature that is not implemented yet).
- Errors go to stderr, one per line, prefixed with the task (file and layout) and the key path, for example `meters.json: layouts[0].split.b.run: must be a string or a list of strings`.
- `--list` prints one layout per line: name, number of panes, source file.
- `-v` additionally prints the chosen terminal, backend, monitor and every computed rectangle. Placement failures are also logged to `~/.local/state/tilepane/tilepane.log`.

## 2. Configuration (JSON)

Default location, when no file is given: `$XDG_CONFIG_HOME/tilepane/config.json` (`~/.config/tilepane/config.json`). When a file is given, only that file is read: the default config is never merged in, and `defaults` and `monitors` come from the file in use. (`--config` is an alias of `--json`.) All behavior is configurable here. A layout is a **tree**: a node is either a split (`dir` with `a`/`b`/`at` or `children`/`sizes`) or a leaf (`run` and so on).

```json
{
  "$schema": "https://raw.githubusercontent.com/anttiraisala/tilepane/master/src/tilepane/tilepane.schema.json",
  "version": 1,
  "defaults": {
    "terminal": "auto",
    "margin": 8,
    "outer_margin": null,
    "snap": "cell",
    "on_exit": "keep",
    "decorations": true
  },
  "monitors": {
    "left": "DP-1",
    "main": "HDMI-1"
  },
  "layouts": [
    {
      "name": "3",
      "margin": 8,
      "outer_margin": 16,
      "split": {
        "dir": "columns",
        "at": "60%",
        "a": { "run": "htop", "cwd": "~", "title": "htop" },
        "b": {
          "dir": "rows",
          "at": "300px",
          "a": { "run": "watch -n1 sensors" },
          "b": { "run": "nvidia-smi -l 1", "on_exit": "restart", "when": "command -v nvidia-smi" }
        }
      }
    }
  ]
}
```

A single-layout file may be flat: `name`, `margin`, `split` at the top level, without a `layouts` list (the name defaults to the file name without extension). A file must not have both `layouts` and a top-level `split`.

### Inheritance and precedence

Settings that apply to windows inherit down the tree. The effective value for a leaf is the first one found in this order: the leaf, its ancestor split nodes (nearest first), the layout, the file's `defaults`, the built-in value. `env` is merged key by key instead of replaced. Keys that inherit: `terminal`, `profile`, `font_size`, `snap`, `on_exit`, `restart_delay`, `max_restarts`, `stop_on_error`, `decorations`, `cwd`, `env`, `margin`. `at_basis` inherits through split nodes only. Keys that never inherit: `run`, `title`, `id`, `mode`, `interval`, `when`, `empty`, `description`. `outer_margin` and `area` are set on the layout or in `defaults`. `docs/CONFIG.md` marks every key.

Built-in values: `terminal` `"auto"`, `margin` 8, `outer_margin` none, `at_basis` `"outer"`, `area` `"work"`, `snap` `"cell"`, `on_exit` `"keep"`, `restart_delay` 1, `max_restarts` 0 (unlimited), `stop_on_error` false, `decorations` true, `mode` `"sequence"`.

### Validation, unknown keys, versions

- Types, enumerated values and structure are validated when the file is loaded. All problems are collected and reported together, each with its key path.
- An unknown key is a warning with a suggestion ("did you mean `on_exit`?"). With `--strict` it is an error. The editor keeps unknown keys when it saves.
- `version` is an integer, currently `1`. A higher version than the program supports is an error. `description` (free text on the file, layouts, nodes and leaves) is ignored by the program; JSON has no comments, so use it instead.
- A key on the wrong level (for example `run` on a split node) is an error.

### Split node

- `dir`: the arrangement of the children. **Canonical values: `"columns"` (children side by side, a on the left) and `"rows"` (children stacked, a on top).** Accepted aliases: `"v"` and `"vertical"` mean `columns`; `"h"` and `"horizontal"` mean `rows` (`v` is a vertical divider line). Tools write the canonical form. Note that tmux uses the opposite convention for `-h`/`-v`.
- `at`: the split point, measured from the size of the **area being split** (before margins):
  - `"60%"`: percentage of the area width/height from the left/top
  - `"300px"`: pixels from the left/top (a bare number means pixels)
  - `"-300px"` / `"-40%"`: measured from the right/bottom
  - Default `"50%"`. `0`, `100%`, or a value larger than the area is an error.
- `a`, `b`: child nodes (a split or a leaf), arbitrary depth.
- An optional `margin` per node overrides the inherited margin for everything below it.

### N-way split
In addition to the binary tree, allow a `children` list and `sizes` (in the style of CSS grid), so that for example three columns are easy to write:

```json
{ "dir": "columns", "sizes": ["1frac", "2frac", "300px"], "children": [ {...}, {...}, {...} ] }
```
`sizes` entries are `Nfrac` (a share of the space left after the fixed sizes, divided proportionally), `Npx` or `N%`. Without `sizes`, all children are `1frac`. If no entry is a `frac`, the last child takes any leftover space. Sizes that exceed the area are an error. `children` cannot be combined with `a`, `b` or `at`.

### Leaf
- `run`: a command (string) or a list of commands. Strings are run through the user's shell as `$SHELL -lc <command>` (`/bin/sh` if `$SHELL` is unset). A list is executed **sequentially in the same terminal** (see section 10). Without `run`, the pane opens an interactive shell.
- `cwd`: working directory. `~` and `$VAR` are expanded. A directory that does not exist is an error shown in the pane.
- `title`: window title. Programs may overwrite it; windows are not identified by title.
- `id`: optional stable identifier, unique within the layout (letters, digits, `_`, `-`, `.`). Without it the tree path (`1.0`) is used. `id` is what state management uses to match windows to panes.
- `terminal`: overrides the terminal for this pane. A name, or a custom command template, for example `{"cmd": ["foot", "--title", "{title}", "--", "{command}"]}`.
- `profile` / `font_size`: optional terminal-specific settings; a terminal that cannot honor them produces a warning, not an error.
- `snap`: `"cell"` | `"pixel"`.
- `on_exit`: `"keep"` | `"close"` | `"restart"` (+ `restart_delay` in seconds, `max_restarts`).
- `env`: extra environment variables (string values; `~` and `$VAR` expanded).
- `mode`, `interval`, `stop_on_error`: see section 10.
- `when`: a shell command. When it exits non-zero the pane is removed and its sibling takes the space (a binary split with one child left is replaced by that child, an N-way split drops the child and its size). If every pane is removed, the layout fails. Use it so one layout works on machines without, for example, a GPU. `when` commands are run only when opening windows (or with `--eval-when`).
- `empty`: `true` reserves the rectangle but opens no window. It cannot be combined with `run`.
- `decorations`: `false` removes window borders when the terminal and window manager allow it.

## 3. Geometry (core logic)

A pure function with no windowing dependencies, easy to unit test:

`compute(layout, monitor_rect) -> list[LeafRect]`

All values are integer pixels. On X11 they are X pixels; on Wayland they are the compositor's logical pixels. Rules:
1. Start with the work area of the monitor (`area: "work"`, the default) or the full monitor (`area: "full"`). The work area excludes panels and docks, computed **per monitor** from the panels' strut hints, because the window manager's own work-area property can be a single rectangle for the whole screen.
2. **The margin lies inside every rectangle on all four sides, and its value is the total gap between two windows.** Example, margin 8: the gap between windows is 4 + 4 = 8, and at the outer edge of the screen it is 4. An odd margin is split with the start side (left/top) getting the floor and the end side the ceiling, so the gap between neighbours is always exactly `margin`. Margins are rounded to whole pixels.
3. A split is always made from the rectangle **outside** the margin. The margin is applied only at the leaf level: window = leaf rectangle minus its insets. Each leaf uses its own effective margin; between a margin-0 pane and a margin-8 pane the gap is 4.
4. `outer_margin` (optional): if set, the margin at the outer edge of the screen is this value (the total value for the outer edge, not halved), while the inner gaps stay according to `margin`. Implementation: subtract outer_margin from the whole area first, then use the inner margins; leaves at the outer edge get no extra inset. Unit tests verify that the edge is not counted twice.
5. A pixel value `at: "300px"` means the size of the area before the margin. An additional option `at_basis: "outer" | "visible"` (default `outer`) can switch the interpretation so that the visible window is exactly the given size. `visible` uses the margin of the split node; a descendant with a different margin makes the window differ by that difference.
6. **Rounding:** every split boundary is computed as a float and rounded once; neighbouring panes share the same boundary value, so there are no gaps and no overlaps.
7. A pane that ends up with no room (width or height of zero or less after the insets) is an error that names the pane.

### Snap
- `"cell"` (**default**): the inner size of the window is rounded down to whole character cells. The position of the window (top-left corner) stays at the computed point; a gap of at most one cell remains on the right/bottom. The cell size comes from the window's own size hints (`WM_NORMAL_HINTS`: base size and resize increments), so no measuring is needed; after the first window of a terminal is placed, later windows start with an exact `--geometry`. A pane smaller than the terminal's minimum size produces a warning. An optional `snap_align` (`"start"` | `"center"`) is reserved for spreading the leftover.
- `"pixel"`: the size is forced to exactly the computed pixel size when the terminal and the window manager allow it (kitty, alacritty and so on). The background fill takes care of the empty edge.

## 4. Window placement (backends)

Backends are chosen at runtime (`$XDG_SESSION_TYPE`, `$XDG_CURRENT_DESKTOP`, the running window manager) behind one interface; `--doctor` reports which one applies and whether it is ready.

- **X11 (first, implemented first):** `python-xlib` (installed as the optional `x11` extra), with `xdotool`/`wmctrl` as a fallback. Windows are identified by a unique WM_CLASS/instance name (`tilepane`, `<layout>:<leaf-id>`) and the PID, never by title. Placement uses `_NET_MOVERESIZE_WINDOW`, after clearing maximized and fullscreen state, and corrects for frame extents (`_NET_FRAME_EXTENTS`, and `_GTK_FRAME_EXTENTS` for GTK client-side decorations; to be verified with gnome-terminal). `decorations: false` uses the Motif hints (verified on Compiz) and may be impossible with client-side-decorated terminals. `snap: "pixel"` removes the window's resize increments before placing (verified with gnome-terminal and xterm). This covers Compiz (the development machine), Mutter and Cinnamon on X11, KWin, Xfwm and others that follow EWMH.
- **Tiling window managers** (i3, bspwm, awesome, dwm and others) place windows themselves; the user adds a floating rule for class `tilepane`. `--doctor` prints a note when one is detected.
- **Wayland:** windows cannot be positioned from the outside, so each compositor has its own backend: sway and Hyprland through their IPC (`swaymsg`, `hyprctl`), KDE through a KWin script over D-Bus, GNOME through a small GNOME Shell extension over D-Bus. These are recognised by `--doctor` and implemented after the X11 backend. Open question: starting terminals as X11 clients (`GDK_BACKEND=x11`) and placing them through XWayland (needs a spike on a GNOME Wayland machine). A Wayland compositor with no backend is reported by `--doctor` with the advice to use an X11 session.
- **Mint/Cinnamon:** X11, same path as above.

### Window lifecycle

- No resident process (except `--watch`, the editor and a possible daemon). Each pane runs a small wrapper (`python -m tilepane.runner <spec>`) inside the terminal; it handles `run` lists, `on_exit`, restarts, `cycle` mode and `--for`, which avoids shell quoting problems.
- A window counts as opened when its map event is seen; timeout 5 s per window. A window that never appears fails the task and the other tasks continue. Windows are started in parallel where the terminal allows it.
- Panes are opened one after another; the new window is the one that appears in the window list after the terminal starts (class `tilepane` narrows it down). Stacking order follows task and pane order (last on top). Focus is not changed unless a leaf is marked for it (reserved). Windows open on the current workspace unless `workspace` is set (reserved).
- With `--wait-monitors N`, monitor detection and alias resolution are retried for up to N seconds; use it in autostart, where monitors or panels may not be ready at login.

### Terminals

`terminal: "auto"` tries in order kitty, alacritty, gnome-terminal, xterm. One adapter per terminal handles title, class, command, geometry, font and `on_exit` behavior. A table in `docs/CONFIG.md` lists what each terminal supports. A requested feature the terminal cannot honor is a warning. Custom terminals are defined with a `cmd` template (see Leaf). gnome-terminal runs one server process, so the launched process is not the window's process; windows are identified by class and instance name. Its title mode must be set to keep the initial title for a fixed `title`.

### State management

The program marks the windows it opens (class/instance + PID + a state file in `~/.local/state/tilepane/`). The state key is (absolute config path, layout name, monitor connector). `--close NAME` closes every instance of that layout on every monitor (narrow it with `--monitor`); `--close all` closes everything tilepane opened. `--toggle` works per task: a task is open when at least one of its windows is alive. Stale state (reboot, crash, windows closed by hand) is detected by checking that the recorded windows still exist.

If a layout is already open, tilepane reconciles instead of opening duplicates: windows are matched to panes by leaf id and re-placed, missing ones are opened, and extra ones are closed only with `--prune`.

## 5. Browser editor (`tilepane --edit`)

- Python stdlib HTTP server (`127.0.0.1` only), static HTML/JS front end, no heavy build step.
- View: a screen drawn in proportion to the monitor. Click a pane, then "split horizontally/vertically" (writing the canonical `columns`/`rows`). Dragging a split line with the mouse changes the `at` value; the value can be switched between % and px, and the direction (from left/top or from right/bottom) can be chosen. N-way `children`/`sizes` splits can be edited (a third pane in the same direction converts a binary split to N-way and back). Undo and redo. A pane too small for its margin is flagged.
- Pane side panel: run, cwd, title, on_exit, snap, margin, and the other leaf keys, with labels and descriptions taken from the schema.
- Margins are visible in the preview at the correct scale. The preview can show the cell snap.
- Layout and monitor selection, new/copy/delete layout.
- Saving writes the same JSON: unknown keys are kept in their original order, two-space indent. Validation errors are listed next to the pane they belong to and block saving.
- A "Test here" button: actually opens the layout on the selected monitor.

### Server security

The local server can write files and, through "Test here", start commands from JSON, and any web page the user visits can send requests to `localhost` (including through DNS rebinding). Requirements: a random per-session token in the URL and in every request, `Host` and `Origin` header checks, writes only to the files that were opened (no endpoint accepts a path or a command from the request), and the server stops when the editor tab closes or after an idle timeout.

## 6. Extra ideas (prioritize later)

- Layout inheritance/templates (`"extends": "3"`, reusable `templates`).
- GNOME shortcut and autostart examples in the README; `tilepane --install-autostart`.
- Borderless, always-on-top, sticky (on all workspaces) options: `above`, `sticky`, `workspace`, `skip_taskbar`, `below`.
- Per-workspace opening (`"workspace": 2`).
- `tilepane --snapshot`: save the current window arrangement as a layout.
- Shell completion for layout and monitor names.
- `--watch`: when the JSON file is saved (or the editor saves it), the layout is updated on screen immediately.
- Per-pane color or title, to tell meters apart at a glance.
- `--dry-run --png layout.png` and `--dry-run --ascii`: draw the layout as an image or as boxes in the terminal.
- `grid` node with CSS-style areas, for layouts a tree cannot express.
- More ideas (built-in meters, `repeat`, `--daemon`, `--zoom`, ...) are listed in `docs/SPEC-REVIEW.md`.

## 7. Implementation order

1. `--doctor`: find out the user's environment (session type, desktop, versions, monitors, available terminals). **Do this yourself by running the commands; do not ask the user.** Report the results and propose a backend.
2. Geometry core + unit tests (margin, outer_margin, negative `at`, percentages, rounding, deep trees, `frac` sizes).
3. Config loading and validation, JSON schema, generated `docs/CONFIG.md`, `--explain`, command line task parsing, `--dry-run`.
4. One backend all the way through (the one that fits the user's environment): one terminal, one window at the right place, then the whole layout.
5. Monitor support (aliases, hotplug and `--wait-monitors`), `--monitors`, and executing multi-task command lines (section 14). The per-monitor work area was done in step 4.
6. `on_exit`, `snap`, state management, `--close` / `--toggle`.
7. `--demo` (section 10).
8. Browser editor (section 13).
9. README, installation (pipx / `pip install -e .`), example configuration.

## 8. Open questions (to be resolved during the work)

- GNOME and KDE on Wayland: the XWayland approach versus an extension or script per compositor (needs a spike on a machine that runs them).
- Whether `_GTK_FRAME_EXTENTS` is enough to line up client-side-decorated windows exactly (the code handles it; no machine with such windows has been tested).
- Whether the meters should be always-on-top / sticky by default (current default: no).

## 9. Decisions so far

- Name: **tilepane**. Linux, Python 3.9+, standard library only, optional `python-xlib`.
- Margin: a total gap, half on each side (floor/ceiling for odd values); optional `outer_margin`. All geometry in integer pixels with shared boundaries.
- `at`: percentage or pixels, from the left/top or from the right/bottom (negative).
- `dir`: canonical `columns` / `rows`; `v`/`vertical` and `h`/`horizontal` are aliases.
- Size unit for shares: `frac` (not `fr`).
- `snap`: default `"cell"`, alternative `"pixel"`.
- `on_exit`: default `"keep"`, alternatives `"close"`, `"restart"`.
- Everything is configurable in JSON; the schema is the authority; unknown keys warn (error with `--strict`); `version` is `1`.
- Monitors are numbered by position (section 12). X11 backend first; other backends behind the same interface.
- No resident process; panes run through a wrapper.
- The project is public (GPL-3.0), so packaging and documentation assume other users.

## 10. Multiple commands per pane and demo mode

### Multiple commands in a leaf
Every leaf (rectangle) gets its own terminal window. The leaf's `run` can be a string or a list. A list means n commands, executed **one after another in the same terminal** (`mode: "sequence"` is the default). For example `cd`, `source venv`, then `htop`: the next command starts when the previous one ends. By default the next command starts whatever the exit status; with `stop_on_error: true` the sequence stops at the first failing command.

Later optional extras, selected with the `mode` field:
- `"cycle"`: the commands rotate every `interval` seconds in the same window (for example 10 s htop → 10 s iotop → 10 s nethogs). `interval` is required for this mode. The running command is terminated when the interval ends.
- `"parallel"`: run side by side in the same window (needs a tmux/zellij-style solution; optional and a later phase).

```json
{ "run": ["htop", "iotop", "nethogs"], "mode": "cycle", "interval": 10 }
```

### on_exit
- `"keep"`: when the command ends, print its exit status and keep an interactive shell in the window.
- `"close"`: close the window when the command ends.
- `"restart"`: start the command again after `restart_delay` seconds (default 1). `max_restarts` (default 0, unlimited) stops a crash loop; the window then behaves as `keep`.

### Demo mode (`--demo`)
- `tilepane --demo` randomly splits the monitor into a few rectangles and starts a fun command in each.
- The number of panes defaults to a random pick of 3, 4, 5 or 6. The demo **does not close by itself**: the terminal windows stay open even after the command ends (`on_exit: keep`). `--for 30s` is optional.
- Options: `--demo N` (number of panes), `--seed S` (reproducible result), `--monitor`, `--for 30s`, `--save demo.json` (saves the resulting layout as JSON that can be edited in the editor).
- Randomness of the split: direction, `at` (20–80 %, sometimes in pixels), depth, margin (for example 4–16).
- Command pool; pick only commands that are found (`which`), and for missing ones use plain shell loops:
  `top`, `htop`, `watch -n1 date`, `watch -n2 'ls -la'`, `vmstat 1`, `watch -n1 'cat /proc/loadavg'`, `watch -n5 df -h`, `journalctl -f`, `dmesg -w`, `ping 1.1.1.1`, `watch -t -n1 'date +%T | figlet'`, `cmatrix`, `sl`, `fortune | cowsay`, `cal`, `sensors`, `nvidia-smi -l 1`.
- It must not require installed packages, and every command has a fallback command. A command that exists but fails (`dmesg -w` is restricted on Ubuntu, `journalctl -f` needs group membership, `ping` needs a network) is handled by running it under a check and falling back to the shell loop if it exits within a second.
- Decisions made when it was built (step 7): the seed is always printed so any demo can be repeated; `--demo N` takes 1 to 12 panes, and the generator keeps every pane at least 240x120 px (before margins), so a pane count that does not fit the monitor is an error. Missing commands share fallbacks, so panes are picked to run different commands while the pool lasts. Pool commands that use shell syntax run through `sh -c`, so the user's login shell (fish, zsh) does not matter. `--monitor all` (or a list) makes one layout per monitor (`demo-0`, `demo-1`, ...). A new demo replaces the previous unsaved demo on the same monitor; `--close all` closes demos too. A demo saved with `--save` is tracked under that file, so `tilepane demo.json` later re-places the same windows instead of opening duplicates.
- `--for DURATION` (`30s`, `5m`, `1h`, or seconds) is handled by the runner and works with any layout, not only the demo: when the time runs out the pane's commands (and a shell started after them) are stopped and the window closes, whatever `on_exit` says. It applies to windows opened in that run; windows that are only re-placed keep their earlier lifetime.

## 11. Layout files

- Every layout has a `name`; names are unique within a file. If a JSON file contains only one layout, it is used by default. If it contains several, the layout is chosen by name (`--layout name`, or a name after the file).
- A single-layout file may be flat: `name`, `margin`, `split` at the top level without a `layouts` list. In a multi-layout file, `layouts` is a list of objects that have a `name`.
- Command line: `tilepane --json path.json [--layout name] [--monitor N]`. The positional form `tilepane path.json [name]` also works. `--monitor` defaults to 0.

## 12. Monitor detection and numbering

- In Linux, monitors have no persistent number. `xrandr --listmonitors` gives indices (0:, 1:), but the order depends on how the X server enumerates them and can change on reboot or when a cable is unplugged. The persistent identifier is the connector name (`HDMI-1`, `DP-2`, `eDP-1`).
- tilepane defines its own numbering: **monitors are numbered by position, from left to right and from top to bottom** (primarily by x, secondarily by y, then by connector name). `0` is the leftmost monitor. This is decided; numbering is not primary-based. The default monitor is 0.
- `--monitor` accepts: a number, a connector name, a config alias (the `monitors` block, whose values are a connector name or a number), `primary`, or `all`.
- An alias or connector that is not connected is a task error (see `--wait-monitors` in section 4).
- `tilepane --monitors` prints the monitors found with their numbers, names, resolutions and positions, so the user can see which number is which.

## 13. Graphical editor: architecture

- **A single self-contained HTML file** (HTML + CSS + vanilla JS, no build step, no external dependencies) that works in two ways with the same code:
  1. **Standalone:** opened in the browser directly as a file (`file://`). A JSON file is opened with a file picker and saved as a download (in Chromium the File System Access API can save directly to the file when supported).
  2. **`tilepane --edit`:** a Python stdlib server (`127.0.0.1`) serves the same HTML and adds: saving directly to the file, the real monitors (size, position) in the preview, an "Open on screen" button and `--watch` updates.
- The editor detects at runtime whether the server is available (`fetch('/api/monitors')`) and enables the extra features only then.
- The HTML embeds the schema (for labels and validation) and a JavaScript copy of the geometry. Python and JavaScript tests share one file of test vectors (layouts and expected rectangles) so the two implementations cannot diverge.
- Creating a new layout from scratch, opening a JSON file, validation, and opening the result of `--demo --save` in the editor.

## 14. Multiple tasks in one command line

A command line consists of **tasks**. A task = one layout file (or the default config) + its layouts + its target monitor(s). All tasks are opened in the same run.

```
tilepane --json cpu.json --monitor 0 \
         --json network.json --monitor 1 \
         --json disk.json --monitor 2 \
         --json logs.json --monitor 3 \
         --json gpu.json
```

Rules:
- `--json` (or a file given as a positional argument) starts a new task. The `--monitor` and `--layout` that follow belong to that task until the next task begins. Parse in order (not as separate lists). Argument interpretation is in section 1.
- `--monitor` missing → monitor 0 (or the default set before the first task).
- `--monitor` accepts a single value or a comma-separated list (`--monitor 0,1,2`), in which case the same layout is opened on each. A value is a number, a connector name, an alias, `primary` or `all`.
- The same file may appear in several tasks on different monitors.
- In a multi-layout file, choose the layout with `--layout name`. If the file contains one layout, use it.
- Geometry is computed per task from the target monitor's own size and work area.
- **Overlap:** if two tasks land on the same monitor, both are opened on top of each other. No warning, no error, no separate switch.
- An invalid task (missing file, unknown monitor, invalid JSON) is reported clearly. The other tasks are opened anyway, and a summary of successes and failures is printed at the end. The exit code is 1 if anything failed.
- `--close` and `--toggle` work with the same task structure.

## 15. Security

- A layout file is a program: opening it runs its `run` commands, and `when` commands run on opening. The README says so. `--dry-run` lists the commands and does not run anything, including `when` conditions unless `--eval-when` is given.
- If importing a layout from a URL is ever added, it must show the commands and ask for confirmation first.
- The editor server follows the rules in section 5.
