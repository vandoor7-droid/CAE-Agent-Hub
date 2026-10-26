#!/usr/bin/env python3
"""Render the bundled structural-analysis report template from normalized JSON."""

from __future__ import annotations

import json
import sys
from pathlib import Path


FIELDS = [
    "task_name", "status", "scope_and_assumptions", "model_summary", "mesh_summary",
    "solver_diagnostics", "validation_matrix", "convergence_table", "evidence_files", "limitations",
]


def render(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(f"- {item}" for item in value) or "- None recorded"
    if isinstance(value, dict):
        return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```"
    return str(value)


def main() -> int:
    if len(sys.argv) != 3:
        print(json.dumps({"status": "invalid", "errors": ["usage: build_analysis_report.py DATA.json OUTPUT.md"]}))
        return 2
    try:
        data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
        template = Path(__file__).resolve().parents[1] / "assets" / "structural-analysis-report-template.md"
        text = template.read_text(encoding="utf-8-sig")
        missing = [field for field in FIELDS if field not in data]
        if missing:
            raise ValueError("missing report fields: " + ", ".join(missing))
        for field in FIELDS:
            text = text.replace("{{" + field + "}}", render(data[field]))
        output = Path(sys.argv[2])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    except Exception as exc:
        print(json.dumps({"status": "invalid", "errors": [str(exc)]}))
        return 2
    print(json.dumps({"status": "pass", "output": str(output.resolve())}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
