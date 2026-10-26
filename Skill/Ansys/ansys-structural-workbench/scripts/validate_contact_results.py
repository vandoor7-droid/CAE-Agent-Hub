#!/usr/bin/env python3
"""Validate contact state, penetration, force transfer, symmetry, and friction bounds."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path


OPEN = {"open", "far_open"}


def relative_error(value: float, target: float, epsilon: float = 1e-12) -> float:
    return 100.0 * abs(value - target) / max(abs(target), epsilon)


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"status": "invalid", "errors": ["usage: validate_contact_results.py CONTACT.json"]}))
        return 2
    try:
        root = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
        contacts = root["contacts"]
        if not isinstance(contacts, list) or not contacts:
            raise ValueError("contacts must be a non-empty array")
        maximum_penetration = float(root.get("validation", {}).get("maximum_penetration", 0.1))
        force_tolerance = float(root.get("validation", {}).get("contact_force_tolerance_percent", 3.0))
        symmetry_tolerance = float(root.get("validation", {}).get("symmetry_tolerance_percent", 2.0))
    except Exception as exc:
        print(json.dumps({"status": "invalid", "errors": [str(exc)]}))
        return 2

    checks, failures, warnings = [], [], []
    by_name = {}
    try:
        for contact in contacts:
            name = contact["name"]
            by_name[name] = contact
            status = str(contact.get("status", "unknown")).lower().replace(" ", "_")
            if contact.get("required_closed", True) and status in OPEN:
                failures.append({"check": "contact_status", "contact": name, "status": status})
            penetration = float(contact.get("maximum_penetration", 0.0))
            checks.append({"check": "penetration", "contact": name, "value": penetration, "limit": maximum_penetration})
            if penetration > maximum_penetration:
                failures.append(checks[-1])
            if "expected_force_magnitude" in contact:
                observed = float(contact["force_magnitude"])
                error = relative_error(observed, float(contact["expected_force_magnitude"]))
                check = {"check": "contact_force", "contact": name, "error_percent": error, "limit_percent": force_tolerance}
                checks.append(check)
                if error > force_tolerance:
                    failures.append(check)
            if float(contact.get("friction_coefficient", 0.0)) > 0 and "tangential_force" in contact and "normal_force" in contact:
                limit = float(contact["friction_coefficient"]) * abs(float(contact["normal_force"])) * float(contact.get("friction_limit_factor", 1.02))
                tangential = abs(float(contact["tangential_force"]))
                check = {"check": "friction_bound", "contact": name, "tangential_force": tangential, "limit": limit}
                checks.append(check)
                if tangential > limit:
                    failures.append(check)
        for pair in root.get("symmetry_pairs", []):
            left = abs(float(by_name[pair[0]]["force_magnitude"]))
            right = abs(float(by_name[pair[1]]["force_magnitude"]))
            mismatch = 100.0 * abs(left - right) / max((left + right) / 2.0, 1e-12)
            check = {"check": "contact_symmetry", "pair": pair, "mismatch_percent": mismatch, "limit_percent": symmetry_tolerance}
            checks.append(check)
            if mismatch > symmetry_tolerance:
                failures.append(check)
    except Exception as exc:
        print(json.dumps({"status": "invalid", "errors": [str(exc)]}))
        return 2

    status = "fail" if failures else ("warning" if warnings else "pass")
    print(json.dumps({"status": status, "checks": checks, "failures": failures, "warnings": warnings}, indent=2))
    return 1 if status != "pass" else 0


if __name__ == "__main__":
    raise SystemExit(main())
