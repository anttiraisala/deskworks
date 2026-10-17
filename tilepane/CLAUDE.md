# CLAUDE.md

Guidance for Claude sessions working on tilepane. Read SPEC.md (behaviour and
decisions) and PROGRESS.md (what is done, what is open) before changing code.

## The project

tilepane opens terminal windows at exact positions per monitor and runs
commands in them. Layouts are JSON trees of splits and panes. Python 3.9+,
standard library only; python-xlib is the optional X11 dependency. Linux, X11
first (Wayland backends are planned, not built). Public, GPL-3.0.

## Working with the owner

- The owner (Antti) writes in Finnish, often by speech-to-text, so words can be
  garbled; read for intent. Answer in Finnish, plainly; explain technical terms
  simply when asked. Code, comments, docs and commit messages are in English.
  `docs/PROJECT-BRIEF.md` is a summary written for adding to the owner's Claude
  project; keep it current like the other documentation. Exceptions to the
  English rule are listed in `../.language-exceptions` (none at the moment).
- This project lives in the `tilepane/` folder of the deskworks repository; the
  repository level `../CLAUDE.md` also applies. Monitor detection and numbering,
  workspaces, per-monitor work areas and placement arithmetic live in the
  `deskmap` library (`../deskmap`); change them there, not here.
- Branch: work is done directly on `master` and pushed there (the owner's
  decision on 2026-10-17; the earlier development branches `claude-personal`
  and `claude/zealous-clarke-naq4z8` were merged into it and are to be deleted).
- The owner runs Linux Mint (Cinnamon, X11) and tests changes there. Say clearly
  what was verified live and what was not.
- When a design choice is the owner's to make, propose one option with reasons
  and ask; otherwise decide, implement and record the decision.
- README rule from the owner: requirements (every tool and package) come first,
  and the demo is shown prominently in the install/try part.

## Commands

```
# run from the tilepane/ directory; deskmap is the sibling folder ../deskmap
export PYTHONPATH=src:.:../deskmap/src
python3 -m unittest discover -s tests -t .      # all tests
python3 -m tilepane.docgen                       # after editing the schema
python3 -m tests.make_vectors                    # after a deliberate geometry change
python3 -m tilepane.cli --dry-run examples/meters.json
```

- The schema (`src/tilepane/tilepane.schema.json`) is the source of truth for
  keys. `docgen` writes `docs/CONFIG.md` and the schema copy embedded in
  `src/tilepane/editor/editor.html`; tests fail when either is stale. A new key
  also goes into the tables in `config.py` (INHERITED, BUILTIN, ...).
- The editor's JavaScript geometry (in `editor.html`, between `BEGIN GEOMETRY`
  and `END GEOMETRY`) is a port of `geometry.py`; both are checked against
  `tests/vectors/geometry.json`. Change them together.
- `tests/js/editor.features.mjs` (page opened as a file) and
  `tests/js/editor.e2e.mjs` (through the editor server) drive the editor in
  Chromium; they run inside the unit tests when node and Playwright are installed.

## Testing real windows in a cloud container

There is no screen by default. This works (Ubuntu container):

```
apt-get install -y openbox xterm x11-xserver-utils x11-utils
python3 -m venv /tmp/venv && /tmp/venv/bin/pip install -e ../deskmap -e '.[x11]'
export DISPLAY=:99 XDG_SESSION_TYPE=x11 XDG_STATE_HOME=/tmp/tp-state
Xvfb :99 -screen 0 1920x1080x24 & openbox &
TILEPANE_LIVE=1 TILEPANE_MONITOR=0 PYTHONPATH=src:. /tmp/venv/bin/python -m unittest tests.test_x11_live
```

Openbox has 4 workspaces (EWMH), which is enough to test workspace handling.
A 2 x 2 grid: `xprop -root -f _NET_DESKTOP_LAYOUT 32c -set _NET_DESKTOP_LAYOUT 0,2,2,0`.
Compiz viewports can be simulated without a window manager: start `Xvfb -noreset`
(otherwise root properties vanish when the last client disconnects) and set
`_NET_NUMBER_OF_DESKTOPS` 1, `_NET_DESKTOP_GEOMETRY` to a multiple of the screen
and `_NET_DESKTOP_VIEWPORT` with xprop; without a window manager nothing moves
windows, so this checks the numbering and offsets only.
gnome-terminal and Cinnamon itself cannot be tested this way.

Careful: `pkill -f PATTERN` also matches the shell running the command when the
pattern appears in it, and kills that shell. Use `pkill -x NAME` or explicit PIDs.

## Keep every file up to date

After each change, and before every commit, go through all files the change
could affect and make them agree with the code as it now is. Do not stop at
the file you edited. Check in particular:

- comments and docstrings in the changed modules and in the modules that call
  them (module docstrings often describe behaviour in a few lines);
- `HELP` in `invocation.py`, error and status messages, `--doctor` output;
- the schema descriptions (they become `docs/CONFIG.md`, `--explain` and the
  editor's field help), then run `docgen`;
- README.md, SPEC.md, PROGRESS.md, CLAUDE.md, `docs/PROJECT-BRIEF.md`,
  `examples/` and the editor's texts in `editor.html`;
- test names and docstrings that describe the old behaviour.

Search for the old behaviour by name (`grep -rn` for the key, option or phrase)
rather than relying on memory. When a step is finished, read through the whole
repository once for anything stale and fix it in the same branch.

### Log files keep their history

Two kinds of files are treated differently:

- **Log files** record how the work went: `PROGRESS.md` (its "Log" section)
  and `docs/SPEC-REVIEW.md` (the review as it was made). Old entries stay as
  they were written, even when what they say is no longer true; that history
  is the point. Never rewrite, shorten or "update" an old entry, and never
  delete one. New information is added as a new dated entry at the end; when
  it changes an earlier decision, the new entry says so ("Before this, ...").
  Only a plain mistake (a typo, a wrong file name) may be corrected in place.
  The current-state parts of a log file are updated, not appended to: the
  status table at the top of `PROGRESS.md`.
- **Every other file** describes the project as it is now (README.md, SPEC.md,
  CLAUDE.md, docs/CONFIG.md, docs/PROJECT-BRIEF.md, code, comments, help texts). These are rewritten
  so they are true today, with no leftover description of old behaviour.

A file that is not listed here and looks like a log (dated entries, newest
last) is a log file too; when unsure, ask before changing old entries.

## Recording work

- Every finished step gets an entry at the end of PROGRESS.md (what was built,
  decisions not fixed by the spec, what was tested live, what is still open,
  test count) and the status table is updated.
- Decisions that change behaviour go into SPEC.md (for the editor, see "As
  built" in section 5); user-facing changes go into README.md.
- Commit in small, described steps and push to `master`.
