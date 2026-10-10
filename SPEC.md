# tilepane: specification

A tool that opens terminal windows at precisely defined positions on the screen (per monitor) and starts the desired commands in them (htop, watch, nvidia-smi, and so on). Layouts are defined in JSON files and can be edited with the mouse in a browser.

Repo: `tilepane`, default branch `master`. Language: Python 3.

## 1. Goal and usage

```
tilepane --json meters.json                    # open the layout described by a JSON file (monitor 0)
tilepane --json meters.json --monitor 2        # same, on monitor 2
tilepane --json meters.json --layout three     # a specific layout, if the file contains several
tilepane --json a.json --monitor 0 --json b.json --monitor 1   # several tasks (see section 14)
tilepane meters.json                           # short form: same as --json meters.json
tilepane 3                                     # layout named "3" from the default config
tilepane --list                                # list layouts
tilepane --close 3                             # close the windows of layout 3
tilepane --toggle 3                            # open if closed, close if open
tilepane --edit                                # start the browser editor (localhost)
tilepane --doctor                              # print environment info (session type, monitors, terminal)
tilepane --monitors                            # list monitors with their numbers, names, sizes and positions
tilepane --dry-run 3                           # print the computed rectangles without opening anything
tilepane --demo                                # random split with fun commands (see section 10)
```

Argument interpretation: if an argument is an existing file or ends with `.json`, it is a configuration file. Otherwise it is a layout name from the default configuration. A file may contain either a single layout (top-level `name`/`split`) or several (`layouts`).

Layout names can be numbers or words ("3", "cpu-dash").

## 2. Configuration (JSON)

Default location, when `--json` is not given: `~/.config/tilepane/config.json`. When `--json` is given, that file is used instead. (`--config` is an alias of `--json`.) All behavior is configurable here. A layout is a **tree**: a node is either a split (`dir`, `at`, `a`, `b`) or a leaf (`run` and so on).

```json
{
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
        "dir": "v",
        "at": "60%",
        "a": { "run": "htop", "cwd": "~", "title": "htop" },
        "b": {
          "dir": "h",
          "at": "300px",
          "a": { "run": "watch -n1 sensors" },
          "b": { "run": "nvidia-smi -l 1", "on_exit": "restart" }
        }
      }
    }
  ]
}
```

A single-layout file may be flat: `name`, `margin`, `split` at the top level, without a `layouts` list. If a file contains exactly one layout, it is used by default. If it contains several, the layout is chosen by name (`--layout name`).

### Split node
- `dir`: `"v"` = vertical split (a on the left, b on the right), `"h"` = horizontal split (a on top, b at the bottom). Also accept `"vertical"` / `"horizontal"`. Make sure the final naming is intuitive.
- `at`: the split point, measured from the size of the **area being split** (before margins):
  - `"60%"`: percentage of the area width/height from the left/top
  - `"300px"`: pixels from the left/top
  - `"-300px"` / `"-40%"`: measured from the right/bottom
- `a`, `b`: child nodes (a split or a leaf), arbitrary depth.
- An optional `margin` per node overrides the area's margin.

### N-way split
In addition to the binary tree, allow a `children` list and `sizes` (in the style of CSS grid), so that for example three columns are easy to write:

```json
{ "dir": "v", "sizes": ["1frac", "2frac", "300px"], "children": [ {...}, {...}, {...} ] }
```
Internally convert to a binary tree or compute directly. `frac` divides the remaining space proportionally.

### Leaf
- `run`: a command (string) or a list of commands. Executed through the shell. A list is executed **sequentially in the same terminal** (see section 10).
- `cwd`: working directory (supports `~`).
- `title`: window title (also used to identify the window).
- `terminal`: overrides the terminal for this pane.
- `profile` / `font_size`: optional terminal-specific settings.
- `snap`: `"cell"` | `"pixel"`.
- `on_exit`: `"keep"` | `"close"` | `"restart"` (+ optional `restart_delay` in seconds).
- `env`: extra environment variables.

