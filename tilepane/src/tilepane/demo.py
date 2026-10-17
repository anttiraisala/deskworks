"""`--demo`: a random layout with fun commands (SPEC.md section 10).

Pure apart from `shutil.which`: the caller passes the random generator, the
area to divide and the lookup, so a seed reproduces the same layout on the same
machine. Every command in the pool has a fallback that needs nothing but
`/bin/sh` and `/proc`, so the demo works without installing anything.
"""

from __future__ import annotations

import random
import re
import shlex
import shutil
from dataclasses import dataclass
from typing import Callable, Optional

SCHEMA_URL = ("https://raw.githubusercontent.com/anttiraisala/tilepane/master/"
              "src/tilepane/tilepane.schema.json")
DEFAULT_COUNTS = (3, 4, 5, 6)
MAX_PANES = 12
# Smallest pane the generator makes, in pixels (before margins).
MIN_W = 240
MIN_H = 120
PANE_ASPECT = 1.3


class DemoError(ValueError):
    """The demo cannot be built (too many panes for the monitor, bad option value)."""


# Fallbacks (title, sh script): plain loops over /proc and coreutils.
_CLOCK = 'clock', 'while :; do clear; date "+%A %d %B %Y%n%n    %T"; sleep 1; done'
_LOAD = 'load', 'while :; do clear; echo "load average:"; cat /proc/loadavg; sleep 1; done'
_LOG = 'load log', ('while :; do printf "%s  load %s\\n" "$(date +%T)" '
        '"$(cut -d" " -f1-3 /proc/loadavg)"; sleep 2; done')
_MEM = 'memory', 'while :; do clear; head -n 5 /proc/meminfo; sleep 2; done'
_FILES = 'files', 'while :; do clear; ls -la; sleep 2; done'
_DISK = 'disk', 'while :; do clear; df -h; sleep 5; done'
_RAIN = 'rain', ('cols=$(tput cols 2>/dev/null || echo 80); while :; do '
         'tr -dc "01 " </dev/urandom | head -c "$cols"; echo; sleep 0.05; done')
_UPTIME = 'uptime', ('while :; do clear; uname -srm; echo; echo "up $(cut -d. -f1 /proc/uptime) s"; '
           'sleep 15; done')


@dataclass(frozen=True)
class Entry:
    title: str
    command: str              # run as given when every binary in `needs` is found
    needs: tuple[str, ...]
    fallback: tuple[str, str]  # (title, sh script)
    sh: bool = False          # `command` uses sh syntax and is wrapped in sh -c
    streams: bool = False     # keeps running; if it exits within a second, use the fallback


POOL: tuple[Entry, ...] = (
    Entry("top", "top", ("top",), _LOAD),
    Entry("htop", "htop", ("htop",), _LOAD),
    Entry("clock", "watch -n1 date", ("watch",), _CLOCK),
    Entry("files", "watch -n2 'ls -la'", ("watch",), _FILES),
    Entry("vmstat", "vmstat 1", ("vmstat",), _MEM),
    Entry("load", "watch -n1 'cat /proc/loadavg'", ("watch",), _LOAD),
    Entry("disk", "watch -n5 df -h", ("watch",), _DISK),
    Entry("journal", "journalctl -f", ("journalctl",), _LOG, streams=True),
    Entry("kernel log", "dmesg -w", ("dmesg",), _LOG, streams=True),
    Entry("ping", "ping 1.1.1.1", ("ping",), _LOG, streams=True),
    Entry("big clock", "watch -t -n1 'date +%T | figlet'", ("watch", "figlet"), _CLOCK),
    Entry("matrix", "cmatrix", ("cmatrix",), _RAIN),
    Entry("train", "while :; do sl -e; sleep 1; done", ("sl",), _RAIN, sh=True),
    Entry("fortune", "while :; do clear; fortune | cowsay; sleep 15; done",
          ("fortune", "cowsay"), _UPTIME, sh=True),
    Entry("calendar", "cal", ("cal",), ("month", 'date "+%B %Y"')),
    Entry("sensors", "watch -n2 sensors", ("watch", "sensors"), _LOAD, streams=True),
    Entry("gpu", "nvidia-smi -l 1", ("nvidia-smi",), _LOAD, streams=True),
)


def _sh(script: str) -> str:
    """Run a sh script whatever the user's login shell is (fish, zsh, ...)."""
    return "sh -c " + shlex.quote(script)


def pane(entry: Entry, which: Callable[[str], Optional[str]] = shutil.which) -> dict:
    """The leaf for `entry` on this machine: its title and command."""
    fb_title, fb_script = entry.fallback
    if not all(which(b) for b in entry.needs):
        return {"run": _sh(fb_script), "title": fb_title}
    if entry.streams:
        # A command that is installed but cannot run here (dmesg is restricted,
        # journalctl needs a group, ping needs a network) exits at once.
        run = _sh(f's=$(date +%s); {entry.command}; '
                  f'if [ $(( $(date +%s) - s )) -le 1 ]; then '
                  f'echo "[demo] {entry.title} is not available here"; {fb_script}; fi')
    else:
        run = _sh(entry.command) if entry.sh else entry.command
    return {"run": run, "title": entry.title}


