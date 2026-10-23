# -*- coding: utf-8 -*-
"""Convert the Abaqus-exported Z00 deck into a flat CalculiX deck.

Input  : an Abaqus .inp with *Part / *Assembly / *Instance structure
Output : a flat ccx deck (nodes, elements, nsets, material, amplitude, one
         dynamic step) that keeps the original node/element labels.

The step is rewritten for CalculiX:
    *DYNAMIC, DIRECT, EXPLICIT=2    <dt>, <total time>
    *BOUNDARY, AMPLITUDE=...        BC_REGION_01, 1/2
    *NODE PRINT, NSET=SENSORS       U   (every increment -> .dat time history)
    *NODE FILE,  NSET=SENSORS       U   (field output, throttled)

Usage:
    python make_ccx_inp.py <abaqus.inp> <out.inp> [--dt 5e-7] [--time 3e-4]
                           [--src BC_REGION_01] [--amp 1e-4]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

KEYWORDS_KEEP_IN_PART = {"NODE", "ELEMENT"}


def kw(line: str) -> str:
    body = line[1:].split(",")[0].strip().upper()
    return re.sub(r"\s+", " ", body)


def params(line: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in line[1:].split(",")[1:]:
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip().upper()] = v.strip()
        elif part.strip():
            out[part.strip().upper()] = ""
    return out


def read_blocks(path: Path):
    """Yield (keyword_line, [data lines]) blocks, streaming."""
    cur_kw = None
    cur_data: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("*"):
                if cur_kw is not None:
                    yield cur_kw, cur_data
                cur_kw, cur_data = line.rstrip("\n"), []
            else:
                if cur_kw is not None:
                    cur_data.append(line.rstrip("\n"))
    if cur_kw is not None:
        yield cur_kw, cur_data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("inp")
    ap.add_argument("out")
    ap.add_argument("--dt", default="5.e-7")
    ap.add_argument("--time", default="3.e-4")
    ap.add_argument("--segments", type=int, default=1,
                    help="split the run into N *DYNAMIC steps with *RESTART,WRITE (checkpointing)")
    ap.add_argument("--src", default="SRC")
    ap.add_argument("--amp", default="AMP_50K_5CYC")
    ap.add_argument("--amp-mag", default="1.e-4")
    ap.add_argument("--no-auto-sensors", action="store_true")
    ap.add_argument("--frd-mode", default="none", choices=["none", "sensors", "all"])
    ap.add_argument("--print-freq", default="")
    ap.add_argument("--file-freq", default="60")
    args = ap.parse_args()

    src = Path(args.inp)
    out = Path(args.out)

    node_lines: list[str] = []
    elem_lines: list[str] = []
    part_nsets: list[tuple[str, list[str]]] = []
    asm_nsets: list[tuple[str, list[str]]] = []
    amplitude: list[str] = []
    material: list[str] = []
    material_name = "WOOD"
    n_nodes = n_elems = 0
    in_part = False
    in_assembly = False

    for header, data in read_blocks(src):
        k = kw(header)
        p = params(header)
        if k == "PART":
            in_part = True
            continue
        if k == "END PART":
            in_part = False
            continue
        if k == "ASSEMBLY":
            in_assembly = True
            continue
        if k == "END ASSEMBLY":
            in_assembly = False
            continue
        if k == "INSTANCE" or k == "END INSTANCE":
            continue
        if in_part and k == "NODE":
            node_lines = data
            n_nodes = len(data)
            continue
        if in_part and k == "ELEMENT":
            elem_lines = data
            n_elems = len(data)
            continue
        if in_part and k == "NSET":
            name = p.get("NSET", "SET")
            if name.upper() == "SET-1":
                continue
            part_nsets.append((name, ("GENERATE" if "GENERATE" in p else "LIST"), data))
            continue
        if in_part and k in ("ELSET", "SOLID SECTION", "SHELL SECTION"):
            if k == "SOLID SECTION":
                material_name = p.get("MATERIAL", material_name)
            continue
        if in_assembly and k == "NSET":
            if any(x.strip() for x in data):
                asm_nsets.append((p.get("NSET", "SET"), "LIST", data))
            continue
        if k == "AMPLITUDE":
            amplitude = data
            continue
        if k == "MATERIAL":
            material = [header] + data
            material_name = p.get("NAME", material_name)
            continue

    if not node_lines or not elem_lines:
        print("ERROR: no *NODE / *ELEMENT found", file=sys.stderr)
        return 2

    # material block: *Material (+ *Density/*Elastic data follow as separate blocks)
    # Re-scan to collect the material sub-cards right after *Material.
    mat_blocks: list[tuple[str, list[str]]] = []
    seen_mat = False
    for header, data in read_blocks(src):
        k = kw(header)
        if k == "MATERIAL":
            seen_mat = True
            mat_blocks.append((header, data))
            continue
        if seen_mat:
            if k in ("DENSITY", "ELASTIC", "PLASTIC", "EXPANSION", "CONDUCTIVITY", "SPECIFIC HEAT"):
                mat_blocks.append((header, data))
                continue
            if k in ("STEP", "AMPLITUDE"):
                break
            seen_mat = False

    sensor_ids: list[int] = []
    for name, mode, data in part_nsets:
        if name.upper().startswith("SENSOR_"):
            for row in data:
                row = row.strip().rstrip(",")
                if row:
                    sensor_ids.extend(int(x) for x in re.split(r"[,\s]+", row) if x)
    sensor_ids = sorted(set(sensor_ids))

    # Non-empty sets survive a remesh; on a re-meshed deck they are empty and the
    # sensor nodes must be recovered geometrically (nearest node to each position).
    part_nsets = [(n, m, d) for (n, m, d) in part_nsets
                  if not n.upper().startswith("SENSOR_") or any(x.strip() for x in d)]
    if not sensor_ids and not args.no_auto_sensors:
        import math
        R, Z0, N = 110.0, 150.0, 18
        targets = [(i + 1, R * math.cos(2 * math.pi * i / N),
                    R * math.sin(2 * math.pi * i / N), Z0) for i in range(N)]
        best = {sid: (1e30, None) for sid, _, _, _ in targets}
        for line in node_lines:
            parts = line.replace(",", " ").split()
            if len(parts) < 4:
                continue
            try:
                nid = int(parts[0]); x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
            except ValueError:
                continue
            for sid, tx, ty, tz in targets:
                d2 = (x - tx) ** 2 + (y - ty) ** 2 + (z - tz) ** 2
                if d2 < best[sid][0]:
                    best[sid] = (d2, nid)
        auto = []
        for sid, _, _, _ in targets:
            d2, nid = best[sid]
            auto.append((f"SENSOR_{sid:02d}", "LIST", [f"{nid},"]))
            print(f"auto sensor {sid:02d}: node {nid} (offset {math.sqrt(d2):.3f} mm)")
        part_nsets.extend(auto)
        sensor_ids = sorted(int(d[0].strip(",")) for _, _, d in auto)

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        f.write("*HEADING\n")
        f.write("Z00 base model for CalculiX (converted from Abaqus export)\n")
        f.write("*PREPRINT, ECHO=NO, MODEL=NO, HISTORY=NO, CONTACT=NO\n")
        f.write("*NODE\n")
        f.writelines(l + "\n" for l in node_lines)
        elset = "EALL"
        f.write(f"*ELEMENT, TYPE=C3D8R, ELSET={elset}\n")
        f.writelines(l + "\n" for l in elem_lines)
        for name, mode, data in part_nsets:
            suffix = ", GENERATE" if mode == "GENERATE" else ""
            f.write(f"*NSET, NSET={name}{suffix}\n")
            f.writelines(l + "\n" for l in data if l.strip())
        for name, mode, data in asm_nsets:
            f.write(f"*NSET, NSET={name}\n")
            f.writelines(l + "\n" for l in data if l.strip())
        f.write("*NSET, NSET=SENSORS\n")
        for i in range(0, len(sensor_ids), 16):
            f.write(", ".join(str(v) for v in sensor_ids[i:i + 16]) + "\n")
        src_node = next((int(d[0].strip(",")) for n, _, d in part_nsets
                         if n.upper() == "SENSOR_01" and d), sensor_ids[0] if sensor_ids else 0)
        if src_node:
            f.write("*NSET, NSET=SRC\n")
            f.write(f"{src_node},\n")
        f.write(f"*ELSET, ELSET={elset}, GENERATE\n")
        f.write(f" 1, {n_elems}, 1\n")
        f.write(f"*SOLID SECTION, ELSET={elset}, MATERIAL={material_name}\n")
        for header, data in mat_blocks:
            f.write(header + "\n")
            f.writelines(l + "\n" for l in data if l.strip())
        f.write(f"*AMPLITUDE, NAME={args.amp}\n")
        f.writelines(l + "\n" for l in amplitude)

        # --- step block(s) -------------------------------------------------
        # With --segments N the time history is cut into N *DYNAMIC steps that
        # share one continuous state; *RESTART,WRITE at the end of every step
        # leaves a restart point roughly every (total_time / N) seconds. If the
        # job dies, the last completed segment can be resumed with
        #     *RESTART, READ, STEP=<k>
        # after renaming <job>.rout to <newjob>.rin.
        def parse_pairs(lines):
            vals = []
            for line in lines:
                for tok in line.replace(",", " ").split():
                    vals.append(float(tok))
            return list(zip(vals[0::2], vals[1::2]))

        def amp_at(pairs, t):
            if not pairs:
                return 0.0
            if t <= pairs[0][0]:
                return pairs[0][1]
            for (ta, va), (tb, vb) in zip(pairs, pairs[1:]):
                if ta <= t <= tb:
                    return vb if tb == ta else va + (vb - va) * (t - ta) / (tb - ta)
            return pairs[-1][1]

        def segment_points(pairs, t0, t1):
            pts = [(0.0, amp_at(pairs, t0))]
            pts += [(t - t0, v) for t, v in pairs if t0 < t < t1]
            pts.append((t1 - t0, amp_at(pairs, t1)))
            out = []
            for p in pts:
                if out and abs(p[0] - out[-1][0]) < 1e-15:
                    out[-1] = p
                else:
                    out.append(p)
            return out

        total_time = float(args.time)
        dt = float(args.dt)
        n_seg = max(1, int(args.segments))
        seg_time = total_time / n_seg
        n_inc_total = int(round(total_time / dt))
        inc_per_seg = max(1, n_inc_total // n_seg)
        pairs = parse_pairs(amplitude)
        freq = f", FREQUENCY={args.print_freq}" if str(args.print_freq).strip() else ""

        for seg in range(n_seg):
            t0 = seg * seg_time
            t1 = total_time if seg == n_seg - 1 else (seg + 1) * seg_time
            amp_name = f"{args.amp}_S{seg + 1}"
            pts = segment_points(pairs, t0, t1)
            f.write(f"*AMPLITUDE, NAME={amp_name}\n")
            for t, v in pts:
                f.write(f"{t:.10e}, {v:.10e}\n")
            f.write(f"*STEP, NAME=SEG{seg + 1}, NLGEOM=NO, INC={inc_per_seg + 10}\n")
            f.write("*DYNAMIC, DIRECT, EXPLICIT=2\n")
            f.write(f"{args.dt}, {t1 - t0:.10e}\n")
            if n_seg > 1:
                f.write("*RESTART, WRITE, FREQUENCY=1\n")
            f.write(f"*BOUNDARY, AMPLITUDE={amp_name}\n")
            f.write(f"{args.src}, 1, 1, {args.amp_mag}\n")
            f.write(f"{args.src}, 2, 2, 0.\n")
            f.write(f"*NODE PRINT, NSET=SENSORS{freq}\n")
            f.write("U\n")
            if args.frd_mode == "sensors":
                f.write(f"*NODE FILE, NSET=SENSORS, FREQUENCY={args.file_freq}\n")
                f.write("U\n")
            elif args.frd_mode == "all":
                f.write(f"*NODE FILE, FREQUENCY={args.file_freq}\n")
                f.write("U\n")
            f.write("*END STEP\n")

    print(f"wrote {out} ({out.stat().st_size/1e6:.1f} MB)")
    print(f"nodes={n_nodes} elements={n_elems} sensors={len(sensor_ids)}")
    print(f"part nsets={[n for n, _, _ in part_nsets]}")
    print(f"assembly nsets={[n for n, _, _ in asm_nsets]}")
    print(f"material={material_name} amp_blocks={len(amplitude)} mat_blocks={len(mat_blocks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())