# Configuration reference

<!-- Generated from src/tilepane/tilepane.schema.json by `python -m tilepane.docgen`. Do not edit by hand. -->

Every key tilepane understands, by level. The JSON schema is the source of truth; `tilepane --explain KEY` prints the same description in a terminal, and editors such as VS Code show it as a tooltip when the file has a `$schema` key. Behavior is described in [SPEC.md](../SPEC.md).

## How a file is organised

A file holds one or more **layouts**. A layout is a tree: a **split node** divides its area between children, a **leaf** is one rectangle (a pane) that normally gets one terminal window.

- A file with a `layouts` list holds several layouts; choose one with `--layout NAME` or by naming it after the file.
- A file with a top-level `split` is a single layout. The layout keys (`name`, `margin`, `split`, ...) then go at the top level, and `name` defaults to the file name.
- A file cannot have both `layouts` and a top-level `split`.

```json
{
  "$schema": "https://raw.githubusercontent.com/anttiraisala/tilepane/master/src/tilepane/tilepane.schema.json",
  "name": "cpu-dash",
  "margin": 8,
  "split": {
    "dir": "columns", "at": "60%",
    "a": { "run": "htop", "title": "htop" },
    "b": { "run": "watch -n1 sensors", "when": "command -v sensors" }
  }
}
```

## Inheritance and precedence

Keys marked **Inherits** apply down the tree. The effective value for a leaf is the first one found in this order: the leaf, its ancestor split nodes (nearest first), the layout, the file's `defaults`, the built-in value. `env` is merged key by key instead of replaced. `at_basis` inherits through split nodes only. `outer_margin` and `area` are set on the layout or in `defaults`. Keys that are not marked never inherit.

## Size values

`at` and the entries of `sizes` use these forms:

- `"60%"`: a percentage of the area being split (before margins).
- `"300px"` or `300`: pixels. A bare number means pixels.
- `"2frac"`: a share of the space left after the fixed sizes, divided in proportion (`sizes` only).
- A negative `at` (`"-300px"`, `"-40%"`) is measured from the right or bottom.

## Validation

A file is validated when it is loaded; all problems are reported together with their key path (for example `layouts[0].split.b.run`). An unknown key is a warning with a suggestion; `--strict` makes it an error. A key on the wrong level (for example `run` on a split node) is an error.

## File

Top level of the file. A tilepane configuration file: one or more layouts that open terminal windows at exact positions. Keys marked as inheriting apply down the tree: leaf, then ancestor split nodes, then the layout, then the file's defaults, then the built-in value.

| Key | Type | Default | Inherits | Description |
|---|---|---|---|---|
| `$schema` | string | none | no | URL of this schema, so that editors such as VS Code can complete and validate the file. Ignored by tilepane. |
| `version` | `1` | none | no | Version of the configuration format. Currently 1. A file with a higher version is rejected so that a newer file is never half understood. Examples: `1`. |
| `description` | string | none | no | Free text about the file, layout, split node or leaf. Ignored by tilepane; JSON has no comments, so use this instead. |
| `defaults` | object | none | no | Values used when a layout, split node or leaf does not set its own. |
| `monitors` | object | none | no | Monitor aliases for --monitor. Each alias maps to a connector name such as "HDMI-1" (see tilepane --monitors) or to a monitor number. Examples: `{"left": "DP-1", "main": "HDMI-1", "side": 2}`. |
| `layouts` | list of layout | none | no | The layouts of a multi-layout file. Choose one with --layout NAME or by naming it after the file. A single-layout file may leave this out and put name, split and the other layout keys at the top level. |

## Defaults

The `defaults` block. Values here apply when nothing nearer sets them.

