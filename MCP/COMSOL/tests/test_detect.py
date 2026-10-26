from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import detect


class DetectTests(unittest.TestCase):
    def test_find_api_jars_under_common_comsol_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jar = root / "plugins" / "comsol.jar"
            jar.parent.mkdir(parents=True)
            jar.write_text("placeholder", encoding="utf-8")

            self.assertEqual(detect.find_api_jars(root), [str(jar.resolve())])

    def test_runs_dir_uses_env_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"COMSOL_MCP_RUNS_DIR": tmp}, clear=False):
                self.assertEqual(detect.runs_dir(), Path(tmp).resolve())

    def test_detect_reports_license_note_without_asserting_license(self):
        result = detect.detect_comsol_environment()

        self.assertIn("notes", result)
        self.assertIn("available", result)


if __name__ == "__main__":
    unittest.main()
