# tilepane: specification

A tool that opens terminal windows at precisely defined positions on the screen (per monitor) and starts the desired commands in them (htop, watch, nvidia-smi, and so on). Layouts are defined in JSON files and can be edited with the mouse in a browser.

Repo: `deskworks` (folder `tilepane/`), default branch `master`. Monitors, workspaces, work areas and placement arithmetic come from the `deskmap` library in the same repository. Language: Python 3 (3.9 or newer), standard library only; `python-xlib` is an optional dependency for the X11 backend. Platform: Linux, X11 first (see section 4).

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
tilepane metering.json                         # a bare file name that is not in the current directory is looked up in the config directory
tilepane 3                                     # layout named "3" from the default config
tilepane 3 5                                   # layouts 3 and 5 from the default config
tilepane --list [file.json]                    # list layouts (default config if no file is given)
tilepane --close 3                             # close the windows of layout 3
tilepane --close all                           # close everything tilepane opened
tilepane --toggle 3                            # open if closed, close if open
tilepane --edit                                # start the browser editor (localhost)
tilepane --doctor                              # print environment info (session type, monitors, terminal)
tilepane --monitors                            # list monitors with their numbers, names, sizes and positions
tilepane --workspaces                          # show the workspaces and their numbers
tilepane --identify                            # one window per monitor per workspace, saying where it should be
tilepane --dry-run 3                           # print the computed rectangles without opening anything
tilepane --explain on_exit                     # print the description of a configuration key
tilepane --demo                                # random split with fun commands (see section 10)
tilepane --uninstall [--purge] [--yes]         # remove tilepane; --purge also deletes ~/.config/tilepane
```

`--uninstall` lists what it will do and asks for confirmation (`--yes` skips it; without a terminal `--yes` is required). It closes the windows tilepane opened on every workspace, removes the program with the tool it was installed with (pipx when its venv has `pipx_metadata.json`, otherwise pip in the running Python; editable installs included), then deletes the state directory, and with `--purge` the config directory with the default config and any layouts saved there. The program is removed first: if that fails, nothing else is deleted. Layout files elsewhere and the cloned repository are never touched; the summary says so. It takes no files, layouts or other actions.

Other options: `-x`/`--exit-shell` (when everything opened or closed without errors, close the terminal tilepane was typed into: tilepane sends SIGHUP to its parent process when that is an interactive shell on a terminal, so the terminal closes that tab or window by itself; nothing is closed after a failure, or when tilepane was not started from a shell, for example by a keyboard shortcut; not allowed with `--dry-run`, `--edit` and the other actions that open no windows), `--workspace N|current|all` (see State management), `--for DURATION` (close the windows opened in this run after that long, see section 10), `-v`/`--verbose` (print decisions: chosen terminal, monitor, rectangles), `--strict` (unknown configuration keys are errors), `--wait-monitors N` (retry monitor detection for up to N seconds, for use at login), `--eval-when` (with `--dry-run`: evaluate `when` conditions; by default dry-run runs nothing), `--version`, `-h`/`--help`.

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
  "$schema": "https://raw.githubusercontent.com/anttiraisala/deskworks/master/tilepane/src/tilepane/tilepane.schema.json",
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

Settings that apply to windows inherit down the tree. The effective value for a leaf is the first one found in this order: the leaf, its ancestor split nodes (nearest first), the layout, the file's `defaults`, the built-in value. `env` is merged key by key instead of replaced. Keys that inherit: `terminal`, `shell`, `profile`, `font_size`, `snap`, `on_exit`, `restart_delay`, `max_restarts`, `stop_on_error`, `decorations`, `cwd`, `env`, `margin`. `at_basis` inherits through split nodes only. Keys that never inherit: `run`, `title`, `id`, `mode`, `interval`, `when`, `empty`, `description`. `outer_margin`, `area` and `workspace` are set on the layout or in `defaults`. `docs/CONFIG.md` marks every key.

Built-in values: `terminal` `"auto"`, `shell` `"auto"`, `margin` 8, `outer_margin` none, `at_basis` `"outer"`, `area` `"work"`, `snap` `"cell"`, `on_exit` `"keep"`, `restart_delay` 1, `max_restarts` 0 (unlimited), `stop_on_error` false, `decorations` true, `mode` `"sequence"`.

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
- `a`, `b`: child nodes (a split or a leaf), arbitrary depth. A missing `a` or `b` is an empty pane; a split with neither divides the area into two empty panes (nothing opens, which is allowed).
- An optional `margin` per node overrides the inherited margin for everything below it.

### N-way split
In addition to the binary tree, allow a `children` list and `sizes` (in the style of CSS grid), so that for example three columns are easy to write:

```json
{ "dir": "columns", "sizes": ["1frac", "2frac", "300px"], "children": [ {...}, {...}, {...} ] }
```
`sizes` entries are `Nfrac` (a share of the space left after the fixed sizes, divided proportionally), `Npx` or `N%`. Without `sizes`, all children are `1frac`. If no entry is a `frac`, the last child takes any leftover space. Sizes that exceed the area are an error. `children` cannot be combined with `a`, `b` or `at`.

### Leaf
- `run`: a command (string) or a list of commands. Strings are run through the pane's shell as `<shell> -lc <command>` (see `shell`; by default the user's `$SHELL`). A list is executed **sequentially in the same terminal** (see section 10). Without `run`, a leaf that has any other window setting (`cwd`, `title`, `terminal`, `env`, ...) opens an interactive shell.
- `cwd`: working directory. `~` and `$VAR` are expanded. A directory that does not exist is an error shown in the pane.
- `title`: window title. Programs may overwrite it; windows are not identified by title.
- `id`: optional stable identifier, unique within the layout (letters, digits, `_`, `-`, `.`). Without it the tree path (`1.0`) is used. `id` is what state management uses to match windows to panes.
- `shell`: the shell that runs the pane's commands (`<shell> -lc <command>`) and the interactive prompt afterwards. `"auto"` (default) is the user's login shell (`$SHELL`, `/bin/sh` if unset), so a zsh or fish user keeps their own setup; otherwise a name found on `PATH` (`"bash"`, `"zsh"`, `"fish"`) or a path. `SHELL` is set to it inside the pane. A shell that is not installed fails that pane only. A leaf with only `shell` opens that shell.
- `terminal`: overrides the terminal for this pane. A name, or a custom command template, for example `{"cmd": ["foot", "--title", "{title}", "--", "{command}"]}`.
- `profile` / `font_size`: optional terminal-specific settings; a terminal that cannot honor them produces a warning, not an error.
- `snap`: `"cell"` | `"pixel"`.
- `on_exit`: `"keep"` | `"close"` | `"restart"` (+ `restart_delay` in seconds, `max_restarts`).
- `env`: extra environment variables (string values; `~` and `$VAR` expanded).
- `mode`, `interval`, `stop_on_error`: see section 10.
- `when`: a shell command. When it exits non-zero the pane is removed and its sibling takes the space (a binary split with one child left is replaced by that child, an N-way split drops the child and its size). If every pane is removed, the layout fails. Use it so one layout works on machines without, for example, a GPU. `when` commands are run only when opening windows (or with `--eval-when`).
- **Empty panes.** A leaf with no keys (`{}`), or only `id`, `description` and `when`, or a missing `a`/`b`, opens no window: the rectangle stays empty. Only keys written on the leaf itself count; settings inherited from above do not fill an empty pane. `empty: true` says the same explicitly (and keeps the pane empty whatever else it has); `empty: false` asks for a window (an interactive shell) on a leaf that has nothing else. `empty: true` cannot be combined with `run`.
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
- Panes are opened one after another; the new window is the one that appears in the window list after the terminal starts (class `tilepane` narrows it down). Stacking order follows task and pane order (last on top). Focus is not changed unless a leaf is marked for it (reserved). Windows open on the workspace given with `--workspace N`, else on the layout's `workspace`, else on the current one (see State management).
- With `--wait-monitors N`, monitor detection and alias resolution are retried for up to N seconds; use it in autostart, where monitors or panels may not be ready at login.

### Terminals

`terminal: "auto"` tries in order kitty, alacritty, gnome-terminal, xterm. One adapter per terminal handles title, class, command, geometry, font and `on_exit` behavior. A table in `docs/CONFIG.md` lists what each terminal supports. A requested feature the terminal cannot honor is a warning. Custom terminals are defined with a `cmd` template (see Leaf). gnome-terminal runs one server process, so the launched process is not the window's process; windows are identified by class and instance name. Its title mode must be set to keep the initial title for a fixed `title`.

### State management

The program marks the windows it opens (class/instance + PID + a state file in `~/.local/state/tilepane/`). The state key is (absolute config path, layout name, monitor connector). `--close NAME` closes every instance of that layout on every monitor (narrow it with `--monitor`); `--close all` closes everything tilepane opened. `--toggle` works per task: a task is open when at least one of its windows is alive. Stale state (reboot, crash, windows closed by hand) is detected by checking that the recorded windows still exist.

If a layout is already open, tilepane reconciles instead of opening duplicates: windows are matched to panes by leaf id and re-placed, missing ones are opened, and extra ones are closed only with `--prune`.

**Workspaces.** Every record also holds the workspace its window is on (internally its index in the window manager's order: the EWMH desktop, or on Compiz the viewport), read from the window itself on every run, so a window moved to another workspace by hand belongs to that one and a window on all workspaces matches any. A layout instance is (state key, workspace):

- Which workspace a layout is opened, re-placed, toggled or closed on: `--workspace` on the command line if given; otherwise the layout's `workspace` key (or the file's `defaults`); otherwise the current workspace. A `workspace` that does not exist on this machine, or one on a window manager without workspaces, is a warning and the current workspace is used (a layout file may be used on several machines); `--workspace N` that does not exist is an error. The key is per layout, not per pane: one layout, one workspace (decided with the owner; a per-pane workspace can be added later without changing this).
- **Numbering** (decided with the owner): workspaces are numbered from 0 in the bottom left corner, along each row to the right, then the rows upward; with one row, 0 is the first. The grid is the one a pager publishes in `_NET_DESKTOP_LAYOUT` (orientation, columns, rows, starting corner), the viewport grid on Compiz, or one row when there is neither. The same number is used by `--workspace`, the layout key, messages, `--workspaces` and the editor. (Before this, numbers were 1-based in the window manager's order.)
- A layout opened on workspace 0 and again on workspace 1 has two sets of windows; the first set is left alone. A new `--demo` replaces only the demo on the same monitor and workspace.
- `--close NAME` closes on that layout's workspace (its `workspace` key) or else the current one; `--close all` closes on the current workspace. `--workspace N` picks another one, `--workspace all` closes on every workspace.
- New windows are moved to the chosen workspace after they appear. In the editor, a "Workspace" list in the header (and the layout panel) sets the layout's `workspace` (0 marked "bottom left"), or "not set" for none; the server reports how many workspaces the machine has.
- `tilepane --workspaces` shows the workspaces: how many, the current one, how they are arranged, the grid with tilepane's numbers and the current one in brackets, and the window manager's names when they are not the defaults. `-v` adds the window manager's own order (1-based) and the raw properties.
- **Compiz/Unity** has one large desktop (`_NET_DESKTOP_GEOMETRY` larger than the screen, at most one EWMH desktop) shown one screen-sized viewport at a time; each viewport holds all monitors. The viewports are the workspaces: their grid is columns x rows of the screen size, the current one comes from `_NET_DESKTOP_VIEWPORT`. Window positions are relative to the current viewport, so a window's workspace is the viewport its centre is in, and windows for another viewport are placed at that viewport's offset (new and re-placed windows alike) instead of being moved with `_NET_WM_DESKTOP`.
- `tilepane --identify` checks the numbering on a real machine: one window on every monitor (`--monitor` narrows it) of every workspace (`--workspace N` narrows it), each printing the workspace number, its place in the grid in words and the monitor's number, name and geometry. A new `--identify` closes the windows of the previous one; `--close all --workspace all` closes them, `--for` and `--dry-run` work as usual.
- A window manager that reports no workspaces behaves as one workspace.

Closing asks each window to close (`_NET_CLOSE_WINDOW`), checks that it went, and asks once more. A window that still stays open is reported and kept in the state, so the next `--close` tries it again. tilepane never kills a terminal process: with gnome-terminal one server owns every tilepane window. A window closed by hand (its close button) is noticed the next time tilepane runs: it is dropped from the state, and opening the layout again opens only that pane.

## 5. Browser editor (`tilepane --edit`)

- Python stdlib HTTP server (`127.0.0.1` only), static HTML/JS front end, no heavy build step.
- View: a screen drawn in proportion to the monitor. Click a pane, then "✂ Cut pane ─" (a horizontal line: top and bottom piece, written as `rows`) or "✂ Cut pane │" (a vertical line: left and right piece, written as `columns`); the cut works like the cut line below, with the line limited to the pane. Dragging a split line with the mouse changes the `at` value; the value can be switched between % and px, and the direction (from left/top or from right/bottom) can be chosen. N-way `children`/`sizes` splits can be edited (a third pane in the same direction converts a binary split to N-way and back). Undo and redo. They cover the edits of the layout and the preview as well: dragging the monitor's edges to another size, choosing another monitor or a custom size in the list, and "Reset size" are steps in the same history. The preview is not part of the file, so those steps do not mark it as changed. A pane too small for its margin is flagged.
- Pane side panel: run, cwd, title, on_exit, snap, margin, and the other leaf keys, with labels and descriptions taken from the schema.
- Margins are visible in the preview at the correct scale. The preview can show the cell snap.
- Layout and monitor selection, new/copy/delete layout.
- Saving writes the same JSON: unknown keys are kept in their original order, two-space indent. Validation errors are listed next to the pane they belong to and block saving.
- A "Test here" button: actually opens the layout on the selected monitor.

### Server security

The local server can write files and, through "Test here", start commands from JSON, and any web page the user visits can send requests to `localhost` (including through DNS rebinding). Requirements: a random per-session token in the URL and in every request, `Host` and `Origin` header checks, writes only to the files that were opened (no endpoint accepts a path or a command from the request), and the server stops when the editor tab closes or after an idle timeout.

### As built (step 8)

- `tilepane --edit [FILE]` edits one file (the default config when none is given; a file that does not exist yet is written on the first save). It prints the address, opens the browser (`--no-browser` only prints it) and serves until the tab is closed. The page is `src/tilepane/editor/editor.html`; it can also be opened directly as a file.
- Server mode is decided by the page itself: the server injects `{"server": true, "token": ...}` into the page, instead of the page probing `/api/monitors`.
- The token is in the page URL (`?t=`) and in an `X-Tilepane-Token` header on every request; `Host` must be `127.0.0.1:PORT` or `localhost:PORT`; `Origin` and `Sec-Fetch-Site`, when sent, must be this server; POST bodies must be JSON (at most 2 MB). The page is sent with a strict Content-Security-Policy, `no-referrer` and `frame-ancestors 'none'`. The server stops 4 s after the tab says goodbye (`pagehide`), after 150 s without a heartbeat (browsers slow timers in hidden tabs to about one a minute), or after 30 minutes without requests.
- Saving is validated again by the Python loader; errors come back next to the problems the page found itself. The file is written atomically and keeps its permissions.
- "Open on screen" saves first, then runs `tilepane --json FILE --layout NAME --monitor N` on the saved file; "Close on screen" runs the matching `--close`. The layout name and the monitor number are checked against the saved file and the detected monitors.
- Turning a two-pane split into N panes ("Add pane next to it") converts a percentage into shares (`50%` becomes `1frac, 1frac`, so a third pane gets an equal share); a pixel size stays fixed. Removing panes back to two converts back to `a`/`b`/`at`.
- Dragging a line keeps the unit and direction of the value (`60%`, `-300px`, ...); percentages are written with one decimal, pixels as whole numbers. The line snaps by itself onto the nearest parallel line elsewhere on the monitor when it comes within 10 screen px, shown with a guide and a pixel readout, and a tooltip at the cursor says "Hold Alt to turn snapping off" ("Lined up with another line" is added while it is snapped, "Snapping is off" while Alt is held); holding Alt turns the snapping off. a snapped value is written with three decimals (four for `frac`), so both lines end on the same pixel at the current size and the panes on either side can then be merged. Shift-drag of a line (also when Shift is pressed in the middle of the drag): the old line stays and nothing is changed until the mouse button goes up; a preview strip and a tooltip show the new empty pane between the old line and the dragged one. On release with Shift held the split becomes an N-way split (if it was a two-part one) with the new empty pane between the two lines: the pane on the side the line was dragged to gives the room, the other pane keeps its place; the sizes keep their units (shares of `frac`, pixels or percent; the new pane gets the unit of the pane that gave it room, pixels when that one is flexible). If the new pane, or the pane that gives room, would be smaller than the margin plus 30 px, or Shift is let go before the button, nothing new is made (let go: the line moves as usual); Esc cancels the whole drag. One undo step. Lines stop 10 px short of their split's edges and outer splits are drawn on top, so a nested split's line never hides the outer one.
- Command lines (added after step 8): the layout panel starts with a "Command line" section, and the header's "Commands" button opens the same list in a dialog: open, `--toggle`, `--close`, `--dry-run` and `--edit` for the current layout and the monitor chosen in the list, each with a Copy button. The monitor is written as its number or its connector name (a switch; the choice is remembered in the browser). The path is the file on disk, with the home directory shortened to `~` and shell quoting where needed; `--layout` is added only when the file has several layouts. Opened as a plain file the page knows only the file name and says so; a size preset is not a real monitor, so `--monitor` is left out then.
- JSON copy and paste (added after step 8): the header's "JSON…" button opens a dialog with a text box holding the current layout as JSON (with several layouts a switch shows the whole file instead). Copy exports it. Pasted text is read as a whole file (has `layouts`), one layout (has `split`) or a bare split/pane tree (wrapped as a layout). Syntax errors are shown in the dialog and nothing changes. *Replace this layout* keeps the old name when the pasted one has none; *Add as new layout* adds every pasted layout with a unique name and drops file-level keys (`defaults`, `monitors`, ...); *Replace whole file* swaps the document. Each import is one undo step and marks the file as changed.
- Clicking outside the monitor picture (or on it between panes, or Escape) clears the selection.
- Swapping panes: dragging a pane onto another swaps their contents; the rectangles stay. While dragging, a copy of the pane (at most 240×150) follows the pointer; over another pane the copy takes that pane's place, showing where the contents will land. A line under the preview reminds that a click outside the monitor unselects and shows the command lines. A moving pane takes along every inheriting value it had (from the built-in values, file defaults, layout and splits above), so it behaves the same in its new place; values that are not needed there are then removed. A setting with no built-in value (`cwd`, `env`, `profile`, `font_size`) that the pane did not have cannot be written as "none", so under a split that sets one, the moved pane gets it.
- Splitting a pane moves its inheriting settings (`cwd`, `shell`, `terminal`, `on_exit`, ...) to the new split, so both halves get them; `run`, `title`, `id` and the other per-pane keys stay with the first half.
- Shared settings are moved up after every change: for each inheriting key except `margin` and `env`, the editor rewrites the layout so each value sits on the highest node (up to the layout itself) where it is the most common one among the window panes below, and is removed where it equals what the node inherits. No window gets a different value. Empty panes are not counted; the file defaults are never changed. `margin` and `env` are only tidied: a copy equal to the inherited value is removed. A file is not rewritten this way until it is first changed in the editor.
- The preview monitor can be resized by dragging its edges and corners: the size is shown in pixels while dragging and under the picture, rounded to 10 px (Alt gives single pixels, Shift keeps the shape), at least 320×200. It becomes "Custom size" in the monitor list, is remembered in the browser and does not change the file; "Reset size" returns to the chosen monitor. Next to the size, the layout's margin can be set with − / + or typed.
- Cut line (asked for by the owner): "✂ Cut screen ─" / "✂ Cut screen │" in the header (keys H and V) show a dashed line across the whole monitor that follows the mouse, snaps to existing boundaries within 8 screen px (Alt turns snapping off), shows its position in pixels and marks the panes it would cut. A click cuts every pane the line goes through; a pane whose piece would be smaller than the margin plus 30 px is skipped and marked. Each cut pane becomes a split whose first piece (top or left) keeps the pane's contents and whose second piece is empty. The new split point is written the way the pane itself was cut: the same unit and direction as the split it came from (`%`, `-%`, `px`, `-px`; a size in an N-way split gives `%` or `px`); a pane that was never cut gets `%`. Percentages get three decimals so all pieces end on the same pixel at the current size. Shift-click keeps cutting; Esc stops.
- Text typed into a field (a command, a title, a number) is committed when the field loses focus. Before any click, in the editor or on a button, and before undo, redo, save and "open on screen", the focused field is made to lose focus first, so that text is never lost when the click goes to a pane, the monitor or a line without moving the focus (Firefox), and the render the commit asks for waits until the click is over, so that the button or pane under the pointer still gets its click.
- Shift-drag from the edge of the work area (asked for by the owner): within 12 screen px inside the edge of the work area (the margin and the first pixels of the pane; marked while Shift is held; the monitor-size handles keep their own place at the very edge and Shift keeps the shape there) a Shift-drag makes a new empty pane between that edge and the line that is dropped. Only the one pane that touches the edge at the grabbed place gets it: it is replaced by a split with the empty pane first (left or top edge) or last (right or bottom edge) and the old pane as the other part, with a percentage `at` of three decimals; the other panes at that edge are not moved. Too narrow (or leaving too little to the pane) nothing is made. Snaps and Esc work as for lines.
- Cut pane (asked for by the owner, it replaced the old "Split" buttons of a selected pane): "✂ Cut pane ─" / "✂ Cut pane │" in the pane's panel halve the selected pane at once: a horizontal line gives a top and a bottom piece (written as `rows`, `at` 50 %), a vertical line a left and a right piece (`columns`, 50 %). The first piece keeps the contents and the new second piece is selected. With nothing selected the same two buttons are in the layout panel: while the screen is one single (empty) pane, as in a fresh editor, that pane is the first rectangle and is cut in half; with several panes they are disabled until a pane is selected. The buttons carry the direction of the line, not the wording "horizontal split", which means side by side in other tools. To choose the place of a cut with the mouse, use Cut screen (above); an earlier version of Cut pane followed the mouse like Cut screen and was changed to this on the owner's request.
- Merging panes (asked for by the owner): two panes can be merged when together they form a rectangle. With a pane selected, arrow buttons on its edges (and "Merge with left / right / above / below" in the panel) merge it with that neighbour; a selected line plus Delete merges the two panes on its sides. An empty pane never wins: merging with one happens at once and the pane with contents fills both places. When both have contents, a confirmation is asked (the selected pane stays), or, for Delete on a line, which side stays. A line with more than one pane on a side is not removed; the editor explains why. Panes from the same split are merged by removing the split (an N-way split adds their sizes); panes from different branches are merged by rebuilding the tree from the rectangles, with every pane taking along its inherited settings. New split points use the unit of the cuts involved; when those mix % and px, the editor asks which to use.
- Not done yet: the cell snap preview, and `--watch` (step 9).

## 6. Extra ideas (prioritize later)

- Layout inheritance/templates (`"extends": "3"`, reusable `templates`).
- GNOME shortcut and autostart examples in the README; `tilepane --install-autostart`.
- Borderless, always-on-top, sticky (on all workspaces) options: `above`, `sticky`, `workspace`, `skip_taskbar`, `below`.
- A per-pane `workspace` (panes of one layout on different workspaces).
- `tilepane --snapshot`: save the current window arrangement as a layout.
- Shell completion for layout and monitor names.
- `--watch`: when the JSON file is saved (or the editor saves it), the layout is updated on screen immediately.
- Per-pane color or title, to tell meters apart at a glance.
- `--dry-run --png layout.png` and `--dry-run --ascii`: draw the layout as an image or as boxes in the terminal.
- `grid` node with CSS-style areas, for layouts a tree cannot express.
- More ideas (built-in meters, `repeat`, `--daemon`, `--zoom`, ...) are listed in `docs/SPEC-REVIEW.md`.

### Open work and proposals (2026-10-10, after step 8)

Not yet built from this specification: `--watch` and the log file `~/.local/state/tilepane/tilepane.log` (step 9, with the final README/examples pass); Wayland backends; kitty and alacritty adapters; `mode: cycle` and `parallel`; `profile` and `font_size`; monitor hotplug; `above`/`sticky`/`skip_taskbar`; the editor's cell snap preview; the xdotool/wmctrl fallback.

New proposals, most practical first:

- `tilepane --install-autostart FILE`: a `.desktop` autostart entry that opens the layout at login (with `--wait-monitors`). `--install-shortcut`: a desktop keybinding, for example Super+M running `--toggle`.
- `--dry-run --ascii`: the layout drawn as boxes in the terminal, a quick check without a browser.
- `tilepane --snapshot`: record the tilepane windows (or any windows) on screen as a new layout: arrange by hand, then save.
- Failure notice: a desktop notification and a title marker when a pane's command ends with an error.
- Per-pane colour or background, to tell meters apart at a glance.
- Built-in meters (CPU, memory, network, disk, clock) in pure Python with coloured sparklines, so the demo and dashboards need nothing installed.
- Variants by monitor shape or count in one file (portrait versus landscape, laptop alone versus docked), chosen automatically.
- `--zoom PANE`: one pane fills the monitor and back, like tmux zoom.
- A gallery of example layouts in `examples/` (meters, logs, development, server watch) with previews.

Recommended order: step 9 (`--watch` and the log file), then `--install-autostart`/`--install-shortcut`, then `--dry-run --ascii`.

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
- The editor knows whether it was served by `tilepane --edit` from a small boot block the server fills in (see "As built" in section 5), and enables the extra features only then.
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

## 16. Analysing the screen (`--analyze`)

The opposite of opening a layout, asked for by the owner on 2026-10-18: `tilepane --analyze [FILE] [--monitor SPEC] [--workspace current|N|all] [--terminals-only] [--dry-run] [--yes] [--edit]` writes the layout that the open windows of a monitor make.

- **Targets:** the monitor of the active window, else of the pointer, unless `--monitor` (also a list or `all`); the workspace is the current one unless `--workspace` says another number or `all`. A file with several results holds one layout for each (names `analyzed-workspace-N-monitor-M`); a layout for an explicit workspace gets `workspace: N`. The default file is `analyzed-layout.json` in the current directory; an existing file is kept unless `--yes` (`--dry-run` prints the file to the standard output and the report to the standard error). With `--edit` the editor opens on the file when it is written.
- **Windows:** `deskmap.backends.Backend.open_windows()` lists them bottom to top with their visible rectangle (frame included) in the coordinates of their own workspace. Used are the windows of type normal that are not minimized, whose centre is in the monitor, on the workspace (a window on every workspace belongs to the current one). `--terminals-only` keeps the windows whose class is a known terminal.
- **Panes:** a terminal gets what `processes.terminal_pane` finds under its process in `/proc`: the settings in the command line of tilepane's runner (`commands`, `cwd`, `title`, `on_exit`), else the deepest process that is not a shell, as `run`, with its directory as `cwd`. A terminal whose process is shared by several windows, or that runs only a shell, becomes `{ "empty": false }`. Any other window becomes `{ "empty": false, "title": "<class>: <title, 40 characters>" }`.
- **Tree (`analyze.derive`):** the windows are widened by half the margin to cells; the area is reduced by `outer_margin` first. Then cuts are made recursively by straight lines across the region: first a cut that crosses no window (in the middle of a free strip, or at the edge of a window when a free strip wider than 12 px is left, which makes an empty pane), then, if every cut crosses windows, the one that takes the least area from them, between the centres of the windows. A window belongs to the side of its centre and is cut to it. Overlaps of up to 6 px and gaps of up to 12 px are noise (terminals sit on character cells). Windows with the same centre are put in equal strips, the topmost first. `margin` is the median gap between neighbours (0 when windows overlap), `outer_margin` is set only when the outermost windows are not at the distance that the margin gives. The split points are written as percent with three decimals, or as pixels when that is closer to the windows.
- **Report:** the number of windows and panes, the margin and the largest difference in pixels between a window and the pane it got; a layout of windows that touch exactly gives 0.

## Bare file names (added 2026-10-18)

A layout file given without a directory part (`tilepane metering.json`, `--json metering.json`, `--edit metering.json`) is taken from the current directory when it exists there; otherwise from the config directory (`$XDG_CONFIG_HOME/tilepane`, by default `~/.config/tilepane`) when it exists there; otherwise it stays as typed and the "file not found" message names both places. A name with a directory part (`./x.json`, `sub/x.json`, `/abs/x.json`, `~/x.json`) is never searched for. `--edit` of a name found nowhere creates the file in the current directory, as before. The same lookup applies to `--analyze FILE`, so a file that exists only in the config directory is the one replaced. The `.json` ending stays required for a name to count as a file.