| Key | Type | Default | Inherits | Description |
|---|---|---|---|---|
| `outer_margin` | number or null | `null` | no | Gap in pixels between the windows and the edge of the screen (or work area). The total value for the outer edge, not halved. null or absent means the edge gap is half of margin. Set on the layout or in defaults. Examples: `16`. |
| `area` | `"work"`, `"full"` | `"work"` | no | Which part of the monitor is divided: "work" excludes panels and docks, "full" uses the whole monitor. Set on the layout or in defaults. |
| `workspace` | whole number | none | no | The workspace (virtual desktop) the layout opens on, 1 for the first one. Without it the layout opens on the current workspace. --workspace on the command line overrides it. A number larger than the number of workspaces opens on the current one, with a warning. Set on the layout or in defaults. Examples: `4`. |
| `at_basis` | `"outer"`, `"visible"` | `"outer"` | through split nodes | How a pixel size in at or sizes is read: "outer" is the pane rectangle before margins, "visible" makes the visible window exactly that size. Inherits through split nodes. Uses the margin of the split node it is set on. |
| `terminal` | string or object | `"auto"` | yes | The terminal that runs the pane: "auto" (kitty, alacritty, gnome-terminal, xterm, first found), a terminal name, or an object {"cmd": [...]} with a command template that contains the {command} placeholder (and optionally {title}). Examples: `"gnome-terminal"`, `{"cmd": ["foot", "--title", "{title}", "--", "{command}"]}`. |
| `shell` | string | `"auto"` | yes | The shell that runs the pane's commands and the interactive prompt afterwards: "auto" (your login shell, $SHELL), a name such as "bash", "zsh" or "fish", or a full path. A pane with only shell set opens that shell. Examples: `"bash"`, `"zsh"`, `"/usr/bin/fish"`. |
| `profile` | string | none | yes | Terminal-specific profile name (for example a gnome-terminal profile). A terminal that cannot use it produces a warning. |
| `font_size` | number | none | yes | Font size in points, for terminals that can set it from the command line. A terminal that cannot honor it produces a warning. Examples: `11`. |
| `snap` | `"cell"`, `"pixel"` | `"cell"` | yes | "cell" rounds the window size down to whole character cells (a gap of up to one cell may remain on the right and bottom). "pixel" forces the exact pixel size when the terminal and window manager allow it. |
| `on_exit` | `"keep"`, `"close"`, `"restart"` | `"keep"` | yes | What happens when the pane's command ends: "keep" prints the exit status and leaves an interactive shell, "close" closes the window, "restart" runs the command again after restart_delay seconds. |
| `restart_delay` | number | `1` | yes | Seconds to wait before restarting when on_exit is "restart". Also the minimum time between restarts, so a failing command does not loop at full speed. |
| `max_restarts` | whole number | `0` | yes | Maximum number of restarts when on_exit is "restart". 0 means unlimited. After the limit the window behaves as "keep". |
| `stop_on_error` | true or false | `false` | yes | In a list of commands (mode "sequence"), stop at the first command that fails instead of continuing with the next. |
| `decorations` | true or false | `true` | yes | false removes the window border and title bar when the terminal and window manager allow it. |
| `cwd` | string | none | yes | Working directory of the command. ~ and $VAR are expanded. A directory that does not exist is an error shown in the pane. Examples: `"~"`, `"~/projects/app"`. |
| `env` | object | none | yes | Extra environment variables for the command, as an object with string values. ~ and $VAR are expanded in the values. Merged key by key down the tree instead of replaced. Examples: `{"LANG": "C"}`. |
| `margin` | number | `8` | yes | Total gap in pixels between two neighbouring windows; each window gets half of it on every side (an odd value is split floor and ceiling so the gap is exact). On a split node it applies to everything below it. Examples: `8`. |

## Layout

One layout (an entry of `layouts`, or the top level of a single-layout file).

