# CLAUDE.md

Guidance for Claude sessions working on deskworks. Read `docs/ARCHITECTURE.md`,
`docs/DECISIONS.md` and `PROGRESS.md` first. Each project folder has its own
`CLAUDE.md` (`tilepane/`, `cascade-windows/`); read the one of the project you
are changing. The rules below apply to the whole repository.

## The repository

Three projects in one repository: `deskmap` (library), `tilepane` and
`cascade-windows` (tools that use it). Linux, X11 first, GNOME Shell extension
for GNOME on Wayland. Python 3.9+, standard library only except the optional
python-xlib. Public, GPL-3.0-or-later.

## Working with the owner

- The owner (Antti) writes in Finnish, often by speech-to-text, so words can be garbled; read for intent. Answer in Finnish, plainly; explain technical terms simply when asked.
- Branch: work is done directly on `master` and pushed there.
- The owner runs Linux Mint (Cinnamon, X11) and tests changes there. Say clearly what was verified live and what was not.
- When a design choice is the owner's to make, propose one option with reasons and ask; otherwise decide, implement and record the decision in `docs/DECISIONS.md`.
- Be a critical partner: point out contradictions or hidden assumptions in a request before doing the work.
- README rule: requirements (every tool and package) come first, and the demo is shown prominently in the install/try part.

## Language

Everything in the repository is English, whatever language the chat is in.
This covers code, identifiers, comments, docstrings, messages, tests, data
files, documentation, commit messages and branch names.

- Never translate or "normalize" material the owner supplied or an existing file; edit a file in its own language.
- Do not add Finnish (or other) UI text unless localization is asked for; then English stays the source and translations go in separate resource files.
- Exceptions are listed in `.language-exceptions` (gitignore-style globs with a language). Create new content in those paths in that language. If new non-English content is needed in an unlisted path, ask the owner once.
- Proper nouns and terms of art stay in their original form.
- Before reporting a task done, check that no non-English text slipped into files or commit messages.

## Layout rules

- `deskmap` never imports a tool; tools never import each other (see `docs/ARCHITECTURE.md`).
- A code move and a behaviour change are separate commits. A moved module takes its tests with it.
- A change to `deskmap` that a tool depends on is made together with the tool's update, in the same commit.

## Commands

```
./scripts/test-all.sh                                   # all projects
cd tilepane && PYTHONPATH=src:. python3 -m unittest discover -s tests -t .
cd cascade-windows && python3 -m unittest discover -s tests
```

Project specific commands (docgen, test vectors, the editor tests, testing real
windows under Xvfb + openbox) are in `tilepane/CLAUDE.md`.

## Keep every file up to date

After each change, and before every commit, go through all files the change
could affect and make them agree with the code as it now is: comments,
docstrings, help texts, error messages, READMEs, `docs/`, examples and test
names. Search for the old behaviour by name (`grep -rn`) instead of relying on
memory.

### Log files keep their history

- **Log files** record how the work went: `PROGRESS.md` (its "Log" section), `docs/DECISIONS.md`, `tilepane/PROGRESS.md`, `tilepane/docs/SPEC-REVIEW.md`, `cascade-windows/CHANGELOG.md`. Old entries stay as written, even when they are no longer true. Never rewrite, shorten or delete one. New information is a new dated entry at the end; when it changes an earlier decision the entry says so. Only a plain mistake (typo, wrong file name) may be corrected in place. The current-state parts (the status table in `PROGRESS.md`) are updated, not appended to.
- **Every other file** describes the project as it is now and is rewritten so it is true today.

A file that looks like a log (dated entries, newest last) is a log file too;
when unsure, ask before changing old entries.

## Recording work

- Every finished step gets a dated entry at the end of `PROGRESS.md` (what was built, decisions, what was tested live, what is open, test counts) and the status table is updated.
- Decisions go into `docs/DECISIONS.md`.
- Commit in small, described steps and push to `master`.
