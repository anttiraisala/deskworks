# Changelog

## Unreleased

- The "This monitor is excluded" notice now also appears for **Cascade Workspace** and **Cascade All Workspaces** when they are started on an excluded monitor. Before, it appeared only for **Cascade Windows**. The cascade itself is unchanged: the other monitors and workspaces are cascaded as before and the excluded monitor is left alone.
- New option `--editor COMMAND` for `--edit-config`: choose the editor that opens the configuration file (`--edit-config --editor gedit`, `--editor nano`, `--editor "code --wait"`). The command runs in the terminal until the editor is closed, so editors that need a terminal work too.
- `--edit-config` opens the configuration file with the desktop's default text editor instead of the handler of the JSON type. When that was a sandboxed browser (for example Firefox as a snap) it showed "Access to the file was denied", because the browser cannot read `~/.config`.
- **Changed: workspace numbering.** Workspaces in `exclude` rules and in `--list-targets` are now numbered from the bottom left corner, left to right along each row and then row by row upwards, like in the other deskworks tools (before: reading order from the top left). The grid position `"x,y"` counts `y` from the bottom: `"0,0"` is the bottom-left workspace (before: the top-left one). On a 2 x 2 grid the old numbers 0, 1, 2, 3 (top row, then bottom row) are now 2, 3, 0, 1. Existing `exclude` rules that name a workspace must be updated; run `cascade-windows --list-targets` to see the numbers.
- The `Rect` type now comes from the shared `deskmap` library, which `install.sh` copies next to the program. Install from a full clone of the deskworks repository.
- Excluding monitors and workspaces: the `exclude` setting lists rules (`monitor` and/or `workspace`) for places the cascade leaves alone. Monitors are given by name or number, workspaces by number or by grid position `x,y`, numbered left to right and top to bottom from 0.
- `--list-targets` prints the workspace numbers and positions and the monitor names and numbers; `--diagnose` includes the same and warns about rules that match nothing.
- A short notification (and a message in the terminal) tells why nothing happened when the monitor is excluded; `notify.excluded` turns the notification off.
- `--ignore-exclusions` and a second shortcut, `Ctrl+Super+Shift+C`, cascade the monitor under the pointer even if it is excluded. The installer registers both shortcuts (Cinnamon, Unity 7) and the GNOME extension provides both; `--keybinding-id` selects which one `--install-keybinding` registers and `--remove-keybinding` removes both.
- GNOME protocol: the state optionally carries `workspace_columns`.

## 0.3.0

- GNOME Shell support (Ubuntu 24.04 with GNOME Shell 46 and Ubuntu 26.04 with GNOME Shell 50, Wayland and X11 sessions) through a thin GNOME Shell extension. All layout logic stays in the shared Python core. See `docs/GNOME.md`.
- The extension adds the `Super+Shift+C` shortcut and a panel menu with the same entries as the desktop menu.
- `./install.sh` and `cascade-windows` detect the desktop and choose the right version automatically (`--backend auto|x11|gnome` overrides it).
- Dialogs and windows that cannot be resized are cascaded too: the top-right corner goes to the cascade position and the size is kept (`skip.dialogs` turns this off).
- New options: `--reset-config`, `--enable-gnome-extension`, `--disable-gnome-extension`, `--environment-report`; the installer and uninstaller gained `--reset-config` and `--purge`.
- The right-click entries are grouped into a Nemo submenu where Nemo supports it.
- Ubuntu Unity 7: the shortcut is registered under `com.canonical.unity.settings-daemon`, where Unity reads its custom shortcuts. The desktop menu stays a flat list there (Nemo limitation).

## 0.2.0

- X11 version for Linux Mint (Cinnamon) and Ubuntu Unity 7: per monitor and per workspace cascade, `Super+Shift+C`, desktop right-click menu, undo and a JSON configuration file.