| Key | Type | Default | Inherits | Description |
|---|---|---|---|---|
| `name` | string or whole number | none | no | Name of the layout, used to select it (tilepane 3, --layout cpu-dash). A string or a whole number. Unique within the file. A flat single-layout file defaults to the file name without extension. Examples: `"3"`, `"cpu-dash"`. |
| `description` | string | none | no | Free text about the file, layout, split node or leaf. Ignored by tilepane; JSON has no comments, so use this instead. |
| `split` | node (split or leaf) | none | no | The root node of the layout tree: a split node, or a single leaf for a layout with one pane. |
| `outer_margin` | number or null | `null` | no | Gap in pixels between the windows and the edge of the screen (or work area). The total value for the outer edge, not halved. null or absent means the edge gap is half of margin. Set on the layout or in defaults. Examples: `16`. |
| `area` | `"work"`, `"full"` | `"work"` | no | Which part of the monitor is divided: "work" excludes panels and docks, "full" uses the whole monitor. Set on the layout or in defaults. |
| `workspace` | whole number | none | no | The workspace (virtual desktop) the layout opens on, 1 for the first one. Without it the layout opens on the current workspace. --workspace on the command line overrides it. A number larger than the number of workspaces opens on the current one, with a warning. Set on the layout or in defaults. Examples: `4`. |
| `at_basis` | `"outer"`, `"visible"` | `"outer"` | through split nodes | How a pixel size in at or sizes is read: "outer" is the pane rectangle before margins, "visible" makes the visible window exactly that size. Inherits through split nodes. Uses the margin of the split node it is set on. |
| `terminal` | string or object | `"auto"` | yes | The terminal that runs the pane: "auto" (kitty, alacritty, gnome-terminal, xterm, first found), a terminal name, or an object {"cmd": [...]} with a command template that contains the {command} placeholder (and optionally {title}). Examples: `"gnome-terminal"`, `{"cmd": ["foot", "--title", "{title}", "--", "{command}"]}`. |
| `shell` | string | `"auto"` | yes | The shell that runs the pane's commands and the interactive prompt afterwards: "auto" (your login shell, $SHELL), a name such as "bash", "zsh" or "fish", or a full path. A pane with only shell set opens that shell. Examples: `"bash"`, `"zsh"`, `"/usr/bin/fish"`. |
| `profile` | string | none | yes | Terminal-specific profile name (for example a gnome-terminal profile). A terminal that cannot use it produces a warning. |
| `font_size` | number | none | yes | Font size in points, for terminals that can set it from the command line. A terminal that cannot honor it produces a warning. Examples: `11`. |
| `snap` | `"cell"`, `"pixel"` | `"cell"` | yes | "cell" rounds the window size down to whole character cells (a gap of up to one cell may remain on the right and bottom). "pixel" forces the exact pixel size when the terminal and window manager allow it. |
| `on_exit` | `"keep"`, `"close"`, `"restart"` | `"keep"` | yes | What happens when the pane's command ends: "keep" prints the exit status and leaves an interactive shell, "close" closes the window, "restart" runs the command again after restart_delay seconds. |
| `restart_delay` | number | `1` | yes | Seconds to wait before restarting when on_exit is "restart". Also the minimum time between restarts, so a failing command does not loop at full speed. |
| `max_restarts` | whole number | `0` | yes | Maximum number of restarts when on_exit is "restart". 0 means unlimited. After the limit the window behaves as "keep". |
| `stop_on_error` | true or false | `false` | yes | In a list of commands (mode "sequence"), stop at the first command that fails instead of continuing with the next. |
| `decorations` | true or false | `true` | yes | false removes the window border and title bar when the terminal and window manager allow it. |
| `cwd` | string | none | yes | Working directory of the command. ~ and $VAR are expanded. A directory that does not exist is an error shown in the pane. Examples: `"~"`, `"~/projects/app"`. |
| `env` | object | none | yes | Extra environment variables for the command, as an object with string values. ~ and $VAR are expanded in the values. Merged key by key down the tree instead of replaced. Examples: `{"LANG": "C"}`. |
| `margin` | number | `8` | yes | Total gap in pixels between two neighbouring windows; each window gets half of it on every side (an odd value is split floor and ceiling so the gap is exact). On a split node it applies to everything below it. Examples: `8`. |

## Split node

A split node: a node that has `dir`.

