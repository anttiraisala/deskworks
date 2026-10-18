# deskworks

Small Linux desktop tools that share one understanding of the desktop: which
monitors there are, how the workspaces are arranged, and where windows may go.

| Folder | What it is | State |
|---|---|---|
| [`deskmap/`](deskmap/) | Library. Reads monitors, workspaces, work areas and windows, and moves and sizes windows. Both tools below are built on it. | pure parts and X11 backend done (`Rect`, monitors, workspaces, work area, placement maths, placing and closing windows), used by tilepane; window listing for cascade-windows next (see [PROGRESS.md](PROGRESS.md)) |
| [`tilepane/`](tilepane/) | Opens terminal windows at exact positions per monitor and workspace and runs commands in them. Layouts are JSON trees of splits and panes, editable in a browser. | working (X11) |
| [`cascade-windows/`](cascade-windows/) | Windows-style "Cascade windows" for Linux: stacks the windows of a monitor or workspace in a neat cascade. | working (X11, GNOME Shell extension) |

The tools are independent programs with their own installation and their own
README. They live in one repository because they change together with the
library. Room is left for more tools that use `deskmap`.

Quickest way to see what it does: install tilepane (see [Install tilepane](#install-tilepane)) and run `tilepane --demo`.

## Requirements

Everything below is for Ubuntu and Linux Mint with an **X11 session** (Mint Cinnamon, Ubuntu with Unity 7).
Check the session type first; it must print `x11`:

```
echo $XDG_SESSION_TYPE
```

| What | Why | Package (apt) | Needed by |
|---|---|---|---|
| git | gets the source | `git` | both |
| Python 3.9 or newer | both are Python programs | `python3` (preinstalled) | both |
| pipx | installs tilepane in its own isolated environment | `pipx` | tilepane |
| python-xlib | talks to the X server (tilepane gets its own copy through pipx; cascade-windows uses the system one) | `python3-xlib` | cascade-windows (system), tilepane (via pipx) |
| xrandr | finds the monitors | `x11-xserver-utils` | both |
| a terminal | the windows tilepane opens | `gnome-terminal` (preinstalled on Ubuntu and Mint) or `xterm` | tilepane |
| Nemo | desktop right-click menu of cascade-windows | `nemo` (preinstalled on Mint and Unity 7) | cascade-windows |
| notify-send | desktop notifications ("This monitor is excluded") | `libnotify-bin` (usually preinstalled) | cascade-windows (optional) |

Install all of it in one go (packages that are already installed are skipped):

```
sudo apt update
sudo apt install git pipx python3-xlib x11-xserver-utils xterm libnotify-bin
pipx ensurepath
export PATH="$HOME/.local/bin:$PATH"   # the same, for this terminal right now
```

`pipx ensurepath` adds `~/.local/bin` to your `PATH` for terminals opened from now on; the `export` line makes
it work in the terminal you are in, so you can go on without opening a new one. If you skip both, the commands
`tilepane` and `cascade-windows` are not found.

Optional, only for a more colourful `tilepane --demo`: `htop cmatrix sl figlet fortune-mod cowsay lm-sensors`.

## Get the repository

One clone holds all three projects:

```
cd ~
git clone https://github.com/anttiraisala/deskworks.git
cd deskworks
```

(With SSH: `git clone git@github.com:anttiraisala/deskworks.git`.) Update later with `git pull` in `~/deskworks`.

## Install tilepane

```
cd ~/deskworks/tilepane
pipx install -e '.[x11]'
```

- `[x11]` adds python-xlib. Without it tilepane can only compute layouts (`--dry-run`).
- `-e` (editable) means that `git pull` updates the program without reinstalling it.
- The shared library `deskmap` is fetched automatically from this repository's `master` branch on GitHub, so the
  computer needs an internet connection and git during the installation. That copy is a snapshot made at the
  installation and it does not follow `git pull`. Make tilepane use the `deskmap` folder of your clone instead, so
  that the two never differ (the new `--analyze` needs this after an update):

  ```
  pipx runpip tilepane install -e ~/deskworks/deskmap
  ```
- If an older tilepane is installed with pipx, remove it first with `pipx uninstall tilepane`, or add `--force`
  to the command above.

Check the installation:

```
tilepane --doctor        # environment, monitors, terminals, backend
tilepane --monitors      # monitor numbers (0 = leftmost)
tilepane --workspaces    # workspaces as a grid with their numbers (0 = bottom left)
tilepane --demo          # opens windows on monitor 0; close them with:
tilepane --close all
```

More in [tilepane/README.md](tilepane/README.md).

## Install cascade-windows

```
cd ~/deskworks/cascade-windows
./install.sh
```

- The installer works at user level; no root rights (`sudo`) are needed. Python-xlib must already be installed
  (`sudo apt install python3-xlib`), or run `./install.sh --install-deps`.
- It copies the program and the `deskmap` library to `~/.local/share/cascade-windows/lib`, creates the command
  `~/.local/bin/cascade-windows`, adds the right-click entries of the desktop (Nemo actions) and registers the
  shortcuts `Super+Shift+C` and `Ctrl+Super+Shift+C`.
- Run the installer from a full clone of this repository, because it needs the `deskmap` folder next to
  `cascade-windows`.
- On GNOME (Ubuntu 24.04 and newer, Wayland) it installs a GNOME Shell extension instead; see
  [cascade-windows/docs/GNOME.md](cascade-windows/docs/GNOME.md).
- If an older version is installed, running `./install.sh` again replaces it. Your configuration file is not
  overwritten.

After the installation restart the desktop file manager so that the menu appears, and check the result:

```
nemo --quit
hash -r                          # make the shell forget old command locations
cascade-windows --diagnose       # environment, monitors, work areas, windows
cascade-windows --list-targets   # workspace and monitor numbers for the 'exclude' rules
cascade-windows                  # cascade the monitor under the pointer; undo with: cascade-windows --undo
```

More in [cascade-windows/README.md](cascade-windows/README.md).

## Where the files are

| What | Location |
|---|---|
| The repository (source) | `~/deskworks` (or wherever you cloned it) |
| tilepane program (pipx) | `~/.local/share/pipx/venvs/tilepane`, command `~/.local/bin/tilepane` |
| tilepane layouts and settings | `~/.config/tilepane/config.json` (layouts can also be anywhere; you give the path) |
| tilepane state (open windows) | `~/.local/state/tilepane/` |
| cascade-windows program | `~/.local/share/cascade-windows/lib`, command `~/.local/bin/cascade-windows` |
| **cascade-windows configuration** | **`~/.config/cascade-windows/config.json`** (create or edit it with `cascade-windows --edit-config`; show what is in effect with `--show-config`) |
| cascade-windows undo data | `~/.local/state/cascade-windows/` |
| cascade-windows right-click entries | `~/.local/share/nemo/actions/cascade-windows-*.nemo_action`, submenu in `~/.config/nemo/actions-tree.json` |

If `XDG_CONFIG_HOME`, `XDG_DATA_HOME` or `XDG_STATE_HOME` are set, they replace `~/.config`, `~/.local/share` and
`~/.local/state`.

## Update

```
cd ~/deskworks
git pull
cd tilepane && pipx install --force -e '.[x11]'
pipx runpip tilepane install -e ~/deskworks/deskmap   # tilepane uses the deskmap of the clone
cd ../cascade-windows && ./install.sh
```

## Uninstall

tilepane (it asks before it does anything; `--yes` skips the question):

```
tilepane --uninstall            # closes its windows, removes its state and the program; layouts stay
tilepane --uninstall --purge    # also deletes ~/.config/tilepane
```

By hand the same is `pipx uninstall tilepane`.

cascade-windows:

```
cd ~/deskworks/cascade-windows
./uninstall.sh                  # removes the program, shortcuts and menu entries; the configuration stays
./uninstall.sh --purge          # also deletes the configuration, its backup and the undo data
nemo --quit                     # refresh the desktop menu
```

Finally, if you want to remove everything, delete the clone (it holds the source of both tools and `deskmap`;
do this only after both tools are uninstalled or you no longer need them):

```
rm -rf ~/deskworks
```

## Troubleshooting

| Problem | Reason and fix |
|---|---|
| `tilepane: command not found` or `cascade-windows: command not found` | `~/.local/bin` is not in `PATH` yet. Run `pipx ensurepath`, then open a new terminal (or `source ~/.bashrc`). Check with `which tilepane`. |
| `AttributeError: ... has no attribute 'open_windows'` (or another missing attribute of `deskmap`) | tilepane uses an older `deskmap` copy than the clone. Run `pipx runpip tilepane install -e ~/deskworks/deskmap`. |
| `cascade-windows: error: unrecognized arguments: --list-targets` | An old cascade-windows is installed. Run `git pull` and `./install.sh` in `cascade-windows`. |
| `The deskmap library was not found` during `./install.sh` | You are not in a full clone. Clone the whole repository and run the installer from `deskworks/cascade-windows`. |
| `The Python X11 library is missing` | `sudo apt install python3-xlib` (or `./install.sh --install-deps`). |
| This is a Wayland session | Both tools move X11 windows. Choose "Ubuntu on Xorg" or a Cinnamon X11 session at login. On GNOME, cascade-windows has its own extension. |
| The right-click entries do not appear | `nemo --quit`. On Unity 7 also `pkill -9 nemo-desktop` (the session restarts it). |
| `--edit-config` opens the wrong program | Choose the editor: `cascade-windows --edit-config --editor xed`, or set `"editor": "xed"` in the configuration file (`~/.config/cascade-windows/config.json`: a line `"editor": "xed",` among the other settings, inside the outer `{ }`). |
| Saved `exclude` rules hit the wrong workspace | Workspace numbers changed to start at the bottom left; see `cascade-windows --list-targets`. |

## Why one repository

`tilepane` and `cascade-windows` both had their own code for finding monitors,
numbering workspaces, subtracting panels from the work area and placing windows
exactly. That code is hard to get right, so it should exist once. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Numbering (the same in every tool)

- **Monitors** are numbered left to right, then top to bottom. Monitor 0 is the leftmost.
- **Workspaces** are numbered from the bottom left corner, left to right along each row, then row by row upwards. Workspace 0 is bottom left. In a 3 x 2 grid:

```
3 4 5
0 1 2
```

Window managers number workspaces in their own order (usually from the top
left). `deskmap` converts between that order and the numbers a person uses; the
tools only ever show and accept the person's numbers.

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): layers, folders and dependency rules
- [docs/DESKMAP.md](docs/DESKMAP.md): what the library contains and how it is extracted
- [docs/DECISIONS.md](docs/DECISIONS.md): decisions and the reasons for them
- [PROGRESS.md](PROGRESS.md): what is done, what is open, and a dated log

## Run the tests

```
cd ~/deskworks
./scripts/test-all.sh
```

This runs the tests of every project. The live X11 tests of `tilepane` need a display; see [CLAUDE.md](CLAUDE.md).

## License

GPL-3.0-or-later, see [LICENSE](LICENSE).
