# -*- coding: utf-8 -*-
"""Compare CalculiX TOF against the Abaqus reference for one (or more) sources.

Reference : tof/Z00_tof.csv  (source_id,receiver_id,tof_us,path_mm,apparent_velocity_m_s)
Candidate : parse_dat_history.py output (source_id,receiver_id,tof_us,ur_max,node_id)

Acceptance thresholds (from the migration plan):
    * single path : |delta| <= 5% target, <= 10% acceptable
    * group mean  : fast group (v_ref >= 1000 m/s) 1558 m/s +-10%; slow 721 +-10%
"""
from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path


def read_ref(path: Path) -> dict[tuple[int, int], dict]:
    out = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            key = (int(row["source_id"]), int(row["receiver_id"]))
            out[key] = {
                "tof": float(row["tof_us"]),
                "path": float(row["path_mm"]),
                "v": float(row["apparent_velocity_m_s"]),
            }
    return out


def read_ccx(path: Path) -> dict[tuple[int, int], float]:
    out = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if not row.get("tof_us"):
                continue
            key = (int(row["source_id"]), int(row["receiver_id"]))
            out[key] = float(row["tof_us"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True)
    ap.add_argument("--ccx", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--fast-threshold", type=float, default=1000.0)
    args = ap.parse_args()

    ref = read_ref(Path(args.ref))
    cand = read_ccx(Path(args.ccx))

    rows, missing = [], 0
    for key, r in sorted(ref.items()):
        t = cand.get(key)
        if t is None:
            missing += 1
            continue
        delta = t - r["tof"]
        rows.append({
            "src": key[0], "rec": key[1],
            "ref": r["tof"], "ccx": t, "d_us": delta,
            "d_pct": 100.0 * delta / r["tof"] if r["tof"] else float("nan"),
            "v": r["v"], "fast": r["v"] >= args.fast_threshold,
        })

    def stats(subset, label):
        if not subset:
            return f"{label}: n=0"
        pcts = [abs(x["d_pct"]) for x in subset]
        return (f"{label}: n={len(subset)}  |d| mean={statistics.mean(pcts):.2f}%  "
                f"median={statistics.median(pcts):.2f}%  max={max(pcts):.2f}%")

    fast = [r for r in rows if r["fast"]]
    slow = [r for r in rows if not r["fast"]]
    lines = []
    lines.append(f"# TOF 对照（参考 {Path(args.ref).name} vs {Path(args.ccx).name}）")
    lines.append("")
    lines.append(f"- 匹配路径：{len(rows)}；缺失：{missing}")
    lines.append("- " + stats(rows, "全部"))
    lines.append("- " + stats(fast, "快轴(v>=1000)"))
    lines.append("- " + stats(slow, "慢轴(v<1000)"))
    lines.append("")
    lines.append("| src | rec | 参考 TOF/us | ccx TOF/us | Δ/us | Δ% | v_ref m/s |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in rows:
        lines.append(f"| {r['src']} | {r['rec']} | {r['ref']:.1f} | {r['ccx']:.1f} | "
                     f"{r['d_us']:+.1f} | {r['d_pct']:+.2f}% | {r['v']:.0f} |")
    text = "\n".join(lines) + "\n"
    print("\n".join(lines[:6]))
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())