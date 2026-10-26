from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
REFERENCES = ROOT / "references"


def run_script(name: str, *args: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPTS / name), *(str(arg) for arg in args)], text=True, capture_output=True)


class SkillScriptTests(unittest.TestCase):
    def test_job_specs(self) -> None:
        for name in ("example-clevis-pin.json", "example-bolted-joint.json"):
            result = run_script("validate_job_spec.py", REFERENCES / name)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_mesh_quality_and_repair(self) -> None:
        quality = run_script("evaluate_mesh_quality.py", REFERENCES / "example-mesh-quality.json")
        self.assertEqual(quality.returncode, 0, quality.stdout)
        repair = run_script("recommend_mesh_repairs.py", REFERENCES / "example-mesh-loop.json")
        self.assertEqual(repair.returncode, 0, repair.stdout)
        self.assertEqual(json.loads(repair.stdout)["repair"]["action"], "refine_worst_region")

    def test_results_contact_and_convergence(self) -> None:
        results = run_script("validate_results.py", REFERENCES / "example-clevis-pin.json")
        self.assertEqual(results.returncode, 0, results.stdout)
        contact = run_script("validate_contact_results.py", REFERENCES / "example-contact-results.json")
        self.assertEqual(contact.returncode, 0, contact.stdout)
        convergence = run_script("evaluate_mesh_convergence.py", REFERENCES / "example-clevis-pin.json")
        self.assertEqual(convergence.returncode, 0, convergence.stdout)

    def test_units_references_and_report(self) -> None:
        units = run_script("normalize_units.py", REFERENCES / "example-units.json")
        self.assertEqual(units.returncode, 0, units.stdout)
        self.assertEqual(json.loads(units.stdout)["quantities"][0]["value"][0], 30000.0)
        refs = run_script("calculate_reference_values.py", REFERENCES / "example-reference-values.json")
        self.assertEqual(refs.returncode, 0, refs.stdout)
        self.assertAlmostEqual(json.loads(refs.stdout)["results"][0]["value"], 47.7464829, places=5)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.md"
            report = run_script("build_analysis_report.py", REFERENCES / "example-report-data.json", output)
            self.assertEqual(report.returncode, 0, report.stdout)
            self.assertIn("CLEVIS_PIN_DSJ_V1", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
