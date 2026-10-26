#!/usr/bin/env python3
"""Normalize structural quantities into explicit target units."""

from __future__ import annotations

import json
import sys
from pathlib import Path


FACTORS = {
    "length": {"m": 1.0, "mm": 1e-3, "cm": 1e-2, "in": 0.0254},
    "force": {"N": 1.0, "kN": 1e3, "lbf": 4.4482216152605},
    "stress": {"Pa": 1.0, "kPa": 1e3, "MPa": 1e6, "GPa": 1e9, "psi": 6894.757293168},
    "moment": {"N*m": 1.0, "N*mm": 1e-3, "kN*m": 1e3, "lbf*in": 0.1129848290276},
    "density": {"kg/m^3": 1.0, "kg/mm^3": 1e9, "t/mm^3": 1e12},
    "angle": {"rad": 1.0, "deg": 0.017453292519943295},
}


def convert(value: object, scale: float) -> object:
    if isinstance(value, list):
        return [float(item) * scale for item in value]
    return float(value) * scale


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"status": "invalid", "errors": ["usage: normalize_units.py QUANTITIES.json"]}))
        return 2
    try:
        root = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
        items = root.get("quantities", root)
        if not isinstance(items, list) or not items:
            raise ValueError("quantities must be a non-empty array")
        normalized = []
        for index, item in enumerate(items):
            quantity = item["quantity"]
            source = item["unit"]
            target = item["to_unit"]
            table = FACTORS[quantity]
            if source not in table or target not in table:
                raise ValueError(f"quantities[{index}] unsupported {quantity} conversion: {source} -> {target}")
            scale = table[source] / table[target]
            normalized.append({**item, "value": convert(item["value"], scale), "unit": target, "source_unit": source})
    except Exception as exc:
        print(json.dumps({"status": "invalid", "errors": [str(exc)]}))
        return 2
    print(json.dumps({"status": "pass", "quantities": normalized}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
