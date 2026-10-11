"""Command line entry point."""

from __future__ import annotations

import json
import os
import random
import sys
from dataclasses import dataclass
from typing import Iterator, Optional, TextIO

from . import (__version__, backends, config, demo, docgen, doctor, geometry, manager,
               monitors, opener, state, workarea)
from .invocation import HELP, Invocation, Task, UsageError, parse


# State key source for a demo that was not saved to a file.
DEMO_SOURCE = "<demo>"


def _pane_summary(leaf: dict, when_evaluated: bool) -> str:
    if leaf.get("empty"):
        text = "(empty)"
    else:
        run = leaf.get("run")
        text = "(shell)" if run is None else "; ".join(run) if isinstance(run, list) else run
        if leaf.get("title"):
            text = f"[{leaf['title']}] {text}"
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
                         f"terminal {leaf.get('terminal')}, shell {leaf.get('shell')}, "
                         f"snap {leaf.get('snap')}, "
                         f"on_exit {leaf.get('on_exit')}, margin {leaf.get('margin')}")
    return "\n".join(lines)


def _format_result(result: opener.PaneResult, verbose: bool) -> str:
    if not result.ok or result.placement is None:
        return f"  {result.id}: FAILED: {result.error}"
    p = result.placement
    a = p.actual
    cells = f"  {p.cols}x{p.rows} cells" if p.cols is not None else ""
    state = "" if p.exact else "  (window manager gave a different size)"
    what = result.terminal if result.action == "opened" else "re-placed"
    line = (f"  {result.id}: {what}  {a.x},{a.y} {a.width}x{a.height}{cells}{state}")
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

    @property
    def key(self) -> manager.Key:
        return (os.path.abspath(self.cfg.source), self.name, self.monitor.name)


