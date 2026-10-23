# -*- coding: utf-8 -*-
"""Extract a displacement frame from a CalculiX .frd and rewrite it as a .dat block.

The hub result exporter reads nodal displacements from a .dat
("displacements (vx,vy,vz) for set ..." blocks). A CalculiX dynamic run keeps
that in the .frd instead, so this tool picks one frame (largest |u| by default)
and emits a single-block .dat the exporter can consume.

Usage:
    python frd_to_dat.py Z00_coarse_ccx.frd -o frame.dat [--frame N] [--time T]
"""
from __future__ import annotations

import argparse
from pathlib import Path

NODE_FIELD = slice(3, 13)
V1 = slice(13, 25)
V2 = slice(25, 37)
V3 = slice(37, 49)


def parse_frames(path: Path):
    frames: list[tuple[float, dict[int, tuple[float, float, float]]]] = []
    cur: dict[int, tuple[float, float, float]] | None = None
    time = 0.0
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("  100CL"):
                parts = line.split()
                try:
                    time = float(parts[2])
                except (IndexError, ValueError):
                    time = 0.0
                cur = {}
                continue
            if cur is None:
                continue
            if line.startswith(" -3"):
                frames.append((time, cur))
                cur = None
                continue
            if line.startswith(" -1") or line.startswith(" -2"):
                if line.startswith(" -1"):
                    try:
                        node = int(line[NODE_FIELD])
                        v = (float(line[V1]), float(line[V2]), float(line[V3]))
                    except ValueError:
                        continue
                    cur[node] = v
    return frames


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("frd")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--frame", type=int, default=-1, help="frame index (default: max |u|)")
    ap.add_argument("--time", default="")
    args = ap.parse_args()

    frames = parse_frames(Path(args.frd))
    if not frames:
        print("no frames found")
        return 1
    if args.frame >= 0:
        idx = min(args.frame, len(frames) - 1)
    else:
        idx = max(range(len(frames)),
                  key=lambda i: max((abs(x) for v in frames[i][1].values() for x in v), default=0.0))
    t, disp = frames[idx]
    umax = max((abs(x) for v in disp.values() for x in v), default=0.0)
    print(f"frames={len(frames)} picked=#{idx} time={t:.3e} nodes={len(disp)} umax={umax:.3e}")

    out = Path(args.out)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        f.write(f"\n                        S T E P       1\n\n")
        f.write(f"                                INCREMENT     {idx + 1}\n\n")
        tlabel = args.time if args.time else f"{t:.7E}"
        f.write(f" displacements (vx,vy,vz) for set NALL and time {tlabel}\n\n")
        for node in sorted(disp):
            vx, vy, vz = disp[node]
            f.write(f"{node:>10d} {vx: .6E} {vy: .6E} {vz: .6E}\n")
    print(f"wrote {out} ({out.stat().st_size/1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())