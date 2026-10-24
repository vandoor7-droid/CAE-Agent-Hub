# -*- coding: utf-8 -*-
"""Three-way TOF comparison: Abaqus reference / coarse mesh / fine mesh.

All inputs are CSV files with at least (source_id, receiver_id, tof_us); the
reference additionally carries path_mm and apparent_velocity_m_s.

    python compare_runs.py --src 1 --ref Z00_tof.csv \
        --coarse ../campaign/tof_ccx_all.csv \
        --fine ../campaign_fine/tof_ccx_all.csv --out compare_fine.md

The point of the table is the last two columns: does the fine mesh move towards
the Abaqus reference, i.e. is the coarse-mesh deviation explained by resolution?
"""
from __future__ import annotations

import argparse
import csv
import statistics
import sys
from pathlib import Path


def read_ref(path: Path) -> dict[tuple[int, int], dict]:
    out = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            out[(int(row["source_id"]), int(row["receiver_id"]))] = {
                "tof": float(row["tof_us"]),
                "path": float(row["path_mm"]),
                "v": float(row["apparent_velocity_m_s"]),
            }
    return out


def read_ccx(path: Path) -> dict[tuple[int, int], float]:
    out = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("tof_us"):
                out[(int(row["source_id"]), int(row["receiver_id"]))] = float(row["tof_us"])
    return out


def pct(value: float, base: float) -> str:
    return f"{100.0 * (value - base) / base:+.2f}%" if base else "—"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=int, default=1)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--coarse", required=True)
    ap.add_argument("--fine", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--fast-threshold", type=float, default=1000.0)
    args = ap.parse_args()

    ref = read_ref(Path(args.ref))
    coarse = read_ccx(Path(args.coarse))
    fine = read_ccx(Path(args.fine))

    rows = []
    for key, r in sorted(ref.items()):
        if key[0] != args.src:
            continue
        c, f = coarse.get(key), fine.get(key)
        if c is None or f is None:
            continue
        rows.append({"rec": key[1], "ref": r["tof"], "coarse": c, "fine": f,
                     "v": r["v"], "path": r["path"],
                     "fast": r["v"] >= args.fast_threshold})
    if not rows:
        print("no common rows", file=sys.stderr)
        return 2

    def summary(subset, label):
        if not subset:
            return f"{label}: n=0"
        dc = statistics.median(100.0 * abs(x["coarse"] - x["ref"]) / x["ref"] for x in subset)
        df = statistics.median(100.0 * abs(x["fine"] - x["ref"]) / x["ref"] for x in subset)
        return (f"{label}: n={len(subset)}  |Δ| 中位 粗网={dc:.2f}%  细网={df:.2f}%  "
                f"改善={dc - df:+.2f} 个百分点")

    fast = [r for r in rows if r["fast"]]
    slow = [r for r in rows if not r["fast"]]
    lines = [f"# 激励源 {args.src}：参考 / 粗网 / 2.5 mm 细网 TOF 三方对照", ""]
    lines.append(f"- 路径数：{len(rows)}（快轴 {len(fast)} / 慢轴 {len(slow)}）")
    lines.append("- " + summary(rows, "全部"))
    lines.append("- " + summary(fast, "快轴(v>=1000)"))
    lines.append("- " + summary(slow, "慢轴(v<1000)"))
    lines.append("")
    lines.append("| rec | 参考 TOF/us | 粗网 TOF/us | 粗网 Δ% | 细网 TOF/us | 细网 Δ% | "
                 "细−粗 Δ/us | v_ref m/s |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        lines.append(f"| {r['rec']} | {r['ref']:.1f} | {r['coarse']:.1f} | "
                     f"{pct(r['coarse'], r['ref'])} | {r['fine']:.1f} | "
                     f"{pct(r['fine'], r['ref'])} | {r['fine'] - r['coarse']:+.1f} | "
                     f"{r['v']:.0f} |")
    text = "\n".join(lines) + "\n"
    print("\n".join(lines[:6]))
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())