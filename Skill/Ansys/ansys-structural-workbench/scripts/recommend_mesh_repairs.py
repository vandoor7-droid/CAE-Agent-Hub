#!/usr/bin/env python3
"""Select one bounded, auditable mesh repair from normalized evidence."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"status": "invalid", "errors": ["usage: recommend_mesh_repairs.py LOOP.json"]}))
        return 2
    try:
        data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
        mesh = data["mesh"]
        attempt = int(data.get("attempt", 1))
        max_attempts = int(data.get("max_attempts", 3))
        history = data.get("repair_history", [])
        if attempt < 1 or max_attempts < 1 or not isinstance(history, list):
            raise ValueError("attempt/max_attempts/history are invalid")
    except Exception as exc:
        print(json.dumps({"status": "invalid", "errors": [str(exc)]}))
        return 2

    action: dict
    if attempt > max_attempts:
        action = {"action": "stop", "reason": "maximum repair attempts reached"}
    elif mesh.get("unmeshed_active_body_count", 0) or mesh.get("invalid_contact_scope_count", 0) or mesh.get("lost_control_scope_count", 0):
        action = {"action": "repair_scope", "reason": "invalid or lost mesh/contact scope"}
    elif mesh.get("nonpositive_jacobian_count", 0) or mesh.get("zero_or_negative_volume_count", 0):
        regions = sorted({str(x.get("region")) for x in mesh.get("worst_elements", []) if x.get("region")})
        prior = any(x.get("action") == "refine_worst_region" for x in history)
        if regions and not prior:
            action = {"action": "refine_worst_region", "regions": regions, "size_factor": 0.7, "reason": "invalid element localized"}
        else:
            action = {"action": "switch_method", "method": data.get("method_policy", {}).get("fallback", "patch_conforming_tetra"), "reason": "invalid element persists"}
    else:
        bad_contacts = [x for x in mesh.get("contact_size_ratios", []) if float(x.get("ratio", 1.0)) > float(mesh.get("maximum_contact_size_ratio", 1.5))]
        if bad_contacts:
            action = {"action": "match_contact_sizing", "contacts": [x.get("name") for x in bad_contacts], "target_ratio": mesh.get("maximum_contact_size_ratio", 1.5), "reason": "opposing contact sizes differ"}
        elif mesh.get("insufficient_thickness_layer_count", 0):
            action = {"action": "increase_thickness_layers", "minimum_layers": mesh.get("required_thickness_layers"), "reason": "through-thickness resolution is insufficient"}
        elif mesh.get("worst_skewness_in_critical_region") or mesh.get("low_quality_elements_in_critical_region"):
            regions = sorted({str(x.get("region")) for x in mesh.get("worst_elements", []) if x.get("region")})
            if regions:
                action = {"action": "refine_worst_region", "regions": regions, "size_factor": 0.8, "reason": "poor quality in a critical region"}
            elif not any(x.get("action") == "slow_transition" for x in history):
                action = {"action": "slow_transition", "growth_rate_factor": 0.8, "reason": "poor critical-region quality without a finer location"}
            else:
                action = {"action": "switch_method", "method": data.get("method_policy", {}).get("fallback", "patch_conforming_tetra"), "reason": "targeted repair unavailable or exhausted"}
        else:
            action = {"action": "stop", "reason": "no approved deterministic repair matches the observed warning"}

    print(json.dumps({"status": "action" if action["action"] != "stop" else "blocked", "attempt": attempt, "max_attempts": max_attempts, "repair": action}, indent=2))
    return 0 if action["action"] != "stop" else 1


if __name__ == "__main__":
    raise SystemExit(main())