## 3. Geometry (core logic)

A pure function with no windowing dependencies, easy to unit test:

`compute(layout, monitor_rect) -> list[LeafRect]`

Rules:
1. Start with the whole work area of the monitor. Panels / top bars are subtracted if the system reports the work area.
2. **The margin lies inside every rectangle on all four sides, and its value is the total gap, so every rectangle has `margin/2` on each side.** Example, margin 8: the gap between windows is 4 + 4 = 8, and at the outer edge of the screen it is 4.
3. A split is always made from the rectangle **outside** the margin. The margin is applied only at the leaf level: window = leaf rectangle minus margin/2 on every side.
4. `outer_margin` (optional): if set, the margin at the outer edge of the screen is this value (the total value for the outer edge, not halved), while the inner gaps stay according to `margin`. Implementation: subtract outer_margin from the whole area first, then use the inner margins; leaves at the outer edge must then not get an extra half margin. Verify with unit tests that the edge is not counted twice.
5. A pixel value `at: "300px"` means the size of the area before the margin. An additional option `at_basis: "outer" | "visible"` (default `outer`) can switch the interpretation so that the visible window is exactly the given size.
6. **Rounding:** all calculations use floats or integers so that the edges of adjacent panes land on the same pixel (no gaps and no overlaps).

### Snap
- `"cell"` (**default**): the inner size of the window is rounded down to whole character cells. The position of the window (top-left corner) stays at the computed point; a gap of at most one cell remains on the right/bottom. The cell size is obtained from the terminal/font or estimated by measuring after the first window opens.
- `"pixel"`: the size is forced to exactly the computed pixel size when the terminal and the window manager allow it (kitty, alacritty and so on). The background fill takes care of the empty edge.

## 4. Window placement (backends)

Chosen at runtime (`$XDG_SESSION_TYPE`, `$XDG_CURRENT_DESKTOP`), and the backend must be swappable behind an interface:

- **X11:** `xdotool` / `wmctrl` or `python-xlib`. The window is identified by a unique WM_CLASS or title (for example `tilepane:<layout>:<leaf-id>`). Remove the maximized state if needed, and take the frame size into account (frame extents) when computing the placement.
- **Wayland (GNOME/Mutter):** windows cannot be positioned from the outside. Options, to be investigated with `--doctor` and chosen together with the user: (a) a small GNOME Shell extension (JS) that Python calls over D-Bus, (b) an X11 session, (c) the terminal's own Wayland support for placement, if available.
- **Mint/Cinnamon:** X11, same path as above.

Terminal (`"auto"`): try in order kitty, alacritty, gnome-terminal, xterm. One "adapter" per terminal: command line options for title, class, command, font and `on_exit` behavior (for example a shell wrapper that runs the command and then waits/restarts).

State management: the program marks the windows it opens (title/class + a state file in `~/.local/state/tilepane/`), so that `--close`, `--toggle` and "do not open duplicates" work. If a layout is already open, move/rearrange it instead of opening new windows.

## 5. Browser editor (`tilepane --edit`)

- Python stdlib HTTP server (`127.0.0.1` only), static HTML/JS front end, no heavy build step.
- View: a screen drawn in proportion to the monitor. Click a pane, then "split horizontally/vertically". Dragging a split line with the mouse changes the `at` value; the value can be switched between % and px, and the direction (from left/top or from right/bottom) can be chosen.
- Pane side panel: run, cwd, title, on_exit, snap, margin.
- Margins are visible in the preview at the correct scale.
- Layout and monitor selection, new/copy/delete layout.
- Saving writes the same JSON (preserve other keys, keep the formatting tidy). Validate against the schema before saving.
- A "Test here" button: actually opens the layout on the selected monitor.

## 6. Extra ideas (prioritize later)

