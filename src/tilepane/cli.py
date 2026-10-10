"""Command line entry point."""

from __future__ import annotations

import argparse
import sys

from . import __version__, doctor, monitors


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tilepane",
        description="Open terminal windows at precisely defined screen positions.",
    )
    p.add_argument("--version", action="version", version=f"tilepane {__version__}")
    p.add_argument("--doctor", action="store_true",
                   help="print environment info (session, monitors, terminals, backend)")
    p.add_argument("--monitors", action="store_true",
                   help="list monitors with numbers, names, sizes and positions")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.doctor:
        print(doctor.render(doctor.collect()))
        return 0

    if args.monitors:
        found, source, errors = monitors.detect()
        for err in errors:
            print(f"warning: {err}", file=sys.stderr)
        if not found:
            print("no monitors found", file=sys.stderr)
            return 1
        print(monitors.format_table(found))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