| Key | Type | Default | Inherits | Description |
|---|---|---|---|---|
| `dir` | `"columns"`, `"rows"`, `"v"`, `"vertical"`, `"h"`, `"horizontal"` | none | no | How a split arranges its children. "columns": side by side, a on the left. "rows": stacked, a on top. The aliases "v"/"vertical" mean columns and "h"/"horizontal" mean rows (v is a vertical divider line; tmux uses the opposite convention). |
| `at` | string or number | `"50%"` | no | Where a two-child split divides its area, measured from the area before margins: "60%", "300px" (a bare number means pixels), measured from the left or top. A negative value ("-300px", "-40%") is measured from the right or bottom. 0, 100% or more than the area is an error. Examples: `"60%"`, `"300px"`, `"-300px"`, `"-40%"`. |
| `a` | node (split or leaf) | none | no | First child of a two-child split: the left (columns) or top (rows) node. Use together with b and at. Leave it out (or write {}) to keep that part of the screen empty. |
| `b` | node (split or leaf) | none | no | Second child of a two-child split: the right (columns) or bottom (rows) node. Takes the space that at leaves over. Leave it out (or write {}) to keep that part of the screen empty. |
| `children` | list of node (split or leaf) | none | no | The children of an N-way split, instead of a, b and at. Sizes come from sizes; without it the children share the space equally. |
| `sizes` | list of string or number | none | no | Sizes of the children of an N-way split, one entry per child: "2frac" (a share of the space left over, divided proportionally), "300px" or "25%". If no entry is a frac, the last child takes the leftover. Examples: `["1frac", "2frac", "300px"]`. |
| `description` | string | none | no | Free text about the file, layout, split node or leaf. Ignored by tilepane; JSON has no comments, so use this instead. |
| `at_basis` | `"outer"`, `"visible"` | `"outer"` | through split nodes | How a pixel size in at or sizes is read: "outer" is the pane rectangle before margins, "visible" makes the visible window exactly that size. Inherits through split nodes. Uses the margin of the split node it is set on. |
| `terminal` | string or object | `"auto"` | yes | The terminal that runs the pane: "auto" (kitty, alacritty, gnome-terminal, xterm, first found), a terminal name, or an object {"cmd": [...]} with a command template that contains the {command} placeholder (and optionally {title}). Examples: `"gnome-terminal"`, `{"cmd": ["foot", "--title", "{title}", "--", "{command}"]}`. |
| `shell` | string | `"auto"` | yes | The shell that runs the pane's commands and the interactive prompt afterwards: "auto" (your login shell, $SHELL), a name such as "bash", "zsh" or "fish", or a full path. A pane with only shell set opens that shell. Examples: `"bash"`, `"zsh"`, `"/usr/bin/fish"`. |
| `profile` | string | none | yes | Terminal-specific profile name (for example a gnome-terminal profile). A terminal that cannot use it produces a warning. |
| `font_size` | number | none | yes | Font size in points, for terminals that can set it from the command line. A terminal that cannot honor it produces a warning. Examples: `11`. |
| `snap` | `"cell"`, `"pixel"` | `"cell"` | yes | "cell" rounds the window size down to whole character cells (a gap of up to one cell may remain on the right and bottom). "pixel" forces the exact pixel size when the terminal and window manager allow it. |
| `on_exit` | `"keep"`, `"close"`, `"restart"` | `"keep"` | yes | What happens when the pane's command ends: "keep" prints the exit status and leaves an interactive shell, "close" closes the window, "restart" runs the command again after restart_delay seconds. |
| `restart_delay` | number | `1` | yes | Seconds to wait before restarting when on_exit is "restart". Also the minimum time between restarts, so a failing command does not loop at full speed. |
| `max_restarts` | whole number | `0` | yes | Maximum number of restarts when on_exit is "restart". 0 means unlimited. After the limit the window behaves as "keep". |
| `stop_on_error` | true or false | `false` | yes | In a list of commands (mode "sequence"), stop at the first command that fails instead of continuing with the next. |
| `decorations` | true or false | `true` | yes | false removes the window border and title bar when the terminal and window manager allow it. |
| `cwd` | string | none | yes | Working directory of the command. ~ and $VAR are expanded. A directory that does not exist is an error shown in the pane. Examples: `"~"`, `"~/projects/app"`. |
| `env` | object | none | yes | Extra environment variables for the command, as an object with string values. ~ and $VAR are expanded in the values. Merged key by key down the tree instead of replaced. Examples: `{"LANG": "C"}`. |
| `margin` | number | `8` | yes | Total gap in pixels between two neighbouring windows; each window gets half of it on every side (an odd value is split floor and ceiling so the gap is exact). On a split node it applies to everything below it. Examples: `8`. |

## Leaf

A leaf: a node with none of the split keys.

