#!/usr/bin/env python3
"""Calculate declared analytical reference quantities without inventing allowables."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def calculate(item: dict) -> dict:
    kind = item["type"]
    p = item["parameters"]
    if kind == "double_shear_stress":
        value = float(p["force"]) / (2.0 * math.pi * float(p["diameter"]) ** 2 / 4.0)
    elif kind == "bearing_stress":
        value = float(p["force"]) / (float(p["diameter"]) * float(p["thickness"]))
    elif kind == "net_section_stress":
        value = float(p["force"]) / ((float(p["width"]) - float(p["hole_diameter"])) * float(p["thickness"]))
    elif kind == "cantilever_tip_displacement":
        value = float(p["force"]) * float(p["length"]) ** 3 / (3.0 * float(p["youngs_modulus"]) * float(p["second_moment"]))
    elif kind == "cantilever_root_bending_stress":
        value = float(p["force"]) * float(p["length"]) * float(p["outer_fiber_distance"]) / float(p["second_moment"])
    elif kind == "friction_pullout_capacity":
        value = float(p["friction_coefficient"]) * float(p["average_pressure"]) * math.pi * float(p["diameter"]) * float(p["engagement_length"])
    else:
        raise ValueError(f"unsupported reference type: {kind}")
    return {"name": item.get("name", kind), "type": kind, "value": value, "unit": item["unit"], "purpose": item.get("purpose", "quantity_order_check")}


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"status": "invalid", "errors": ["usage: calculate_reference_values.py REFERENCES.json"]}))
        return 2
    try:
        root = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
        specs = root.get("references", root)
        if not isinstance(specs, list) or not specs:
            raise ValueError("references must be a non-empty array")
        results = [calculate(spec) for spec in specs]
    except Exception as exc:
        print(json.dumps({"status": "invalid", "errors": [str(exc)]}))
        return 2
    print(json.dumps({"status": "pass", "results": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
