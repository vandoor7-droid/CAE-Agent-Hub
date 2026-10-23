# -*- coding: utf-8 -*-
"""Run the 18-source TOF campaign in parallel and merge the results.

Every source gets its own deck (single *BOUNDARY substitution) and job directory
entry, so the runs are independent. ccx is single-threaded, so the wall clock is
governed by memory (about 2.4 GB per worker) rather than by cores.

    python run_parallel.py --base Z00_coarse_tof.inp --work D:/ccx_work/z00/campaign \
        --jobs 6 --sources 1 2 3 ... 18
"""
from __future__ import annotations

import argparse
import math
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import parse_dat_history as pdh  # noqa: E402


def rewrite(text: str, src_set: str) -> str:
    return "\n".join(
        line.replace("SRC", src_set, 1) if line.startswith(("SRC, 1, 1,", "SRC, 2, 2,")) else line
        for line in text.splitlines()
    ) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--ccx", default=r"D:\ccx_work\bin\ccx.exe")
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--sources", type=int, nargs="+", default=list(range(1, 19)))
    args = ap.parse_args()

    base = Path(args.base)
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    text = base.read_text(encoding="utf-8")
    sensors = pdh.parse_sensor_sets(base)

    pending = []
    for src in args.sources:
        name = f"src{src:02d}"
        deck = work / f"{name}.inp"
        dat = work / f"{name}.dat"
        done_flag = work / f"{name}.done"
        if done_flag.exists() and dat.exists() and dat.stat().st_size > 0:
            print(f"[{name}] already done", flush=True)
            continue
        # a killed run leaves a partial .dat / restart file behind: never mistake
        # that for a finished source, and always clear it before restarting
        for suffix in (".dat", ".rout", ".rin", ".frd", ".sta", ".cvg", ".12d", ".stdout", ".done"):
            stale = work / f"{name}{suffix}"
            if stale.exists():
                try:
                    stale.unlink()
                except OSError:
                    pass
        deck.write_text(rewrite(text, f"SENSOR_{src:02d}"), encoding="utf-8")
        pending.append((src, name, deck))

    print(f"{len(pending)} sources to run, {args.jobs} in parallel", flush=True)
    running: list[tuple[int, str, subprocess.Popen, float]] = []
    done: list[int] = []
    queue = list(pending)
    while queue or running:
        while queue and len(running) < args.jobs:
            src, name, deck = queue.pop(0)
            log = (work / f"{name}.stdout").open("w", encoding="utf-8", errors="replace")
            p = subprocess.Popen([args.ccx, "-i", name], cwd=str(work),
                                 stdout=log, stderr=subprocess.STDOUT)
            running.append((src, name, p, time.time()))
            print(f"[{name}] started (pid {p.pid})", flush=True)
        time.sleep(5)
        still = []
        for src, name, p, t0 in running:
            rc = p.poll()
            if rc is None:
                still.append((src, name, p, t0))
            else:
                print(f"[{name}] rc={rc} in {time.time()-t0:.0f}s", flush=True)
                if rc == 0:
                    (work / f"{name}.done").write_text(
                        f"{time.strftime('%Y-%m-%dT%H:%M:%S')}\n", encoding="utf-8")
                    # the restart file is ~570 MB per segment; nothing left to resume
                    for suffix in (".rout", ".rin", ".frd"):
                        junk = work / f"{name}{suffix}"
                        if junk.exists():
                            try:
                                junk.unlink()
                            except OSError:
                                pass
                done.append(src)
        running = still

    merged = work / "tof_ccx_all.csv"
    rows_all = []
    for src in args.sources:
        dat = work / f"src{src:02d}.dat"
        if not dat.exists():
            continue
        hist = pdh.parse_dat_history(dat, "SENSORS")
        for rec in range(1, pdh.N_SENSOR + 1):
            if rec == src:
                continue
            node = sensors.get(f"SENSOR_{rec:02d}")
            data = hist.get(node) if node else None
            if not data:
                continue
            theta = 2.0 * math.pi * (rec - 1) / pdh.N_SENSOR
            ur = [(t, u1 * math.cos(theta) + u2 * math.sin(theta)) for t, u1, u2, _ in data]
            tof, ur_max = pdh.detect_first_arrival(ur)
            rows_all.append((src, rec, tof, ur_max, node))
    with merged.open("w", encoding="utf-8", newline="\n") as f:
        f.write("source_id,receiver_id,tof_us,ur_max,node_id\n")
        for src, rec, tof, ur_max, node in rows_all:
            f.write(f"{src},{rec},{'' if tof is None else f'{tof*1e6:.1f}'},{ur_max:.6e},{node}\n")
    print(f"merged {len(rows_all)} paths -> {merged}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())