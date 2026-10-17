# Progress

Newest log entries last. See `CLAUDE.md` for how this file is kept.

## Status

| Step | Description | State |
|---|---|---|
| 1 | Repository created; tilepane and cascade-windows imported with history | done |
| 2 | Repository level documents, test script, language exceptions | done |
| 3 | `deskmap` package: pure parts (`Rect`, monitors, workspaces, work area, placement maths) with tests | next |
| 4 | `deskmap` X11 backend moved from tilepane | open |
| 5 | tilepane uses `deskmap` | open |
| 6 | Window listing and cascade operations in `deskmap`; cascade-windows uses `deskmap` | open |
| 7 | GNOME backend and extension protocol moved into `deskmap` | open |

## Log

### 2026-10-17: repository created
- Created from the maintainer's decision to share the desktop-reading code between tilepane and cascade-windows. Context: both projects had their own monitor detection, workspace numbering, work area and X11 placement code.
- `tilepane` (47 commits) and `cascade-windows` (22 commits) were added with `git subtree add`, so their history is kept in the subfolders. The original repositories were not touched.
- Tests at import: tilepane 384 pass (5 skipped: live X11 and browser tests that need a display), cascade-windows 218 pass (21 skipped).
- Not yet changed: no code was edited by the import. The projects still use their own copies of the shared logic.
- Open: confirm the repository license for cascade-windows (it had none), and name of the repository's Python distribution if `deskmap` should be published.
