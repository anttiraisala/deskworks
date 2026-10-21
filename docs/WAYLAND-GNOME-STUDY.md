# Study: tilepane and deskworks on GNOME (Wayland and X11)

Written 2026-10-21 at the owner's request. It is a study, not a decision: nothing here is built yet. Goal: tilepane and
cascade-windows (through `deskmap`) work on Linux Mint Cinnamon, Ubuntu GNOME 24.04 and 26.04, and Ubuntu Unity 7.

## 1. Where each desktop stands

| Desktop | Session | tilepane | cascade-windows |
|---|---|---|---|
| Linux Mint, Cinnamon | X11 | works (verified live) | works (verified live) |
| Ubuntu Unity 7 (Compiz) | X11 | works (verified live, viewports as workspaces) | works (verified live) |
| Ubuntu 24.04 GNOME | "Ubuntu on Xorg" (`/usr/share/xsessions/ubuntu-xorg.desktop` exists) | should work through the X11 backend; **not tried yet** | X11 backend; not tried yet |
| Ubuntu 24.04 GNOME | Wayland (the default) | **does not work**: "no backend for a wayland session" | needs the GNOME extension; extension never run in a real shell |
| Ubuntu 26.04 GNOME (Shell 50) | Wayland only (no `/usr/share/xsessions/`) | **does not work** (same message) | same as above |

The first thing to do costs nothing: run `tilepane --doctor`, `tilepane --demo` and `cascade-windows` in the Xorg session of
the 24.04 machine. That settles the "GNOME 24, X11" row.

## 2. Why Wayland needs something extra

On Wayland an ordinary program cannot move or size other programs' windows; only the compositor (GNOME Shell, which contains
Mutter) can. So a small GNOME Shell extension does the moving and tilepane/cascade ask it over D-Bus. Cascade-windows already has such
an extension (`cascade-windows/gnome-extension/`, protocol in `cascade_windows/shell_protocol.py`, backend in
`gnome_backend.py`, about 640 lines of JavaScript and Python plus tests). Its own documentation says it **was written without access to a
GNOME session** and lists the places most likely to be wrong (`docs/GNOME.md`, "Unverified against a real shell"). It has never run in a real shell.

## 3. What exists and can be reused

| Piece | Where | Reusable for tilepane? |
|---|---|---|
| D-Bus service in the extension (`GetState`, `Apply`), JSON protocol v1 | `gnome-extension/lib/service.js`, `protocol.js`, `shell_protocol.py` | Yes, as the base. |
| Window list with id, title, wm_class, workspace, rectangle (frame), kind, minimized, fullscreen, sticky, maximized, stacking order | `lib/windows.js` `collectState` | Yes: this is what `--analyze` (`open_windows`) needs, and new-window detection. |
| Operations: place (move and resize), raise, maximize, unmaximize | `Apply` | Yes: placing is the main need. |
| Monitor geometry and work area per monitor (panel and dock subtracted) | `collectState` | Yes; connector names are missing (`Monitor N`). |
| Workspace count, current one, grid columns | `collectState` | Yes; `deskmap.workspaces` already numbers a grid from the bottom left. |
| Installer that copies and enables the extension | `cascade_windows/gnome_install.py`, `install.sh` | Partly: it is part of cascade's install, tilepane lives in pipx. |
| A fake shell and a private D-Bus session for tests, Node tests of the pure parts | `tests/fake_shell.py`, `gnome-extension/tests/` | Yes. |
| Node-free parts of tilepane (layout, geometry, `/proc` command reading, editor, `--analyze` logic) | tilepane | Unchanged: they do not touch the window system. |

## 4. What is missing for tilepane

Tilepane uses a different backend interface (`deskmap.backends.Backend`, a Protocol) than cascade (`cascade_windows.backend.Backend`, a class).
Both have their own X11 implementation (397 and 831 lines). The GNOME backend exists only in cascade's interface. Needed:

