# -*- coding: utf-8 -*-
"""Parse CalculiX .dat time histories and compute TOF for one source.

Pipeline
    .dat  ->  per-increment displacement blocks (set SENSORS)
          ->  u_r(t) = u1*cos(theta_r) + u2*sin(theta_r),  theta_r = 2*pi*(r-1)/N
          ->  first-arrival detection (threshold = 0.05 * max|u_r|, >= 5 points)
          ->  CSV: source_id,receiver_id,tof_us,ur_max

The detection rule is copied verbatim from the Abaqus reference script
(abaqus/export_all_paths.py) so the two solvers are compared on equal terms.
"""
from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

THRESHOLD_RATIO = 0.05
MIN_POINTS = 5
N_SENSOR = 18

HDR = re.compile(
    r"displacements\s+\(vx,vy,vz\)\s+for\s+set\s+(\S+)\s+and\s+time\s+([-+0-9.Ee]+)",
    re.IGNORECASE,
)


def parse_sensor_sets(deck: Path) -> dict[str, int]:
    """SENSOR_xx -> node id (first node of the set)."""
    out: dict[str, int] = {}
    cur = None
    with deck.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            u = line.upper()
            if u.startswith("*NSET"):
                m = re.search(r"NSET=([A-Za-z0-9_]+)", line, re.IGNORECASE)
                cur = m.group(1) if m else None
                continue
            if line.startswith("*"):
                cur = None
                continue
            if cur and cur.upper().startswith("SENSOR_"):
                tok = line.strip().split(",")[0].strip()
                if tok.isdigit():
                    out[cur] = int(tok)
    return out


def parse_dat_history(dat: Path, set_name: str = "SENSORS") -> dict[int, list[tuple[float, float, float, float]]]:
    """node -> [(t, u1, u2, u3), ...] sorted by time."""
    hist: dict[int, list[tuple[float, float, float, float]]] = {}
    cur_time = None
    in_block = False
    with dat.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = HDR.search(line)
            if m:
                in_block = m.group(1).strip() == set_name
                cur_time = float(m.group(2))
                continue
            if not in_block:
                continue
            s = line.strip()
            if not s:
                continue
            parts = s.replace(",", " ").split()
            if len(parts) < 4 or not parts[0].isdigit():
                in_block = False
                continue
            node = int(parts[0])
            try:
                u1, u2, u3 = float(parts[1]), float(parts[2]), float(parts[3])
            except ValueError:
                in_block = False
                continue
            hist.setdefault(node, []).append((cur_time, u1, u2, u3))
    for v in hist.values():
        v.sort(key=lambda d: d[0])
    return hist


def detect_first_arrival(ur_data, threshold_ratio: float = THRESHOLD_RATIO,
                         min_points: int = MIN_POINTS):
    if not ur_data:
        return None, 0.0
    ur_max = max(abs(d[1]) for d in ur_data)
    if ur_max < 1e-15:
        return None, 0.0
    threshold = ur_max * threshold_ratio
    for i in range(1, len(ur_data)):
        if abs(ur_data[i][1]) > threshold:
            cnt = sum(1 for j in range(i, min(i + 10, len(ur_data)))
                      if abs(ur_data[j][1]) > threshold)
            if cnt >= min_points:
                return ur_data[i][0], ur_max
    return None, ur_max


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--deck", required=True, help="ccx .inp with SENSOR_xx nsets")
    ap.add_argument("--dat", required=True, help="ccx .dat")
    ap.add_argument("--source", type=int, required=True, help="source sensor id (1..18)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--set-name", default="SENSORS")
    args = ap.parse_args()

    deck = Path(args.deck)
    dat = Path(args.dat)
    sensors = parse_sensor_sets(deck)
    if len(sensors) != N_SENSOR:
        print(f"WARNING: found {len(sensors)} SENSOR_xx sets, expected {N_SENSOR}")

    hist = parse_dat_history(dat, args.set_name)
    print(f"parsed {len(hist)} nodes x {len(next(iter(hist.values()))) if hist else 0} time samples from {dat.name}")

    by_id: dict[int, str] = {}
    for name, node in sensors.items():
        try:
            by_id[node] = name
        except Exception:
            pass

    rows = []
    for rec in range(1, N_SENSOR + 1):
        if rec == args.source:
            continue
        name = f"SENSOR_{rec:02d}"
        node = sensors.get(name)
        if node is None:
            print(f"  {name}: missing")
            continue
        data = hist.get(node)
        if not data:
            print(f"  {name} (node {node}): no history")
            continue
        theta = 2.0 * math.pi * (rec - 1) / N_SENSOR
        ur = [(t, u1 * math.cos(theta) + u2 * math.sin(theta)) for t, u1, u2, _ in data]
        tof, ur_max = detect_first_arrival(ur)
        rows.append((args.source, rec, tof, ur_max, node))
        if tof is None:
            print(f"  {name} (node {node}): no arrival detected, ur_max={ur_max:.3e}")
        else:
            print(f"  {name} (node {node}): TOF={tof*1e6:.1f} us  ur_max={ur_max:.3e}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        f.write("source_id,receiver_id,tof_us,ur_max,node_id\n")
        for src, rec, tof, ur_max, node in rows:
            tof_us = "" if tof is None else f"{tof*1e6:.1f}"
            f.write(f"{src},{rec},{tof_us},{ur_max:.6e},{node}\n")
    print(f"wrote {out} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())