- Layout inheritance/templates (`"extends": "3"`, reusable `templates`).
- GNOME shortcut and autostart examples in the README.
- Borderless, always-on-top, sticky (on all workspaces) options: `decorations`, `above`, `sticky`, `workspace`.
- Per-workspace opening (`"workspace": 2`).
- `tilepane --snapshot`: save the current window arrangement as a layout.
- Command health check and a delay in `restart` mode.
- Shell completion for layout and monitor names.
- `--watch`: when the JSON file is saved (or the editor saves it), the layout is updated on screen immediately.
- A `$schema` JSON schema file, so that editors such as VS Code can autocomplete and validate the configuration.
- Per-pane color or title, to tell meters apart at a glance.
- `--dry-run --png layout.png`: draw the layout as an image for README examples.
- Groups: `tilepane 3 5` opens two layouts at once, and `--close all` closes everything.

## 7. Implementation order

1. `--doctor`: find out the user's environment (session type, desktop, versions, monitors, available terminals). **Do this yourself by running the commands; do not ask the user.** Report the results and propose a backend.
2. Geometry core + unit tests (margin, outer_margin, negative `at`, percentages, rounding, deep trees, `frac` sizes).
3. Config loading and validation (JSON schema), `--dry-run`.
4. One backend all the way through (the one that fits the user's environment): one terminal, one window at the right place, then the whole layout.
5. Monitor support, `--monitors`, and multi-task command lines (section 14).
6. `on_exit`, `snap`, state management, `--close` / `--toggle`.
7. `--demo` (section 10).
8. Browser editor (section 13).
9. README, installation (pipx / `pip install -e .`), example configuration.

## 8. Open questions (to be resolved during the work)

- Wayland or X11 (resolved by `--doctor`), and in the Wayland case a GNOME extension or an X11 session.
- Which terminal to use (kitty/alacritty vs. gnome-terminal).
- The number of monitors and how they are named.
- HiDPI scaling and how pixels are interpreted (default: logical, scaled pixels).
- Whether the meters should be always-on-top / sticky.
- Whether the project is shared with others (affects packaging and documentation).

## 9. Decisions so far

- Name: **tilepane**.
- Margin: a total gap, half on each side; optional `outer_margin`.
- `at`: percentage or pixels, from the left/top or from the right/bottom (negative).
- `snap`: default `"cell"`, alternative `"pixel"`.
- `on_exit`: default `"keep"`, alternatives `"close"`, `"restart"`.
- Everything is configurable in JSON.

## 10. Multiple commands per pane and demo mode

### Multiple commands in a leaf
Every leaf (rectangle) gets its own terminal window. The leaf's `run` can be a string or a list. A list means n commands, executed **one after another in the same terminal** (`mode: "sequence"` is the default). For example `cd`, `source venv`, then `htop`: the next command starts when the previous one ends.

Later optional extras, selected with the `mode` field:
- `"cycle"`: the commands rotate every `interval` seconds in the same window (for example 10 s htop → 10 s iotop → 10 s nethogs).
- `"parallel"`: run side by side in the same window (needs a tmux/zellij-style solution; optional and a later phase).

```json
{ "run": ["htop", "iotop", "nethogs"], "mode": "cycle", "interval": 10 }
```

### Demo mode (`--demo`)
- `tilepane --demo` randomly splits the monitor into a few rectangles and starts a fun command in each.
- The number of panes defaults to a random pick of 3, 4, 5 or 6. The demo **does not close by itself**: the terminal windows stay open even after the command ends (`on_exit: keep`). `--for 30s` is optional.
- Options: `--demo N` (number of panes), `--seed S` (reproducible result), `--monitor`, `--for 30s`, `--save demo.json` (saves the resulting layout as JSON that can be edited in the editor).
- Randomness of the split: direction, `at` (20–80 %, sometimes in pixels), depth, margin (for example 4–16).
- Command pool; pick only commands that are found (`which`), and for missing ones use plain shell loops:
  `top`, `htop`, `watch -n1 date`, `watch -n2 'ls -la'`, `vmstat 1`, `watch -n1 'cat /proc/loadavg'`, `watch -n5 df -h`, `journalctl -f`, `dmesg -w`, `ping 1.1.1.1`, `watch -t -n1 'date +%T | figlet'`, `cmatrix`, `sl`, `fortune | cowsay`, `cal`, `sensors`, `nvidia-smi -l 1`.
- It must not require installed packages, and every command has a fallback command.

## 11. Layout files

- Every layout has a `name`. If a JSON file contains only one layout, it is used by default. If it contains several, the layout is chosen by name (`--layout name`, or as the second argument).
- A single-layout file may be flat: `name`, `margin`, `split` at the top level without a `layouts` list. In a multi-layout file, `layouts` is a list of objects that have a `name`.
- Command line: `tilepane --json path.json [--layout name] [--monitor N]`. The positional form `tilepane path.json` also works. `--monitor` defaults to 0.

## 12. Monitor detection and numbering

- In Linux, monitors have no persistent number. `xrandr --listmonitors` gives indices (0:, 1:), but the order depends on how the X server enumerates them and can change on reboot or when a cable is unplugged. The persistent identifier is the connector name (`HDMI-1`, `DP-2`, `eDP-1`).
- tilepane defines its own numbering: **monitors are numbered by position, from left to right and from top to bottom** (primarily by x, secondarily by y). `0` is the leftmost monitor. This is decided; numbering is not primary-based. The default monitor is 0.
- `--monitor` accepts: a number, a connector name, a config alias (the `monitors` block), `primary`, or `all`.
- `tilepane --monitors` prints the monitors found with their numbers, names, resolutions and positions, so the user can see which number is which.

## 13. Graphical editor: architecture

- **A single self-contained HTML file** (HTML + CSS + vanilla JS, no build step, no external dependencies) that works in two ways with the same code:
  1. **Standalone:** opened in the browser directly as a file (`file://`). A JSON file is opened with a file picker and saved as a download (in Chromium the File System Access API can save directly to the file when supported).
  2. **`tilepane --edit`:** a Python stdlib server (`127.0.0.1`) serves the same HTML and adds: saving directly to the file, the real monitors (size, position) in the preview, an "Open on screen" button and `--watch` updates.
- The editor detects at runtime whether the server is available (`fetch('/api/monitors')`) and enables the extra features only then.
- Creating a new layout from scratch, opening a JSON file, validation, and opening the result of `--demo --save` in the editor.

## 14. Multiple tasks in one command line

A command line consists of **tasks**. A task = one layout file + its target monitor(s). All tasks are opened in the same run.

```
tilepane --json cpu.json --monitor 0 \
         --json network.json --monitor 1 \
         --json disk.json --monitor 2 \
         --json logs.json --monitor 3 \
         --json gpu.json
```

Rules:
- `--json` starts a new task. The `--monitor` and `--layout` that follow belong to that task until the next `--json` begins. Parse in order (not as separate lists).
- `--monitor` missing → monitor 0.
- `--monitor` accepts a single value or a comma-separated list (`--monitor 0,1,2`), in which case the same layout is opened on each. A value is a number, a connector name, an alias or `all`.
- The same file may appear in several tasks on different monitors.
- In a multi-layout file, choose the layout with `--layout name`. If the file contains one layout, use it.
- Geometry is computed per task from the target monitor's own size and work area.
- **Overlap:** if two tasks land on the same monitor, both are opened on top of each other. No warning, no error, no separate switch.
- An invalid task (missing file, unknown monitor, invalid JSON) is reported clearly. The other tasks are opened anyway, and a summary of successes and failures is printed at the end. The exit code is non-zero if anything failed.
- `--close` and `--toggle` work with the same task structure.
