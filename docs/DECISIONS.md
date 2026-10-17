# Decisions

Decisions that shape the repository, with the reason. Newest last. An old
decision is not edited; a later entry says when it replaces an earlier one.

1. **One repository for the library and the tools** (2026-10-17). They change together; an interface change and its users go in one commit. A new repository was created instead of renaming `tilepane`, so the original repositories stay untouched as a safe fallback.
2. **Numbering** (2026-10-17). Monitors: left to right, then top to bottom. Workspaces: from the bottom left, left to right, then row by row upwards. This is how tilepane already works and the maintainer wants it everywhere.
3. **Coordinate model** (2026-10-17). `deskmap` uses tilepane's mechanism (desktop coordinates plus `workspace_offset`), because it places windows exactly on every monitor. cascade-windows builds its cell-relative view on top.
4. **Backends** (2026-10-17). X11 through python-xlib first; the GNOME Shell extension from cascade-windows is moved in later. Other Wayland compositors (sway, Hyprland, KWin) come after.
5. **Branch** (2026-10-17). Work is done on `master` and pushed there.
6. **Imported with history** (2026-10-17). `tilepane` and `cascade-windows` were added with `git subtree add`, so `git log` and `git blame` in the subfolders keep the original commits.
7. **License** (2026-10-17). GPL-3.0-or-later for the whole repository, as tilepane already had. cascade-windows had no license file before; adding it here is a change the maintainer should confirm.
8. **Languages** (2026-10-17). Everything is English. The one exception, `tilepane/docs/YHTEENVETO.md` (Finnish), is listed in `.language-exceptions`.
9. **Schema URLs and the project brief** (2026-10-17). Before this, the `$schema` and `$id` URLs pointed to the original `anttiraisala/tilepane` repository and `tilepane/docs/YHTEENVETO.md` was a Finnish exception. The URLs now point to `anttiraisala/deskworks/master/tilepane/src/tilepane/tilepane.schema.json`, and the Finnish summary was translated into English and renamed `tilepane/docs/PROJECT-BRIEF.md`, so decision 8 no longer has an exception and `.language-exceptions` is empty.
10. **Technology is unified where it helps** (2026-10-17). The maintainer allowed changing the technology of the projects. The tools keep their own way of being installed (tilepane through pip/pipx, cascade-windows through `install.sh`, which copies the program to `~/.local/share/cascade-windows/lib`), but both now take the shared library from this repository: tilepane through a pip dependency with a git URL, cascade-windows by `install.sh` copying `deskmap/src/deskmap` into the same `lib` folder. No tool needs a package manager that it did not need before.
