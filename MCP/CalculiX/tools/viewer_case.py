# -*- coding: utf-8 -*-
"""Export a CalculiX result into a CAE-Agent-Hub viewer case.

Reads the mesh from a CalculiX input deck (``*NODE`` / ``*ELEMENT`` blocks) and
one displacement frame from the ``.frd`` file, then writes

    <out-dir>/result_mesh.json   nodal coordinates/displacements + per-element |u|
    <out-dir>/cae_project.json   small metadata blob for the viewer header

The hub viewer's FE page colours elements with the per-element ``mises`` field;
for a transient run the meaningful scalar is the displacement magnitude, so the
field is filled with the nodal mean of |u| and the legend is relabelled through
``fieldLabel``.  Nothing is invented: colours are |u| and the deformation shown
is ``scale * u`` with ``scale = 1`` (true scale) by default. Pass
``--auto-scale`` (max |u| spans 6% of the model diagonal) or
``--deformation-scale N`` when an exaggerated view is wanted for a figure.

    python viewer_case.py --inp run.inp --frd run.frd --out-dir case/

The ``.frd`` is only written if the deck asks for it, e.g.

    *NODE FILE
    U

Use ``--frame -1`` (default) for the frame with the largest |u|, or ``--frame N``
for a specific frame index (0-based, as stored in the ``.frd``).
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

# fixed-width columns of the .frd " -1" node records
NODE_FIELD = slice(3, 13)
V1 = slice(13, 25)
V2 = slice(25, 37)
V3 = slice(37, 49)

HEX8 = ("C3D8", "C3D8R", "C3D8I", "C3D8T")


def parse_frames(path: Path):
    """Return [(time, {node: (ux, uy, uz)})] for every displacement frame."""
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
            if line.startswith(" -1"):
                try:
                    node = int(line[NODE_FIELD])
                    cur[node] = (float(line[V1]), float(line[V2]), float(line[V3]))
                except ValueError:
                    continue
    return frames


def load_mesh(inp: Path):
    """Return ({node: (x, y, z)}, [(element, [nodes])], element_type, step_name)."""
    nodes: dict[int, tuple[float, float, float]] = {}
    elems: list[tuple[int, list[int]]] = []
    etype = "C3D8R"
    step = "STEP-1"
    mode = None
    with inp.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("*"):
                up = line.upper()
                if up.startswith("*STEP"):
                    for tok in line.split(","):
                        tok = tok.strip()
                        if tok.upper().startswith("NAME="):
                            step = tok.split("=", 1)[1].strip()
                elif up.startswith("*ELEMENT"):
                    mode = "E"
                    if "TYPE=" in up:
                        etype = line.split("TYPE=", 1)[1].split(",")[0].strip()
                elif up.startswith("*NODE") and "FILE" not in up and "PRINT" not in up:
                    mode = "N"
                else:
                    mode = None
                continue
            if mode == "N":
                p = line.replace(",", " ").split()
                if len(p) >= 4:
                    try:
                        nodes[int(p[0])] = (float(p[1]), float(p[2]), float(p[3]))
                    except ValueError:
                        pass
            elif mode == "E":
                p = line.replace(",", " ").split()
                if len(p) >= 9:
                    elems.append((int(p[0]), [int(x) for x in p[1:9]]))
    return nodes, elems, etype, step


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inp", required=True, help="CalculiX deck with the mesh")
    ap.add_argument("--frd", required=True, help=".frd file with at least one U frame")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--frame", type=int, default=-1,
                    help="frame index (0-based); default -1 picks the largest |u|")
    ap.add_argument("--title", default="CalculiX result")
    ap.add_argument("--instance", default="MODEL")
    ap.add_argument("--field-label", default="U, Magnitude (mm)")
    ap.add_argument("--dt", default="", help="optional time increment, recorded in cae_project.json")
    ap.add_argument("--time", default="", help="optional total time, recorded in cae_project.json")
    ap.add_argument("--deformation-scale", type=float, default=None,
                    help="explicit displacement magnification; default 1.0 (true scale)")
    ap.add_argument("--auto-scale", action="store_true",
                    help="legacy convenience: scale so max |u| spans 6%% of the model diagonal")
    ap.add_argument("--with-deformed", action="store_true",
                    help="also write the redundant deformed array (the viewer recomputes it)")
    args = ap.parse_args()

    inp, frd = Path(args.inp), Path(args.frd)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    print("loading mesh ...", flush=True)
    nodes, elems, etype, step = load_mesh(inp)
    print(f"mesh: {len(nodes)} nodes, {len(elems)} elements ({etype}), step={step}", flush=True)
    if not nodes or not elems or etype not in HEX8:
        print(f"this exporter handles 8-node hex elements only (got {etype})")
        return 1

    frames = parse_frames(frd)
    if not frames:
        print("no displacement frames found in the .frd; add *NODE FILE / U to the deck")
        return 1
    if args.frame >= 0:
        idx = min(args.frame, len(frames) - 1)
    else:
        idx = max(range(len(frames)),
                  key=lambda i: max((abs(x) for v in frames[i][1].values() for x in v), default=0.0))
    t, disp = frames[idx]
    umax = max((abs(x) for v in disp.values() for x in v), default=0.0)

    xs = [nodes[n][0] for n in nodes]
    ys = [nodes[n][1] for n in nodes]
    zs = [nodes[n][2] for n in nodes]
    diag = math.dist((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))
    # True scale by default: a transient run's displacement is tiny compared with
    # the model, so magnifying it silently (the old 0.06*diag/umax rule) makes the
    # picture look like a different structure. Ask for --auto-scale explicitly.
    if args.deformation_scale is not None:
        scale = float(args.deformation_scale)
    elif args.auto_scale:
        scale = (0.06 * diag / umax) if umax > 0 else 1.0
    else:
        scale = 1.0

    node_list = []
    for label, (x, y, z) in nodes.items():
        d = disp.get(label, (0.0, 0.0, 0.0))
        record = {
            "label": label,
            "coordinates": [round(x, 6), round(y, 6), round(z, 6)],
            "displacement": [d[0], d[1], d[2]],
        }
        if args.with_deformed:
            record["deformed"] = [round(x + scale * d[0], 6), round(y + scale * d[1], 6),
                                  round(z + scale * d[2], 6)]
        node_list.append(record)

    elem_list = []
    vals = []
    for label, conn in elems:
        us = [math.sqrt(sum(c * c for c in disp.get(n, (0.0, 0.0, 0.0)))) for n in conn]
        val = float(sum(us) / len(us))
        vals.append(val)
        elem_list.append({"label": label, "type": etype, "connectivity": conn, "mises": val})

    vmin, vmax = min(vals), max(vals)
    payload = {
        "schemaVersion": 1,
        "source": inp.name,
        "instance": args.instance,
        "step": step,
        "analysisType": "dynamic",
        "frame": idx + 1,
        "timeMs": t * 1e3,
        "deformationScale": scale,
        "elementType": etype,
        "fieldLabel": args.field_label,
        "nodes": node_list,
        "elements": elem_list,
        "fieldRanges": {"misesMin": vmin, "misesMax": vmax, "maxDisplacement": umax},
    }

    target = out / "result_mesh.json"
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {target} ({target.stat().st_size / 1e6:.1f} MB)  "
          f"frame #{idx + 1}/{len(frames)} t={t:.3e} s  scale={scale:.1f}  "
          f"|u| {vmin:.2e}..{vmax:.2e}")

    settings = {"field": "U", "deformation_scale": round(scale, 6),
                "magnified": abs(scale - 1.0) > 1e-9, "frame": idx + 1}
    if args.dt:
        settings["dt_s"] = float(args.dt)
    if args.time:
        settings["total_time_s"] = float(args.time)
    project = {
        "schemaVersion": 1,
        "project": {
            "name": args.title,
            "solver": "CalculiX (ccx)",
            "model": f"3D dynamic explicit ({etype})",
            "source": inp.name,
        },
        "connection": {
            "status": "connected",
            "message": "Solved by CalculiX ccx; the .frd displacement frame is exported as result_mesh.json.",
        },
        "inputs": {
            "summary": [
                {"label": {"en": "Deck", "zh": "输入文件"},
                 "value": {"en": inp.name, "zh": inp.name}},
                {"label": {"en": "Mesh", "zh": "网格"},
                 "value": {"en": f"{len(elems)} {etype} elements, {len(nodes)} nodes",
                           "zh": f"{len(elems)} 个 {etype} 单元，{len(nodes)} 个节点"}},
                {"label": {"en": "Frame", "zh": "帧"},
                 "value": {"en": f"#{idx + 1} of {len(frames)}, t = {t * 1e3:.4g} ms",
                           "zh": f"第 {idx + 1}/{len(frames)} 帧，t = {t * 1e3:.4g} ms"}},
            ],
            "solver_settings": settings,
        },
        "outputs": {"status": "exported", "resultMesh": "result_mesh.json",
                    "frame": idx + 1, "timeMs": t * 1e3},
    }
    (out / "cae_project.json").write_text(json.dumps(project, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    print(f"wrote {out / 'cae_project.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