| Key | Type | Default | Inherits | Description |
|---|---|---|---|---|
| `run` | string or list of string | none | no | The command, run through the pane's shell (see shell; by default your login shell) as <shell> -lc <command>. A list is run one command after another in the same terminal (see mode and stop_on_error). Without run, a pane that has any other setting (cwd, title, terminal, ...) opens an interactive shell; a pane with no settings stays empty. Examples: `"htop"`, `["cd ~/app", "source venv/bin/activate", "python main.py"]`. |
| `title` | string | none | no | Window title. Programs and shells may overwrite it, so tilepane does not use it to find its windows. Examples: `"htop"`. |
| `id` | string | none | no | Stable identifier of the pane, unique within the layout (letters, digits, _, - and .; not only digits and dots). Used to match windows to panes when a layout is already open. Without it the tree path (for example 1.0) is used, which changes when the tree is edited. Examples: `"cpu"`. |
| `mode` | `"sequence"`, `"cycle"`, `"parallel"` | `"sequence"` | no | How a list of commands runs: "sequence" one after another, "cycle" rotate every interval seconds in the same window, "parallel" side by side (planned). |
| `interval` | number | none | no | Seconds each command runs before the next one takes over. Required when mode is "cycle". Examples: `10`. |
| `when` | string | none | no | A shell command. If it exits non-zero, the pane is left out and its sibling takes the space, so one layout works on machines without, for example, a GPU. Run only when opening windows (or with --dry-run --eval-when). Examples: `"command -v nvidia-smi"`. |
| `empty` | true or false | `false` | no | true reserves the rectangle but opens no window. A pane with no settings (or a missing a or b) is already empty; empty makes it explicit. false gives a pane with no other settings an interactive shell. true cannot be combined with run. |
| `description` | string | none | no | Free text about the file, layout, split node or leaf. Ignored by tilepane; JSON has no comments, so use this instead. |
| `terminal` | string or object | `"auto"` | yes | The terminal that runs the pane: "auto" (kitty, alacritty, gnome-terminal, xterm, first found), a terminal name, or an object {"cmd": [...]} with a command template that contains the {command} placeholder (and optionally {title}). Examples: `"gnome-terminal"`, `{"cmd": ["foot", "--title", "{title}", "--", "{command}"]}`. |
| `shell` | string | `"auto"` | yes | The shell that runs the pane's commands and the interactive prompt afterwards: "auto" (your login shell, $SHELL), a name such as "bash", "zsh" or "fish", or a full path. A pane with only shell set opens that shell. Examples: `"bash"`, `"zsh"`, `"/usr/bin/fish"`. |
| `profile` | string | none | yes | Terminal-specific profile name (for example a gnome-terminal profile). A terminal that cannot use it produces a warning. |
| `font_size` | number | none | yes | Font size in points, for terminals that can set it from the command line. A terminal that cannot honor it produces a warning. Examples: `11`. |
| `snap` | `"cell"`, `"pixel"` | `"cell"` | yes | "cell" rounds the window size down to whole character cells (a gap of up to one cell may remain on the right and bottom). "pixel" forces the exact pixel size when the terminal and window manager allow it. |
| `on_exit` | `"keep"`, `"close"`, `"restart"` | `"keep"` | yes | What happens when the pane's command ends: "keep" prints the exit status and leaves an interactive shell, "close" closes the window, "restart" runs the command again after restart_delay seconds. |
| `restart_delay` | number | `1` | yes | Seconds to wait before restarting when on_exit is "restart". Also the minimum time between restarts, so a failing command does not loop at full speed. |
| `max_restarts` | whole number | `0` | yes | Maximum number of restarts when on_exit is "restart". 0 means unlimited. After the limit the window behaves as "keep". |
| `stop_on_error` | true or false | `false` | yes | In a list of commands (mode "sequence"), stop at the first command that fails instead of continuing with the next. |
| `decorations` | true or false | `true` | yes | false removes the window border and title bar when the terminal and window manager allow it. |
| `cwd` | string | none | yes | Working directory of the command. ~ and $VAR are expanded. A directory that does not exist is an error shown in the pane. Examples: `"~"`, `"~/projects/app"`. |
| `env` | object | none | yes | Extra environment variables for the command, as an object with string values. ~ and $VAR are expanded in the values. Merged key by key down the tree instead of replaced. Examples: `{"LANG": "C"}`. |
| `margin` | number | `8` | yes | Total gap in pixels between two neighbouring windows; each window gets half of it on every side (an odd value is split floor and ceiling so the gap is exact). On a split node it applies to everything below it. Examples: `8`. |

## Monitors

Monitor aliases for --monitor. Each alias maps to a connector name such as "HDMI-1" (see tilepane --monitors) or to a monitor number. Example: `{"left": "DP-1", "main": "HDMI-1", "side": 2}`.