def pick_panes(rng: random.Random, n: int,
               which: Callable[[str], Optional[str]] = shutil.which) -> list[dict]:
    """n leaves, all running different commands while the pool lasts.

    Missing commands share fallbacks, so the pool is deduplicated by what the
    panes would actually run on this machine.
    """
    order = list(POOL)
    rng.shuffle(order)
    unique: dict[str, dict] = {}
    for entry in order:
        leaf = pane(entry, which)
        unique.setdefault(leaf["run"], leaf)
    distinct = list(unique.values())
    return [dict(distinct[i % len(distinct)]) for i in range(n)]


def _split_point(rng: random.Random, size: int, share: float) -> str:
    """An `at` value at `share` of `size`: mostly percentages, sometimes pixels or from the end."""
    style = rng.random()
    if style < 0.6:
        return f"{round(share * 100)}%"
    if style < 0.75:
        return f"-{100 - round(share * 100)}%"
    px = round(share * size)
    if style < 0.9:
        return f"{px}px"
    return f"-{size - px}px"


def _at_pixels(at: str, size: int) -> int:
    m = re.fullmatch(r"(-?)(\d+)(%|px)", at)
    assert m, at
    value = int(m.group(2)) * size / 100 if m.group(3) == "%" else int(m.group(2))
    return round(size - value if m.group(1) else value)


def _need(count: int, other: int, low: int, low_other: int) -> Optional[int]:
    """Length a part needs to hold `count` panes when its other side is `other` long."""
    across = other // low_other
    if across == 0:
        return None
    return -(-count // across) * low


def _tree(rng: random.Random, n: int, width: int, height: int) -> dict:
    """A random split tree with n leaves (leaves are filled in later) for a width x height area."""
    if n == 1:
        return {}
    # (direction, panes in a, length a needs, length b needs) for every split that fits.
    choices = []
    for direction, size, other, low, low_other in (("columns", width, height, MIN_W, MIN_H),
                                                   ("rows", height, width, MIN_H, MIN_W)):
        for first in range(1, n):
            need_a = _need(first, other, low, low_other)
            need_b = _need(n - first, other, low, low_other)
            if need_a is not None and need_b is not None and need_a + need_b <= size:
                choices.append((direction, first, need_a, need_b))
    if not choices:
        raise DemoError(f"{n} panes do not fit in {width}x{height}")
    directions = sorted({c[0] for c in choices})
    if len(directions) == 2:
        # Prefer cutting the long side; terminals look best somewhat wider than tall.
        wide = width >= PANE_ASPECT * height
        long_side, short_side = ("columns", "rows") if wide else ("rows", "columns")
        direction = long_side if rng.random() < 0.75 else short_side
    else:
        direction = directions[0]
    _, first, need_a, need_b = rng.choice([c for c in choices if c[0] == direction])
    size = width if direction == "columns" else height

    share = first / n + rng.uniform(-0.15, 0.15)
    # Both sides must hold their panes; the spec asks for 20-80 %.
    lo, hi = max(0.2, need_a / size), min(0.8, 1 - need_b / size)
    if lo > hi:
        lo, hi = need_a / size, 1 - need_b / size
    share = min(max(share, lo), hi)
    at = _split_point(rng, size, share)
    cut = _at_pixels(at, size)
    if cut < need_a or size - cut < need_b:
        # A rounded percentage can land just short of the room the panes need.
        at = f"{round(share * size)}px"
        cut = _at_pixels(at, size)
    if direction == "columns":
        a, b = _tree(rng, first, cut, height), _tree(rng, n - first, width - cut, height)
    else:
        a, b = _tree(rng, first, width, cut), _tree(rng, n - first, width, height - cut)
    return {"dir": direction, "at": at, "a": a, "b": b}


def _fill(node: dict, leaves: list[dict]) -> dict:
    if not node:
        return leaves.pop(0)
    return {**node, "a": _fill(node["a"], leaves), "b": _fill(node["b"], leaves)}


def build(rng: random.Random, width: int, height: int, *, panes: Optional[int] = None,
          name: str = "demo", seed: object = None,
          which: Callable[[str], Optional[str]] = shutil.which) -> dict:
    """A flat single-layout configuration for a width x height area."""
    n = panes or rng.choice(DEFAULT_COUNTS)
    if not 1 <= n <= MAX_PANES:
        raise DemoError(f"the demo takes 1 to {MAX_PANES} panes, not {n}")
    margin = rng.randint(2, 8) * 2
    tree = _tree(rng, n, width, height)
    leaves = pick_panes(rng, n, which)
    split = _fill(tree, leaves) if tree else leaves[0]
    layout = {
        "$schema": SCHEMA_URL,
        "version": 1,
        "name": name,
        "description": "made by tilepane --demo" + (f" --seed {seed}" if seed is not None else ""),
        "margin": margin,
        "on_exit": "keep",
        "split": split,
    }
    return layout


def parse_duration(text: str) -> float:
    """'30s', '2m', '1h' or a bare number of seconds."""
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(s|m|h)?\s*", text)
    if not m or float(m.group(1)) <= 0:
        raise DemoError(f"--for needs a duration such as 30s, 5m or 1h, got '{text}'")
    return float(m.group(1)) * {"s": 1, "m": 60, "h": 3600, None: 1}[m.group(2)]
