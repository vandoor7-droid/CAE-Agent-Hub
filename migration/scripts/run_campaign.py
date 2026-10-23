# -*- coding: utf-8 -*-
"""Run the 18-source TOF campaign on a converted CalculiX deck.

For each source sensor k it rewrites the boundary condition of the base deck
(one text substitution on the *BOUNDARY card), runs ccx, parses the .dat and
appends the 17 receiver TOFs to a merged CSV.

Usage:
    python run_campaign.py --inp Z00_coarse_ccx.inp --work D:\ccx_work\z00\campaign \
        --sources 1 2 3 --dt 1.2e-7 --time 3.e-4
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import parse_dat_history as pdh


def rewrite_src(base_text: str, src_set: str) -> str:
    out = []
    for line in base_text.splitlines():
        if line.startswith("SRC, 1, 1,") or line.startswith("SRC, 2, 2,"):
            out.append(line.replace("SRC", src_set, 1))
        else:
            out.append(line)
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inp", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--ccx", default=r"D:\ccx_work\bin\ccx.exe")
    ap.add_argument("--sources", type=int, nargs="+", default=list(range(1, 19)))
    ap.add_argument("--merged", default="tof_ccx_all.csv")
    args = ap.parse_args()

    base = Path(args.inp)
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    text = base.read_text(encoding="utf-8")
    sensors = pdh.parse_sensor_sets(base)
    merged = work / args.merged
    if not merged.exists():
        merged.write_text("source_id,receiver_id,tof_us,ur_max,node_id\n", encoding="utf-8")

    for src in args.sources:
        name = f"src{src:02d}"
        deck = work / f"{name}.inp"
        if not deck.exists():
            deck.write_text(rewrite_src(text, f"SENSOR_{src:02d}"), encoding="utf-8")
        dat = work / f"{name}.dat"
        t0 = time.time()
        if not dat.exists() or dat.stat().st_size == 0:
            cmd = [args.ccx, "-i", name]
            with (work / f"{name}.stdout").open("w", encoding="utf-8", errors="replace") as log:
                rc = subprocess.call(cmd, cwd=str(work), stdout=log, stderr=subprocess.STDOUT)
            print(f"[{name}] ccx rc={rc} in {time.time()-t0:.0f}s", flush=True)
            if rc != 0:
                print(f"[{name}] FAILED, see {name}.stdout", flush=True)
                continue
        # parse & append
        hist = pdh.parse_dat_history(dat, "SENSORS")
        rows = []
        for rec in range(1, pdh.N_SENSOR + 1):
            if rec == src:
                continue
            node = sensors.get(f"SENSOR_{rec:02d}")
            data = hist.get(node) if node else None
            if not data:
                continue
            import math
            theta = 2.0 * math.pi * (rec - 1) / pdh.N_SENSOR
            ur = [(t, u1 * math.cos(theta) + u2 * math.sin(theta)) for t, u1, u2, _ in data]
            tof, ur_max = pdh.detect_first_arrival(ur)
            rows.append(f"{src},{rec},{'' if tof is None else f'{tof*1e6:.1f}'},{ur_max:.6e},{node}\n")
        with merged.open("a", encoding="utf-8", newline="\n") as f:
            f.writelines(rows)
        print(f"[{name}] {len(rows)} paths in {time.time()-t0:.0f}s", flush=True)

    print(f"merged -> {merged}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())