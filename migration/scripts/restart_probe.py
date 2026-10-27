# -*- coding: utf-8 -*-
"""Probe whether CalculiX *RESTART works for explicit dynamics.

Builds three decks from the pristine cantilever example:
  tA : 4 dynamic steps x 5 increments, *RESTART,WRITE in every step   (reference, 20 inc)
  tB : the first 2 steps only                                        (simulated interruption)
  tC : *RESTART,READ,STEP=2 + the remaining 2 steps                  (resume, 10 inc)

Then compares the final displacements of tA against tB+tC.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

EX = Path(__file__).resolve().parents[2] / "MCP" / "CalculiX" / "examples" / "cantilever.inp"
WORK = Path(r"D:\ccx_work\restart_probe")
CCX = r"D:\ccx_work\bin\ccx.exe"
DT = "1.e-7"
NINC = 5


def header(text: str) -> str:
    idx = text.index("*STEP")
    return text[:idx]


def step_block(n_inc: int, restart_write: bool) -> str:
    lines = [
        f"*STEP, INC={n_inc * 4}",
        "*DYNAMIC, DIRECT, EXPLICIT=2",
        f"{DT}, {n_inc}*{DT}".replace(f"{n_inc}*{DT}", f"{float(DT) * n_inc:.1e}"),
    ]
    if restart_write:
        lines.append("*RESTART, WRITE, FREQUENCY=1")
    lines += ["*CLOAD", "TIP, 3, -4.0", "*NODE PRINT, NSET=NALL", "U", "*END STEP", ""]
    return "\n".join(lines)


def read_last_block(dat: Path):
    text = dat.read_text(encoding="utf-8", errors="replace").splitlines()
    blocks = []
    cur = None
    for line in text:
        if "displacements" in line and "for set" in line:
            cur = {}
            blocks.append(cur)
            continue
        if cur is None:
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            cur[int(parts[0])] = (float(parts[1]), float(parts[2]), float(parts[3]))
        except ValueError:
            continue
    return blocks


def run(name: str) -> int:
    rc = subprocess.call([CCX, "-i", name], cwd=str(WORK),
                         stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    return rc


def read_times(dat: Path) -> list[float]:
    out = []
    for line in dat.read_text(encoding="utf-8", errors="replace").splitlines():
        if "for set" in line and " and time " in line:
            try:
                out.append(float(line.rsplit("time", 1)[1]))
            except ValueError:
                pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify", action="store_true",
                    help="CI mode: assert state equality and .dat time continuity")
    args = ap.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    src = EX.read_text(encoding="utf-8")
    head = header(src)

    (WORK / "tA.inp").write_text(head + "".join(step_block(NINC, True) for _ in range(4)), encoding="utf-8")
    (WORK / "tB.inp").write_text(head + "".join(step_block(NINC, True) for _ in range(2)), encoding="utf-8")
    (WORK / "tC.inp").write_text(
        "*RESTART, READ, STEP=2\n" + "".join(step_block(NINC, True) for _ in range(2)),
        encoding="utf-8",
    )

    for f in WORK.glob("t?"):
        if f.suffix in {".dat", ".rout", ".rin", ".sta", ".frd", ".cvg", ".12d"}:
            f.unlink()

    print("run tA ...", run("tA"), flush=True)
    print("run tB ...", run("tB"), flush=True)
    rout = WORK / "tB.rout"
    if not rout.exists():
        print("NO tB.rout produced -> restart writing failed for explicit dynamics")
        print((WORK / "tB.dat").read_text(encoding="utf-8", errors="replace")[:800])
        return 1
    rout.replace(WORK / "tC.rin")
    print("run tC ...", run("tC"), flush=True)

    a = read_last_block(WORK / "tA.dat")
    c = read_last_block(WORK / "tC.dat")
    print(f"tA blocks={len(a)}  tC blocks={len(c)}")
    if not a or not c:
        print("missing displacement blocks")
        return 1
    last_a, last_c = a[-1], c[-1]
    common = set(last_a) & set(last_c)
    diff = max((max(abs(last_a[n][i] - last_c[n][i]) for i in range(3)) for n in common), default=float("nan"))
    scale = max((abs(v) for d in last_a.values() for v in d), default=1.0)
    print(f"nodes compared={len(common)}  max|du|={diff:.3e} mm  (max|u|={scale:.3e})  ratio={diff / scale:.3e}")

    # The .dat history must continue on the absolute time axis after a restart,
    # otherwise merging segment histories would need per-segment offsets.
    tb, tc = read_times(WORK / "tB.dat"), read_times(WORK / "tC.dat")
    ok_time = bool(tb) and bool(tc) and abs(tc[0] - (tb[-1] + float(DT))) < 0.05 * float(DT)
    print(f"time axis: tB last={tb[-1]:.3e}  tC first={tc[0]:.3e}  "
          f"dt={float(DT):.1e}  continuous={ok_time}")

    if not args.verify:
        return 0
    ok_state = bool(common) and diff / scale < 1e-12
    print(f"verify: state_equal={ok_state}  time_continuous={ok_time}  "
          f"-> {'PASS' if ok_state and ok_time else 'FAIL'}")
    return 0 if ok_state and ok_time else 1


if __name__ == "__main__":
    raise SystemExit(main())
