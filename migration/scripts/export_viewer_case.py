# -*- coding: utf-8 -*-
"""Build a CAE-Agent-Hub viewer case (result_mesh.json + cae_project.json) from a
CalculiX deck plus an .frd frame.

The viewer's FE page colours elements by the ``mises`` field; for a transient
ultrasonic run the meaningful scalar is the displacement magnitude, so the field
is filled with |u| per element and the legend is relabelled through
``fieldLabel``. Nothing is invented: colours are |u|, deformation is the real
displacement vector scaled for visibility.

    python export_viewer_case.py --inp run.inp --frd run.frd --out-dir case_dir
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

from frd_to_dat import parse_frames

C3D8_EDGES = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
              (0, 4), (1, 5), (2, 6), (3, 7)]


def load_mesh(inp: Path):
    nodes: dict[int, tuple[float, float, float]] = {}
    elems: list[tuple[int, list[int]]] = []
    mode = None
    with inp.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("*"):
                u = line.upper()
                mode = "N" if u.startswith("*NODE") else ("E" if u.startswith("*ELEMENT") else None)
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
    return nodes, elems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inp", required=True)
    ap.add_argument("--frd", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--frame", type=int, default=-1)
    ap.add_argument("--max-json-mb", type=float, default=0.0, help="subsample by z<=half if exceeded")
    ap.add_argument("--title", default="Z00 木柱超声仿真")
    ap.add_argument("--deformation-scale", type=float, default=None,
                    help="explicit displacement magnification; default 1.0 (true scale)")
    ap.add_argument("--auto-scale", action="store_true",
                    help="legacy convenience: scale so max |u| spans 6%% of the model diagonal")
    ap.add_argument("--with-deformed", action="store_true", help="also write the redundant deformed array")
    args = ap.parse_args()

    inp, frd = Path(args.inp), Path(args.frd)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    print("loading mesh ...", flush=True)
    nodes, elems = load_mesh(inp)
    print(f"mesh: {len(nodes)} nodes, {len(elems)} elements", flush=True)

    frames = parse_frames(frd)
    if not frames:
        print("no frames in frd")
        return 1
    if args.frame >= 0:
        idx = min(args.frame, len(frames) - 1)
    else:
        idx = max(range(len(frames)),
                  key=lambda i: max((abs(x) for v in frames[i][1].values() for x in v), default=0.0))
    t, disp = frames[idx]
    umax = max((math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2) for v in disp.values()), default=0.0)
    print(f"frame #{idx} t={t:.3e}s  nodes with data={len(disp)}  |u|max={umax:.3e} mm", flush=True)

    xyz = np.array(list(nodes.values()), dtype=np.float64)
    bbox = xyz.max(axis=0) - xyz.min(axis=0)
    diag = float(np.linalg.norm(bbox))
    # true scale by default; magnification must be asked for explicitly
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
        elem_list.append({"label": label, "type": "C3D8R", "connectivity": conn, "mises": val})

    vmin, vmax = min(vals), max(vals)
    payload = {
        "schemaVersion": 1,
        "source": inp.name,
        "instance": "WOODCOLUMN",
        "step": "UltrasonicStep",
        "analysisType": "dynamic",
        "frame": idx + 1,
        "timeMs": t * 1e3,
        "deformationScale": scale,
        "elementType": "C3D8R",
        "fieldLabel": "U, Magnitude (mm)",
        "nodes": node_list,
        "elements": elem_list,
        "fieldRanges": {
            "misesMin": vmin,
            "misesMax": vmax,
            "maxDisplacement": umax,
        },
    }

    target = out / "result_mesh.json"
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    size_mb = target.stat().st_size / 1e6
    print(f"wrote {target} ({size_mb:.1f} MB)  scale={scale:.1f}  |u| field {vmin:.2e}..{vmax:.2e} mm")

    project = {
        "schemaVersion": 1,
        "project": {
            "name": args.title,
            "prompt": "CalculiX 复算：木柱超声场显式动力学，50 kHz 五周期激励，18 传感器监测。",
            "solver": "CalculiX (ccx)",
            "model": "3D dynamic explicit (C3D8R)",
            "source": inp.name,
        },
        "connection": {
            "status": "connected",
            "message": "由 CalculiX ccx 求解，.frd 场输出导出为 result_mesh.json。",
        },
        "inputs": {
            "summary": [
                {"label": {"en": "Geometry", "zh": "几何"},
                 "value": {"en": "D220 x H300 mm wood column, void r12 x h40 mm", "zh": "D220×H300 mm 木柱，空洞 r12×h40 mm"}},
                {"label": {"en": "Material", "zh": "材料"},
                 "value": {"en": "Wood, E = 1340 MPa, nu = 0.3, rho = 6e-10 t/mm3", "zh": "木材，E=1340 MPa，ν=0.3，ρ=6e-10 t/mm³"}},
                {"label": {"en": "Excitation", "zh": "激励"},
                 "value": {"en": "50 kHz 5-cycle Hanning, U1 = 1e-4 mm, 0.22 ms", "zh": "50 kHz 五周期汉宁窗，U1=1e-4 mm，0.22 ms"}},
                {"label": {"en": "Mesh", "zh": "网格"},
                 "value": {"en": f"C3D8R, {len(elems)} elements, 5 mm seed", "zh": f"C3D8R，{len(elems)} 单元，5 mm 种子"}},
            ],
            "solver_settings": {"dt_s": 1.2e-7, "total_time_s": 2.2e-4, "field": "U"},
        },
        "outputs": {"status": "exported", "resultMesh": "result_mesh.json", "frame": idx + 1, "timeMs": t * 1e3},
    }
    (out / "cae_project.json").write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out/'cae_project.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())