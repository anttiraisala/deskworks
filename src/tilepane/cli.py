"""Command line entry point."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Iterator, Optional, TextIO

from . import __version__, backends, config, docgen, doctor, geometry, monitors, opener, workarea
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


def _monitor_label(mon: monitors.Monitor) -> str:
    return f"monitor {mon.number} {mon.name} {mon.width}x{mon.height}+{mon.x}+{mon.y}"


def _format_layout(name: str, source: str, mon: monitors.Monitor, area: geometry.Rect,
                   leaves: list[geometry.LeafRect], *, verbose: bool,
                   when_evaluated: bool) -> str:
    lines = [f'layout "{name}"  ({source})  {_monitor_label(mon)}']
    if area != workarea.monitor_rect(mon):
        lines.append(f"  work area {area.width}x{area.height}+{area.x}+{area.y} "
                     "(monitor minus panels)")
    ids = [lr.leaf.get("id", lr.id) for lr in leaves]
    width = max(len(i) for i in ids)
    lines.append(f"  {'id':<{width}}  {'x':>6} {'y':>6} {'w':>6} {'h':>6}  pane")
    for pane_id, lr in zip(ids, leaves):
        r = lr.rect
        lines.append(f"  {pane_id:<{width}}  {r.x:>6} {r.y:>6} {r.width:>6} {r.height:>6}  "
                     f"{_pane_summary(lr.leaf, when_evaluated)}")
        if verbose:
            o, leaf = lr.outer, lr.leaf
            lines.append(f"  {'':<{width}}  pane {o.width}x{o.height}+{o.x}+{o.y}, "
                         f"terminal {leaf.get('terminal')}, snap {leaf.get('snap')}, "
                         f"on_exit {leaf.get('on_exit')}, margin {leaf.get('margin')}")
    return "\n".join(lines)


def _format_result(result: opener.PaneResult, verbose: bool) -> str:
    if not result.ok or result.placement is None:
        return f"  {result.id}: FAILED: {result.error}"
    p = result.placement
    a = p.actual
    cells = f"  {p.cols}x{p.rows} cells" if p.cols is not None else ""
    state = "" if p.exact else "  (window manager gave a different size)"
    line = (f"  {result.id}: {result.terminal}  {a.x},{a.y} {a.width}x{a.height}{cells}{state}")
    if verbose:
        w = p.wanted
        line += (f"\n      wanted {w.x},{w.y} {w.width}x{w.height}; planned "
                 f"{p.planned.x},{p.planned.y} {p.planned.width}x{p.planned.height}; "
                 f"window id {result.window_id:#x}")
    return line


@dataclass
class _Unit:
    cfg: config.ConfigFile
    name: str
    monitor: monitors.Monitor
    resolved: dict
    leaves: list[geometry.LeafRect]
    area: geometry.Rect


class _Runner:
    def __init__(self, inv: Invocation, out: TextIO, err: TextIO,
                 detected: Optional[list[monitors.Monitor]], backend=None, popen=None,
                 work_areas: Optional[dict] = None):
        self.inv, self.out, self.err = inv, out, err
        self._backend, self._popen = backend, popen
        # Monitors handed in by a test: do not query X for the work area either.
        self._work: Optional[tuple[dict, str]] = (
            (work_areas or {}, "given") if (work_areas is not None or detected is not None) else None)
        self._monitors = detected
        self._files: dict[str, object] = {}
        self.failed = 0

    def monitors(self) -> list[monitors.Monitor]:
        if self._monitors is None:
            found, _source, errors = monitors.wait_for_monitors(self.inv.wait_monitors)
            for e in errors:
                print(f"warning: {e}", file=self.err)
            self._monitors = found
        return self._monitors

    def area(self, mon: monitors.Monitor, kind: str) -> geometry.Rect:
        """The rectangle to divide: the work area (monitor minus panels) or the full monitor."""
        full = workarea.monitor_rect(mon)
        if kind == "full":
            return full
        if self._work is None:
            self._work = workarea.detect(self.monitors())
            if self._work[1] == "none":
                print("note: the work area could not be determined; using the full monitor",
                      file=self.err)
        return self._work[0].get(mon.number, full)

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

    def units(self, when_eval) -> Iterator[_Unit]:
        """Every (layout, monitor) of every task, resolved and laid out.

        A task that cannot be used is reported and counted in `self.failed`;
        the others carry on.
        """
        for task in self.inv.tasks or [Task()]:
            try:
                cfg = self.load(task)
                names = self.select(cfg, task)
                spec = task.monitor or self.inv.default_monitor or "0"
                mons = monitors.resolve_many(spec, self.monitors(), cfg.monitors)
            except config.ConfigError as exc:
                for e in exc.errors:
                    self.error(e)
                self.failed += 1
                continue
            except monitors.MonitorError as exc:
                self.error(f"{task.source or config.default_config_path()}: {exc}")
                self.failed += 1
                continue
            for name in names:
                for mon in mons:
                    try:
                        resolved = config.resolve_layout(cfg, cfg.get(name), when_eval=when_eval)
                        area = self.area(mon, resolved["area"])
                        leaves = geometry.compute(resolved, area)
                    except config.ConfigError as exc:
                        for e in exc.errors:
                            self.error(e)
                        self.failed += 1
                        continue
                    except geometry.GeometryError as exc:
                        self.error(f"{cfg.source}: layout '{name}' on {_monitor_label(mon)}: {exc}")
                        self.failed += 1
                        continue
                    yield _Unit(cfg, name, mon, resolved, leaves, area)

    def dry_run(self) -> int:
        ok = 0
        when_eval = config.run_when if self.inv.eval_when else None
        for unit in self.units(when_eval):
            print(_format_layout(unit.name, unit.cfg.source, unit.monitor, unit.area, unit.leaves,
                                 verbose=self.inv.verbose, when_evaluated=self.inv.eval_when),
                  file=self.out)
            ok += 1
        if ok + self.failed > 1 or self.failed:
            print(f"dry run: {ok} ok, {self.failed} failed",
                  file=self.out if not self.failed else self.err)
        return 1 if self.failed else 0

    def open_windows(self) -> int:
        backend, reason = (self._backend, "") if self._backend else backends.choose()
        if backend is None:
            self.error(f"cannot open windows: {reason}")
            return 1
        ok = 0
        try:
            op = opener.Opener(backend, **({"popen": self._popen} if self._popen else {}))
            for unit in self.units(config.run_when):
                results = op.open_layout(unit.leaves)
                bad = [r for r in results if not r.ok]
                print(f'layout "{unit.name}" on {_monitor_label(unit.monitor)}: '
                      f"{len(results) - len(bad)} of {len(results)} windows opened",
                      file=self.out)
                for r in results:
                    print(_format_result(r, self.inv.verbose),
                          file=self.err if not r.ok else self.out)
                    for w in r.warnings:
                        print(f"  warning: {r.id}: {w}", file=self.err)
                if bad:
                    self.failed += 1
                else:
                    ok += 1
        finally:
            backend.disconnect()
        if ok + self.failed > 1 or self.failed:
            print(f"opened: {ok} ok, {self.failed} failed",
                  file=self.out if not self.failed else self.err)
        return 1 if self.failed else 0

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
         detected: Optional[list[monitors.Monitor]] = None, backend=None, popen=None,
         work_areas: Optional[dict] = None) -> int:
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

    runner = _Runner(inv, out, err, detected, backend, popen, work_areas)
    if inv.action == "list":
        return runner.list_layouts()
    if inv.dry_run:
        return runner.dry_run()
    return runner.open_windows()


if __name__ == "__main__":
    sys.exit(main())
