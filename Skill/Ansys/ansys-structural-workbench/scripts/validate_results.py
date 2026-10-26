#!/usr/bin/env python3
"""Validate solver state, vector equilibrium, symmetry, and parasitic reactions."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def vector(value: object, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{label}.vector must contain three numbers")
    return [float(item) for item in value]


def norm(value: list[float]) -> float:
    return math.sqrt(sum(x * x for x in value))


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"status": "invalid", "errors": ["usage: validate_results.py RESULTS.json"]}))
        return 2
    try:
        root = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
        data = root.get("validation_data", root)
        solver = data["solver"]
        applied = data["applied_forces"]
        reactions = data["reactions"]
        validation = data.get("validation", {})
        force_tolerance = float(validation.get("force_balance_tolerance_percent", 0.5))
        moment_tolerance = float(validation.get("moment_balance_tolerance_percent", 1.0))
        if not isinstance(applied, list) or not applied or not isinstance(reactions, list) or not reactions:
            raise ValueError("applied_forces and reactions must be non-empty arrays")
        force_units = {item.get("unit") for item in applied + reactions}
        if len(force_units) != 1 or None in force_units:
            raise ValueError("all force vectors must use one explicit unit")
        av = [vector(item.get("vector"), f"applied_forces[{i}]") for i, item in enumerate(applied)]
        rv = [vector(item.get("vector"), f"reactions[{i}]") for i, item in enumerate(reactions)]
    except Exception as exc:
        print(json.dumps({"status": "invalid", "errors": [str(exc)]}))
        return 2

    checks, failures = {}, []
    solver_ok = bool(solver.get("run_completed")) and int(solver.get("error_count", 0)) == 0 and str(solver.get("final_state", "")).lower() == "converged"
    checks["solver_state"] = {"status": "pass" if solver_ok else "fail", "observed": solver}
    if not solver_ok:
        failures.append(checks["solver_state"])

    force_residual = [sum(v[i] for v in av + rv) for i in range(3)]
    force_denominator = sum(norm(v) for v in av)
    if force_denominator <= 0:
        print(json.dumps({"status": "invalid", "errors": ["total applied force magnitude must be positive"]}))
        return 2
    force_error = 100.0 * norm(force_residual) / force_denominator
    checks["force_balance"] = {"residual_vector": force_residual, "unit": next(iter(force_units)), "error_percent": force_error, "limit_percent": force_tolerance, "status": "pass" if force_error <= force_tolerance else "fail"}
    if force_error > force_tolerance:
        failures.append(checks["force_balance"])

    try:
        if data.get("applied_moments") is not None or data.get("reaction_moments") is not None:
            moments = data.get("applied_moments", []) + data.get("reaction_moments", [])
            if not moments:
                raise ValueError("moment arrays are empty")
            units = {item.get("unit") for item in moments}
            if len(units) != 1 or None in units:
                raise ValueError("all moments must use one explicit unit")
            mv = [vector(item.get("vector"), "moment") for item in moments]
            applied_mv = [vector(item.get("vector"), "applied moment") for item in data.get("applied_moments", [])]
            denominator = sum(norm(v) for v in applied_mv)
            if denominator <= 0:
                raise ValueError("total applied moment magnitude must be positive")
            residual = [sum(v[i] for v in mv) for i in range(3)]
            error = 100.0 * norm(residual) / denominator
            checks["moment_balance"] = {"residual_vector": residual, "unit": next(iter(units)), "error_percent": error, "limit_percent": moment_tolerance, "status": "pass" if error <= moment_tolerance else "fail"}
            if error > moment_tolerance:
                failures.append(checks["moment_balance"])

        by_name = {item["name"]: item for item in reactions}
        symmetry_checks = []
        for pair in data.get("symmetry_pairs", []):
            left, right = norm(vector(by_name[pair[0]]["vector"], pair[0])), norm(vector(by_name[pair[1]]["vector"], pair[1]))
            mismatch = 100.0 * abs(left - right) / max((left + right) / 2.0, 1e-12)
            limit = float(validation.get("symmetry_tolerance_percent", 2.0))
            item = {"pair": pair, "mismatch_percent": mismatch, "limit_percent": limit, "status": "pass" if mismatch <= limit else "fail"}
            symmetry_checks.append(item)
            if item["status"] == "fail":
                failures.append(item)
        if symmetry_checks:
            checks["symmetry"] = symmetry_checks

        parasitic_checks = []
        for name in data.get("parasitic_reaction_names", []):
            ratio = 100.0 * norm(vector(by_name[name]["vector"], name)) / force_denominator
            limit = float(validation.get("maximum_parasitic_reaction_percent", 0.1))
            item = {"reaction": name, "ratio_percent": ratio, "limit_percent": limit, "status": "pass" if ratio <= limit else "fail"}
            parasitic_checks.append(item)
            if item["status"] == "fail":
                failures.append(item)
        if parasitic_checks:
            checks["parasitic_reactions"] = parasitic_checks
    except Exception as exc:
        print(json.dumps({"status": "invalid", "errors": [str(exc)]}))
        return 2

    status = "fail" if failures else "pass"
    print(json.dumps({"status": status, "checks": checks, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
