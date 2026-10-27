# -*- coding: utf-8 -*-
"""Chunked CalculiX runner: one ccx process per *STEP, resumable after a kill.

Why not a single long run?  CalculiX only writes restart data at the END of a
step, and it does not record which step is complete in a file the driver can
trust (``.sta`` stays empty for explicit dynamics, ``.dat`` repeats the step
number but a partial step looks the same as a finished one).  Running one
process per step makes the completion marker trivial and exact: the process
exited with 0.

Layout in the work directory (``--name`` defaults to the deck stem):

    <name>_seg1.inp ... <name>_segn.inp     per-step decks (preamble + RESTART,READ)
    <name>.progress.json                    {"completed": k, "segments": n, ...}
    <name>_seg<k>.rout                      restart data written by segment k
    <name>_seg<k+1>.rin                     copy of it, read by segment k+1
    <name>_seg<k>.dat ...                   per-step time history
    <name>.dat                              merged history (absolute time continues)
    <name>.done                             only after the last segment succeeded

    python run_segments.py --deck D:/ccx_work/z00/Z00_coarse_tof8.inp \
        --work D:/ccx_work/z00/campaign --name src02        # resume if needed
    python run_segments.py ... --fresh                      # ignore checkpoints
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

CCX = r"D:\ccx_work\bin\ccx.exe"


def split_deck(text: str) -> tuple[str, list[str]]:
    """Split a segmented deck into (preamble, [segment chunks]).

    A chunk starts at the ``*AMPLITUDE`` block that belongs to the step (if
    any) and ends with ``*END STEP``.
    """
    lines = text.splitlines(keepends=True)
    steps = [i for i, l in enumerate(lines) if l.lstrip().upper().startswith("*STEP")]
    ends = [i for i, l in enumerate(lines) if l.lstrip().upper().startswith("*END STEP")]
    if not steps or len(steps) != len(ends):
        raise SystemExit("deck is not segmented: need one *END STEP per *STEP")

    starts: list[int] = []
    prev_end = -1
    for idx, s in enumerate(steps):
        j = s
        for k in range(prev_end + 1, s):
            if lines[k].lstrip().upper().startswith("*AMPLITUDE"):
                j = k
        starts.append(j)
        prev_end = ends[idx]

    preamble = "".join(lines[: starts[0]])
    chunks = [
        "".join(lines[starts[i]: ends[i] + 1]) for i in range(len(starts))
    ]
    return preamble, chunks


def read_progress(path: Path) -> dict:
    if not path.exists():
        return {"completed": 0}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"completed": 0}


def write_progress(path: Path, data: dict) -> None:
    data["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def cleanup_segment(work: Path, name: str, k: int, drop_rout: bool) -> None:
    """Remove throw-away files of segment k (1-based); optionally its .rout."""
    for suffix in (".frd", ".cvg", ".12d", ".sta", ".stdout", ".rin"):
        p = work / f"{name}_seg{k}{suffix}"
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass
    if drop_rout:
        p = work / f"{name}_seg{k}.rout"
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass


def merge_dats(work: Path, name: str, n_seg: int) -> int:
    merged = work / f"{name}.dat"
    tmp = merged.with_suffix(".dat.tmp")
    rows = 0
    with tmp.open("w", encoding="utf-8", newline="\n") as out:
        for k in range(1, n_seg + 1):
            part = work / f"{name}_seg{k}.dat"
            if not part.exists():
                raise SystemExit(f"missing {part.name}; cannot merge the history")
            out.write(part.read_text(encoding="utf-8", errors="replace"))
            rows += 1
    tmp.replace(merged)
    return rows


def run_source(deck: Path, work: Path, name: str, *, ccx: str = CCX,
               resume: bool = True, timeout: float = 0.0) -> int:
    text = deck.read_text(encoding="utf-8")
    preamble, chunks = split_deck(text)
    n_seg = len(chunks)
    work.mkdir(parents=True, exist_ok=True)
    prog = work / f"{name}.progress.json"
    state = read_progress(prog) if resume else {"completed": 0}
    if not resume:
        for k in range(1, n_seg + 1):
            cleanup_segment(work, name, k, drop_rout=True)
    done = int(state.get("completed", 0))
    if done >= n_seg and (work / f"{name}.done").exists():
        print(f"[{name}] already done ({n_seg}/{n_seg})", flush=True)
        return 0
    if done:
        print(f"[{name}] resuming at segment {done + 1}/{n_seg}", flush=True)
    else:
        print(f"[{name}] {n_seg} segments to run", flush=True)

    state.update({"segments": n_seg})
    write_progress(prog, state)

    for k in range(done + 1, n_seg + 1):
        seg_job = f"{name}_seg{k}"
        seg_inp = work / f"{seg_job}.inp"
        # *RESTART, READ must be the FIRST line of the deck: ccx then takes the
        # model from <job>.rin and only the remaining step definition is read
        # from the input file.
        if k == 1:
            parts = [preamble, chunks[k - 1]]
        else:
            parts = [f"*RESTART, READ, STEP={k - 1}\n", chunks[k - 1]]
        seg_inp.write_text("".join(parts), encoding="utf-8")

        if k > 1:
            src_rout = work / f"{name}_seg{k - 1}.rout"
            if not src_rout.exists():
                print(f"[{name}] segment {k - 1} left no .rout; cannot resume "
                      f"segment {k}", flush=True)
                return 2
            shutil.copyfile(src_rout, work / f"{seg_job}.rin")

        log = (work / f"{seg_job}.stdout").open("w", encoding="utf-8", errors="replace")
        t0 = time.time()
        proc = subprocess.Popen([ccx, "-i", seg_job], cwd=str(work),
                                stdout=log, stderr=subprocess.STDOUT)
        state.update({"active": k, "pid": proc.pid})
        write_progress(prog, state)
        try:
            rc = proc.wait(timeout=timeout or None)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            print(f"[{name}] segment {k} stopped by --timeout; checkpoint kept",
                  flush=True)
            return 3
        finally:
            log.close()
        dt = time.time() - t0
        if rc != 0:
            print(f"[{name}] segment {k} rc={rc} after {dt:.0f}s; checkpoint kept",
                  flush=True)
            return rc
        state.update({"completed": k, "segments": n_seg})
        state.pop("active", None)
        state.pop("pid", None)
        write_progress(prog, state)
        print(f"[{name}] segment {k}/{n_seg} ok in {dt:.0f}s", flush=True)
        # segment k's .rout is needed to resume into k+1, so keep it; drop older
        if k > 1:
            cleanup_segment(work, name, k - 1, drop_rout=True)

    merge_dats(work, name, n_seg)
    (work / f"{name}.done").write_text(time.strftime("%Y-%m-%dT%H:%M:%S") + "\n",
                                       encoding="utf-8")
    cleanup_segment(work, name, n_seg, drop_rout=True)
    for k in range(1, n_seg + 1):
        for suffix in (".dat", ".inp"):
            p = work / f"{name}_seg{k}{suffix}"
            if p.exists():
                p.unlink()
    print(f"[{name}] all {n_seg} segments done -> {name}.dat", flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--deck", required=True, help="segmented .inp")
    ap.add_argument("--work", required=True)
    ap.add_argument("--name", default="")
    ap.add_argument("--ccx", default=CCX)
    ap.add_argument("--fresh", action="store_true", help="ignore checkpoints and restart from 0")
    ap.add_argument("--timeout", type=float, default=0.0,
                    help="kill the current segment after N seconds (checkpoint kept)")
    args = ap.parse_args()
    deck = Path(args.deck)
    name = args.name or deck.stem
    return run_source(deck, Path(args.work), name, ccx=args.ccx,
                      resume=not args.fresh, timeout=args.timeout)


if __name__ == "__main__":
    sys.exit(main())
