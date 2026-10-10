"""Command line entry point."""

from __future__ import annotations

import sys
from typing import Optional, TextIO

from . import __version__, config, docgen, doctor, geometry, monitors
from .invocation import HELP, Invocation, Task, UsageError, parse


def _pane_summary(leaf: dict, when_evaluated: bool) -> str:
    if leaf.get("empty"):
        text = "(empty)"
    else:
        run = leaf.get("run")
        text = "(shell)" if run is None else "; ".join(run) if isinstance(run, list) else run
    if len(text) > 48:
        text = text[:45] + "..."
    if "when" in leaf and not when_evaluated:
        text += f"  [when: {leaf['when']}]"
    return text


def _format_layout(name: str, source: str, mon: monitors.Monitor, resolved: dict,
                   leaves: list[geometry.LeafRect], *, verbose: bool,
                   when_evaluated: bool) -> str:
    lines = [f'layout "{name}"  ({source})  monitor {mon.number} {mon.name} '
             f"{mon.width}x{mon.height}+{mon.x}+{mon.y}"]
    ids = [lr.leaf.get("id", lr.id) for lr in leaves]
    width = max(len(i) for i in ids)
    lines.append(f"  {'id':<{width}}  {'x':>6} {'y':>6} {'w':>6} {'h':>6}  pane")
    for pane_id, lr in zip(ids, leaves):
        r = lr.rect
        row = (f"  {pane_id:<{width}}  {r.x:>6} {r.y:>6} {r.width:>6} {r.height:>6}  "
               f"{_pane_summary(lr.leaf, when_evaluated)}")
        lines.append(row)
        if verbose:
            o, leaf = lr.outer, lr.leaf
            lines.append(f"  {'':<{width}}  pane {o.width}x{o.height}+{o.x}+{o.y}, "
                         f"terminal {leaf.get('terminal')}, snap {leaf.get('snap')}, "
                         f"on_exit {leaf.get('on_exit')}, margin {leaf.get('margin')}")
    return "\n".join(lines)