1. **A `deskmap` backend for GNOME** implementing the Protocol: `windows`, `open_windows`, `active_window`, `pointer`, `wait_new_window`
   (poll `GetState` until a new window with the right class appears), `place`, `metrics`, `find`, `current_desktop`, `desktop_count`,
   `desktop_info`, `move_to_desktop`, `workspace_offset`, `close`. The plan item 7 in `PROGRESS.md` ("GNOME backend and extension protocol moved into
   deskmap") is this.
2. **Protocol v2** with: the window's `pid`, a `close` operation (`Meta.Window.delete`), `move to workspace`, `activate`, and monitor connector names
   (or read them from `org.gnome.Mutter.DisplayConfig` on D-Bus, which needs no extension).
3. **Monitors on GNOME.** Today `deskmap.monitors.detect()` uses `xrandr` (through XWayland on Wayland). With fractional scaling or different
   scales it reports other numbers than the compositor uses. The shell's own monitor list must be the source on GNOME (connector name, scale, logical position).
4. **Window recognition.** Tilepane starts a terminal with `--class=tilepane` and waits for a new window of that class. On Wayland the class is the
   application id; whether `gnome-terminal --class` gives that, and whether `Meta.Window.get_wm_class()` returns it, must be tried. Fallback: match by title,
   which tilepane already sets, or by the process id.
5. **Exact sizes without X11 size hints.** On X11 tilepane rounds a window to whole character cells with the window's size hints and the frame
   extents. Wayland terminals give no resize increments to the compositor. The position can be exact (`move_frame`); the size can be exact too, but a
   terminal may then show a partial last row or column, or refuse a size. Plan: try `snap: "none"` style placement first, learn the cell size from a
   first window (metrics) and ask the terminal for `--geometry` afterwards, as the code does on X11 for the second window.
6. **Backend choice and `--doctor`.** `backends.choose()` must pick the GNOME backend when the session is Wayland on GNOME and the extension answers, and
   say how to install it when it does not. `--doctor` already has a row `wayland-gnome-extension (not ready)`.
7. **One extension, not two.** Both tools would talk to the same D-Bus name. Recommended: one extension owned by `deskmap`
   (`deskmap/gnome-extension/`), named for deskworks, with the shortcuts and the panel menu of cascade as options that cascade's installer
   turns on, so tilepane users do not get cascade's menu. Installing it needs a command for tilepane users (`tilepane --install-gnome-extension`).
8. **Closing, workspaces and identification of "our" windows** (`find`) work by id in the protocol; the state file tilepane keeps (window id, pane id)
   must survive a shell restart (window ids are not stable then): re-find by title or class.

## 5. Risks

- **Nothing in the extension has run in a real GNOME Shell.** Bugs in `lib/windows.js` and `service.js` (D-Bus method return values, maximize calls
  that differ between Shell 46 and 50, shortcut registration) are likely. They are cheap to fix once seen.
- **Shell versions.** Ubuntu 24.04 has Shell 46 and 26.04 has 50; extension APIs change between releases. The metadata already lists 46 to 50; only 46 and 50 matter.
- **Wayland reloads extensions only at login**, so every test round on a Wayland machine needs a log out and in (or a nested/headless shell).
- **Scaling.** Fractional scaling and mixed-DPI monitors can make pixel-exact placing impossible for natively scaled windows.
- **Cell snapping** (point 5) may end with sizes that are exact only to a whole cell on Wayland.
- **Testing without the owner.** Resolved on 2026-10-21: a real GNOME Shell 46 runs headless in the container (`scripts/gnome-headless.sh`,
  `gnome-shell --headless --wayland --virtual-monitor`, with a fake logind from python3-dbusmock). Cascade-windows' extension loaded in it on the
  first try, `--diagnose` listed the monitor, work area and workspaces, and a real cascade of three Wayland windows (`foot`) put them at exactly the
  rectangles asked for. So "never run in a real shell" is no longer true for Shell 46; Shell 50 (Ubuntu 26.04) and gnome-terminal are still untested.

## 6. Plan and work estimate

A "round" below is one working session of mine followed by the owner running a few commands on a VM and pasting the output. Estimates are for
reaching "works on the machines in section 1", not for polishing.

| Step | Work | Rounds |
|---|---|---|
| 0 | Try the X11 session of GNOME 24 (no code). | 1 short |
| 1 | Cascade-windows' GNOME extension: headless Shell 46 done 2026-10-21 (works). Still to do: Shell 50 on the 26.04 VM and gnome-terminal. | 1 to 2 |
| 2 | Protocol v2 (pid, close, move to workspace, monitor names) in extension and Python; tests with the fake shell. | 1 to 2 |
| 3 | `deskmap` GNOME backend with the deskmap Protocol; move extension and protocol into `deskmap`; cascade uses the moved code; `choose()` and doctor. | 2 to 3 |
| 4 | Monitors from the shell (scale, connector names); numbering unchanged. | 1 |
| 5 | Terminal recognition and placing on Wayland: try gnome-terminal and xterm (XWayland); decide cell snapping. | 2 to 3 |
| 6 | Installer for tilepane (extension install command), docs, tests of the whole path, live checks on 24 and 26. | 1 to 2 |
| 7 | Optional later: merge the two X11 backends and the two work-area implementations; other compositors (sway, Hyprland, KDE). | not needed for the goal |

Total: roughly **9 to 14 rounds**, of which the owner's part is short each time (log in, run a command, paste). The uncertain steps are 1 and 5.
The headless shell works in the container, so steps 2, 3 and most of 5 can be done without the VMs; the owner's rounds are for Shell 50, gnome-terminal and the last check (about 4 to 6).

## 7. Decisions for the owner

1. One shared extension in `deskmap` (recommended) or two separate ones?
2. Should tilepane on Wayland accept a size that is a whole cell off (recommended: yes, with a note in the output), or insist on pixel-exact sizes?
3. Is `xterm` through XWayland an acceptable stopgap before the extension is ready? (Cheap: allow the X11 backend on Wayland for X11 windows only; gnome-terminal would still not work.)
