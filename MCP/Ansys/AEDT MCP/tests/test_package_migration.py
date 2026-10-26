from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PackageMigrationTests(unittest.TestCase):
    def test_legacy_bridge_files_are_absent(self):
        obsolete = [
            "aedt_mcp_bridge.py",
            "aedt_socket_protocol.py",
            "reload_bridge_in_aedt.py",
            "stop_bridge_in_aedt.py",
            "stop_mcp.py",
            "scripts/install_aedt_mcp_autostart.ps1",
            "scripts/install_aedt_toolkit_button.ps1",
            "scripts/launch_aedt_with_mcp_bridge.ps1",
            "scripts/start_aedt_mcp_bridge_in_aedt.py",
            "scripts/stop_aedt_mcp_bridge_in_aedt.py",
        ]

        present = [path for path in obsolete if (ROOT / path).exists()]

        self.assertEqual(present, [])

    def test_documentation_describes_pyaedt_explicit_targets_and_release(self):
        for name in ("README.md", "README.zh-CN.md"):
            with self.subTest(name=name):
                content = (ROOT / name).read_text(encoding="utf-8")
                self.assertIn("PyAEDT", content)
                self.assertIn("PID", content)
                self.assertIn("port", content.lower())
                self.assertIn("broker", content.lower())
                self.assertIn("release_desktop", content)
                self.assertIn("release_connection", content)
                self.assertIn("QuitApplication", content)
                self.assertNotIn("aedt_mcp_bridge.py", content)
                self.assertNotIn("click `Start AEDT MCP Bridge`", content)

    def test_environment_example_contains_only_worker_configuration(self):
        content = (ROOT / ".env.example").read_text(encoding="utf-8")

        self.assertIn("AEDT_VERSION=2026.1", content)
        self.assertIn("AEDT_WORKER_TIMEOUT=60", content)
        self.assertNotIn("AEDT_MCP_PORT", content)
        self.assertNotIn("AEDT_MCP_TOKEN", content)

    def test_mcp_config_has_no_raw_bridge_variables(self):
        content = (ROOT / "examples" / "mcp_config.example.json").read_text(encoding="utf-8")

        self.assertIn("AEDT_VERSION", content)
        self.assertNotIn("AEDT_MCP_HOST", content)
        self.assertNotIn("AEDT_MCP_PORT", content)

    def test_close_watcher_is_packaged(self):
        content = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn('"aedt_close_watcher"', content)

    def test_legacy_toolbar_cleanup_script_is_present_and_scoped(self):
        content = (ROOT / "scripts" / "remove_legacy_aedt_mcp_toolbar.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("Codex MCP", content)
        self.assertIn("Start AEDT MCP Bridge", content)
        self.assertIn("Stop AEDT MCP Bridge", content)
        self.assertNotIn("Remove-Item -Recurse", content)


if __name__ == "__main__":
    unittest.main()