class _Runner:
    def __init__(self, inv: Invocation, out: TextIO, err: TextIO,
                 detected: Optional[list[monitors.Monitor]], backend=None, popen=None,
                 work_areas: Optional[dict] = None, store: Optional[state.StateStore] = None):
        self.inv, self.out, self.err = inv, out, err
        self._store = store
        self._backend, self._popen = backend, popen
        # Monitors handed in by a test: do not query X for the work area either.
        self._work: Optional[tuple[dict, str]] = (
            (work_areas or {}, "given") if (work_areas is not None or detected is not None) else None)
        self._monitors = detected
        self._files: dict[str, object] = {}
        self.failed = 0
        # Workspaces, read once a backend is up: the current one and how many.
        self._current_ws: Optional[int] = None
        self._ws_count: Optional[int] = None

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

    def _manager(self) -> tuple[Optional[manager.Manager], Optional[object]]:
        backend, reason = (self._backend, "") if self._backend else backends.choose()
        if backend is None:
            self.error(f"cannot reach the window system: {reason}")
            return None, None
        if not self._resolve_workspace(backend):
            backend.disconnect()
            return None, None
        op = opener.Opener(backend, lifetime=self.inv.lifetime,
                           **({"popen": self._popen} if self._popen else {}))
        return manager.Manager(backend, self._store or state.StateStore(), op), backend

    def _resolve_workspace(self, backend) -> bool:
        """Read the workspaces and check a --workspace number against them."""
        self._current_ws = backend.current_desktop()
        self._ws_count = backend.desktop_count()
        spec = self.inv.workspace
        if spec is None or spec in ("current", "all"):
            return True
        if self._current_ws is None:
            self.error(f"--workspace {spec}: the window manager does not report workspaces")
            return False
        if self._ws_count is not None and int(spec) > self._ws_count:
            self.error(f"--workspace {spec}: there are only {self._ws_count} workspaces")
            return False
        return True

    def workspace_for(self, layout_ws: Optional[int] = None, where: str = "") -> Optional[int]:
        """The workspace (0-based; None: every one, or none known) for a layout.

        --workspace wins; then the layout's own "workspace"; then the current one.
        """
        spec = self.inv.workspace
        if spec == "all":
            return None
        if spec is not None:
            return self._current_ws if spec == "current" else int(spec) - 1
        if layout_ws is None:
            return self._current_ws
        if self._current_ws is None:
            print(f"warning: {where}workspace {layout_ws}: the window manager does not report "
                  "workspaces; ignored", file=self.err)
            return None
        if self._ws_count is not None and layout_ws > self._ws_count:
            print(f"warning: {where}workspace {layout_ws} does not exist (there are "
                  f"{self._ws_count}); using the current one", file=self.err)
            return self._current_ws
        return layout_ws - 1

    def _unit_ws(self, unit: "_Unit") -> Optional[int]:
        return self.workspace_for(unit.resolved.get("workspace"), f'layout "{unit.name}": ')

    def _closed(self, mgr: manager.Manager, n: int) -> int:
        """Report windows the last close could not close; returns n."""
        if mgr.refused:
            ids = ", ".join(f"{x:#x}" for x in mgr.refused)
            self.error(f"{len(mgr.refused)} window(s) did not close ({ids}); close them by hand "
                       "or run the same --close again")
            self.failed += 1
        return n

    @staticmethod
    def _where(ws: Optional[int]) -> str:
        """' (workspace N)' for messages, when workspaces are in play."""
        return f" (workspace {ws + 1})" if ws is not None else ""

    def _report_unit(self, unit: _Unit, rep: manager.UnitReport, ws: Optional[int]) -> None:
        total = len(rep.results)
        print(f'layout "{unit.name}" on {_monitor_label(unit.monitor)}{self._where(ws)}: '
              f"{rep.opened} opened, {rep.replaced} re-placed"
              + (f", {rep.pruned} pruned" if rep.pruned else "")
              + (f", {len(rep.failed)} of {total} failed" if rep.failed else ""),
              file=self.out)
        for r in rep.results:
            print(_format_result(r, self.inv.verbose), file=self.err if not r.ok else self.out)
            for w in r.warnings:
                print(f"  warning: {r.id}: {w}", file=self.err)
        if rep.extra:
            print(f"  note: windows for panes that no longer exist: {', '.join(rep.extra)} "
                  "(--prune closes them)", file=self.out)

    def open_windows(self) -> int:
        mgr, backend = self._manager()
        if mgr is None:
            return 1
        ok = 0
        try:
            for unit in self.units(config.run_when):
                ws = self._unit_ws(unit)
                rep = mgr.open_unit(unit.key, unit.leaves, prune=self.inv.prune, workspace=ws)
                self._report_unit(unit, rep, ws)
                if rep.failed:
                    self.failed += 1
                else:
                    ok += 1
        finally:
            backend.disconnect()
        if ok + self.failed > 1 or self.failed:
            print(f"opened: {ok} ok, {self.failed} failed",
                  file=self.out if not self.failed else self.err)
        return 1 if self.failed else 0

    def toggle_windows(self) -> int:
        mgr, backend = self._manager()
        if mgr is None:
            return 1
        ok = 0
        try:
            for unit in self.units(config.run_when):
                ws = self._unit_ws(unit)
                if mgr.is_open(unit.key, ws):
                    n = self._closed(mgr, mgr.close(source=unit.key[0], layout=unit.name,
                                                    monitor=unit.monitor.name, workspace=ws))
                    print(f'layout "{unit.name}" on {_monitor_label(unit.monitor)}{self._where(ws)}: '
                          f"closed {n} window(s)", file=self.out)
                    ok += 1
                    continue
                rep = mgr.open_unit(unit.key, unit.leaves, prune=self.inv.prune, workspace=ws)
                self._report_unit(unit, rep, ws)
                if rep.failed:
                    self.failed += 1
                else:
                    ok += 1
        finally:
            backend.disconnect()
        return 1 if self.failed else 0

    def close_windows(self) -> int:
        mgr, backend = self._manager()
        if mgr is None:
            return 1
        tasks = self.inv.tasks
        try:
            if (len(tasks) == 1 and tasks[0].source is None and tasks[0].layouts == ["all"]):
                ws = self.workspace_for()
                n = self._closed(mgr, mgr.close(workspace=ws))
                print(f"closed {n} window(s){self._where(ws)}", file=self.out)
                return 1 if self.failed else 0
            for task in tasks:
                source = manager.source_path(task.source, config.default_config_path())
                names = list(dict.fromkeys(task.layouts)) or [None]
                spec = task.monitor or self.inv.default_monitor
                # A layout that names its workspace is closed there (unless
                # --workspace says otherwise), so the file is read when it can be.
                try:
                    cfg = self.load(task)
                except config.ConfigError:
                    cfg = None
                if cfg is not None and names == [None] and self.inv.workspace is None:
                    names = cfg.names()
                try:
                    if spec:
                        cfg = self.load(task)
                        mons = [m.name for m in monitors.resolve_many(spec, self.monitors(), cfg.monitors)]
                    else:
                        mons = [None]
                except config.ConfigError as exc:
                    for e in exc.errors:
                        self.error(e)
                    self.failed += 1
                    continue
                except monitors.MonitorError as exc:
                    self.error(f"{source}: {exc}")
                    self.failed += 1
                    continue
                for name in names:
                    lay = cfg.get(name) if cfg is not None and name is not None else None
                    layout_ws = None
                    if lay is not None:
                        layout_ws = lay.get("workspace", cfg.defaults.get("workspace"))
                    ws = self.workspace_for(layout_ws, f'layout "{name}": ')
                    count = sum(self._closed(mgr, mgr.close(source=source, layout=name, monitor=m,
                                                            workspace=ws))
                                for m in mons)
                    label = f'layout "{name}"' if name else f"all layouts of {source}"
                    where = (f" on {', '.join(mons)}" if mons != [None] else "") + self._where(ws)
                    print(f"{label}{where}: closed {count} window(s)" if count
                          else f"{label}{where}: nothing was open", file=self.out)
        finally:
            backend.disconnect()
        return 1 if self.failed else 0

    def _demo_layouts(self, seed: str) -> tuple[list[tuple[monitors.Monitor, geometry.Rect]], dict]:
        """One random layout per target monitor, as the text of a configuration file."""
        rng = random.Random(seed)
        spec = self.inv.default_monitor or "0"
        mons = monitors.resolve_many(spec, self.monitors(), {})
        placed, layouts = [], []
        for mon in mons:
            area = self.area(mon, "work")
            name = "demo" if len(mons) == 1 else f"demo-{mon.number}"
            try:
                layouts.append(demo.build(rng, area.width, area.height, panes=self.inv.demo_panes,
                                          name=name, seed=seed))
            except demo.DemoError as exc:
                self.error(f"--demo on {_monitor_label(mon)}: {exc}")
                self.failed += 1
                continue
            placed.append((mon, area))
        if len(layouts) == 1:
            return placed, layouts[0]
        head = {k: layouts[0][k] for k in ("$schema", "version")} if layouts else {}
        body = [{k: v for k, v in lay.items() if k not in ("$schema", "version")} for lay in layouts]
        return placed, {**head, "layouts": body}

    def demo(self) -> int:
        seed = self.inv.seed if self.inv.seed is not None else str(random.SystemRandom().randrange(10**6))
        print(f"demo: seed {seed} (repeat it with --seed {seed})", file=self.out)
        try:
            placed, data = self._demo_layouts(seed)
        except monitors.MonitorError as exc:
            self.error(f"--demo: {exc}")
            return 1
        if not placed:
            return 1
        text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        if self.inv.save:
            try:
                with open(self.inv.save, "w", encoding="utf-8") as fh:
                    fh.write(text)
            except OSError as exc:
                self.error(f"--save {self.inv.save}: {exc.strerror or exc}")
                return 1
            print(f"demo: saved to {self.inv.save} (edit it, then open it with "
                  f"tilepane {self.inv.save})", file=self.out)
        # Through the normal loader, so a demo is an ordinary layout in every respect.
        source = os.path.abspath(self.inv.save) if self.inv.save else DEMO_SOURCE
        cfg = config.load_text(text, source, strict=True)
        units = []
        for (mon, area), lay in zip(placed, cfg.layouts):
            resolved = config.resolve_layout(cfg, lay)
            units.append(_Unit(cfg, lay["name"], mon, resolved, geometry.compute(resolved, area),
                               area))
        label = f"--demo --seed {seed}"
        if self.inv.dry_run:
            for unit in units:
                print(_format_layout(unit.name, label, unit.monitor, unit.area, unit.leaves,
                                     verbose=self.inv.verbose, when_evaluated=False),
                      file=self.out)
            return 1 if self.failed else 0

        mgr, backend = self._manager()
        if mgr is None:
            return 1
        try:
            for unit in units:
                key = (source, unit.name, unit.monitor.name)
                # A new demo replaces the previous one on the same monitor and workspace.
                ws = self.workspace_for()
                self._closed(mgr, mgr.close(source=DEMO_SOURCE, monitor=unit.monitor.name,
                                            workspace=ws))
                self._closed(mgr, mgr.close(source=source, layout=unit.name,
                                            monitor=unit.monitor.name, workspace=ws))
                rep = mgr.open_unit(key, unit.leaves, workspace=ws)
                self._report_unit(unit, rep, ws)
                if rep.failed:
                    self.failed += 1
        finally:
            backend.disconnect()
        return 1 if self.failed else 0

    def edit(self, open_browser=None) -> int:
        from .editor import server as editor_server

        task = self.inv.tasks[0] if self.inv.tasks else Task()
        path = os.path.abspath(task.source or config.default_config_path())
        if os.path.isdir(path):
            self.error(f"{path} is a directory")
            return 1

        def monitors_now() -> list[dict]:
            found = self.monitors()
            work = {m.number: self.area(m, "work") for m in found}
            return editor_server.monitor_list(found, work)

        def workspace_count() -> Optional[int]:
            backend, _reason = (self._backend, "") if self._backend else backends.choose()
            if backend is None:
                return None
            try:
                return backend.desktop_count()
            except Exception:  # noqa: BLE001 - the editor works without it
                return None
            finally:
                if backend is not self._backend:
                    backend.disconnect()

        try:
            srv = editor_server.EditorServer(path, monitors_now, workspaces=workspace_count)
        except OSError as exc:
            self.error(f"cannot start the editor: {exc}")
            return 1
        exists = os.path.exists(path)
        print(f"tilepane editor for {path}" + ("" if exists else " (new file; written when you save)"),
              file=self.out)
        print(f"  {srv.url}", file=self.out)
        print("  It stops when you close the tab, or with Ctrl+C.", file=self.out)
        self.out.flush()
        if not self.inv.no_browser:
            import webbrowser
            (open_browser or webbrowser.open)(srv.url)
        try:
            reason = srv.serve()
        except KeyboardInterrupt:
            reason = "interrupted"
        print(f"tilepane editor stopped ({reason})", file=self.out)
        return 0

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
         work_areas: Optional[dict] = None, store: Optional[state.StateStore] = None) -> int:
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

    runner = _Runner(inv, out, err, detected, backend, popen, work_areas, store)
    if inv.action == "list":
        return runner.list_layouts()
    if inv.action == "close":
        return runner.close_windows()
    if inv.action == "toggle":
        return runner.toggle_windows()
    if inv.action == "demo":
        return runner.demo()
    if inv.action == "edit":
        return runner.edit()
    if inv.dry_run:
        return runner.dry_run()
    return runner.open_windows()


if __name__ == "__main__":
    sys.exit(main())
