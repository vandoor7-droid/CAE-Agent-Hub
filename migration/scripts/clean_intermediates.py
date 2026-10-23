# -*- coding: utf-8 -*-
"""Delete the throw-away artifacts a CalculiX run leaves behind.

CalculiX jobs write large intermediate files next to the results:

    *.rout  *.rin   restart / checkpoint files (hundreds of MB to GB)
    *.frd           field output (tens to hundreds of MB)
    *.inp           per-source decks (25 MB each; regenerable from the base deck)
    *.sta *.cvg *.12d *.stdout   solver bookkeeping (small)

What is *kept* by default: ``*.dat`` (the time histories the TOF parser reads),
``*.done`` markers and every ``*.csv``/``*.md`` report.

Typical use:

    python clean_intermediates.py D:/ccx_work/z00/campaign            # dry run
    python clean_intermediates.py D:/ccx_work/z00/campaign --apply    # delete

Dry run is the default on purpose: check the list and the total size first.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

DROP_SUFFIXES = (
    ".rout", ".rin", ".frd", ".inp", ".sta", ".cvg", ".12d", ".stdout",
    ".nam", ".log", ".12da",
)
KEEP_SUFFIXES = (".dat", ".done", ".csv", ".md")


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024 or unit == "GB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("work", nargs="+", help="directories to clean")
    ap.add_argument("--apply", action="store_true", help="actually delete")
    ap.add_argument("--keep", action="append", default=[],
                    help="extra suffix to keep, e.g. --keep .stdout")
    args = ap.parse_args()

    keep = set(KEEP_SUFFIXES) | set(args.keep)
    victims: list[Path] = []
    for work in args.work:
        root = Path(work)
        if not root.is_dir():
            print(f"skip (not a directory): {root}", file=sys.stderr)
            continue
        for p in sorted(root.rglob("*")):
            if not p.is_file():
                continue
            suffix = p.suffix.lower()
            if suffix in keep:
                continue
            if suffix in DROP_SUFFIXES:
                victims.append(p)

    total = sum(p.stat().st_size for p in victims)
    by_suffix: dict[str, list[int]] = {}
    for p in victims:
        slot = by_suffix.setdefault(p.suffix.lower(), [0, 0])
        slot[0] += 1
        slot[1] += p.stat().st_size

    for suffix, (count, size) in sorted(by_suffix.items()):
        print(f"{suffix:8s} {count:4d} files  {human(size)}")
    print(f"total: {len(victims)} files, {human(total)}")

    if not args.apply:
        print("dry run — pass --apply to delete")
        return 0
    deleted = 0
    for p in victims:
        try:
            p.unlink()
            deleted += 1
        except OSError as exc:
            print(f"failed: {p}: {exc}", file=sys.stderr)
    print(f"deleted {deleted}/{len(victims)} files, freed {human(total)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())