class _Runner:
    def __init__(self, inv: Invocation, out: TextIO, err: TextIO,
                 detected: Optional[list[monitors.Monitor]]):
        self.inv, self.out, self.err = inv, out, err
        self._monitors = detected
        self._files: dict[str, object] = {}
        self._noted_area = False

    def monitors(self) -> list[monitors.Monitor]:
        if self._monitors is None:
            found, _source, errors = monitors.wait_for_monitors(self.inv.wait_monitors)
            for e in errors:
                print(f"warning: {e}", file=self.err)
            self._monitors = found
        return self._monitors

    def load(self, task: Task) -> config.ConfigFile:
        path = task.source or config.default_config_path()
        if path not in self._files:
            try:
                cfg = config.load_file(path, strict=self.inv.strict)
            except config.ConfigError as exc:
                self._files[path] = exc
            else:
                for w in cfg.warnings:
                    print(f"warning: {w}", file=self.err)
                self._files[path] = cfg
        got = self._files[path]
        if isinstance(got, config.ConfigError):
            raise got
        return got  # type: ignore[return-value]

    @staticmethod
    def select(cfg: config.ConfigFile, task: Task) -> list[str]:
        if not task.layouts:
            if len(cfg.layouts) == 1:
                return cfg.names()
            raise config.ConfigError([
                f"{cfg.source}: the file has {len(cfg.layouts)} layouts; choose one with "
                f"--layout NAME ({', '.join(cfg.names())})"])
        missing = [n for n in task.layouts if cfg.get(n) is None]
        if missing:
            raise config.ConfigError([
                f"{cfg.source}: no layout named {', '.join(repr(n) for n in missing)} "
                f"(available: {', '.join(cfg.names())})"])
        return list(dict.fromkeys(task.layouts))

    def error(self, message: str) -> None:
        print(f"error: {message}", file=self.err)

    def dry_run(self) -> int:
        ok = failed = 0
        tasks = self.inv.tasks or [Task()]
        for task in tasks:
            try:
                cfg = self.load(task)
                names = self.select(cfg, task)
                spec = task.monitor or self.inv.default_monitor or "0"
                mons = monitors.resolve_many(spec, self.monitors(), cfg.monitors)
            except config.ConfigError as exc:
                for e in exc.errors:
                    self.error(e)
                failed += 1
                continue
            except monitors.MonitorError as exc:
                self.error(f"{task.source or config.default_config_path()}: {exc}")
                failed += 1
                continue

            when_eval = config.run_when if self.inv.eval_when else None
            for name in names:
                for mon in mons:
                    try:
                        resolved = config.resolve_layout(cfg, cfg.get(name), when_eval=when_eval)
                        area = geometry.Rect(mon.x, mon.y, mon.width, mon.height)
                        leaves = geometry.compute(resolved, area)
                    except config.ConfigError as exc:
                        for e in exc.errors:
                            self.error(e)
                        failed += 1
                        continue
                    except geometry.GeometryError as exc:
                        self.error(f"{cfg.source}: layout '{name}' on monitor {mon.number}: {exc}")
                        failed += 1
                        continue
                    print(_format_layout(name, cfg.source, mon, resolved, leaves,
                                         verbose=self.inv.verbose,
                                         when_evaluated=self.inv.eval_when), file=self.out)
                    if resolved["area"] == "work" and not self._noted_area:
                        self._noted_area = True
                        print("  note: panels are not subtracted yet; the full monitor is used "
                              "(per-monitor work area comes in step 5)", file=self.out)
                    ok += 1
        if ok + failed > 1 or failed:
            print(f"dry run: {ok} ok, {failed} failed", file=self.out if not failed else self.err)
        return 1 if failed else 0

    def list_layouts(self) -> int:
        failed = 0
        for task in self.inv.tasks or [Task()]:
            try:
                cfg = self.load(task)
            except config.ConfigError as exc:
                for e in exc.errors:
                    self.error(e)
                failed += 1
                continue
            for lay in cfg.layouts:
                panes = sum(1 for _ in config.iter_leaves(lay["split"]))
                print(f"{lay['name']}\t{panes} panes\t{cfg.source}", file=self.out)
        return 1 if failed else 0


def main(argv: Optional[list[str]] = None, *, out: Optional[TextIO] = None,
         err: Optional[TextIO] = None,
         detected: Optional[list[monitors.Monitor]] = None) -> int:
    out = out or sys.stdout
    err = err or sys.stderr
    try:
        inv = parse(sys.argv[1:] if argv is None else argv)
    except UsageError as exc:
        print(f"tilepane: {exc}", file=err)
        return 2

    if inv.action == "help":
        print(HELP, end="", file=out)
        return 0
    if inv.action == "version":
        print(f"tilepane {__version__}", file=out)
        return 0
    if inv.action == "doctor":
        print(doctor.render(doctor.collect()), file=out)
        return 0
    if inv.action == "monitors":
        found, _source, errors = monitors.wait_for_monitors(inv.wait_monitors)
        for e in errors:
            print(f"warning: {e}", file=err)
        if not found:
            print("no monitors found", file=err)
            return 1
        print(monitors.format_table(found), file=out)
        return 0
    if inv.action == "explain":
        text = docgen.explain(inv.explain or "")
        if text is None:
            hint = docgen.suggest(inv.explain or "")
            more = f" (did you mean {', '.join(hint)}?)" if hint else ""
            print(f"tilepane: unknown key '{inv.explain}'{more}", file=err)
            return 2
        print(text, file=out)
        return 0

    runner = _Runner(inv, out, err, detected)
    if inv.action == "list":
        return runner.list_layouts()
    if not inv.dry_run:
        print("tilepane: opening windows is not implemented yet (step 4 of SPEC.md "
              "section 7); use --dry-run to see the computed layout", file=err)
        return 2
    return runner.dry_run()


if __name__ == "__main__":
    sys.exit(main())
