import os
from pathlib import Path
import unittest

from aedt_launcher import AedtLauncher
from aedt_target import AedtTarget
from tests.live.run_acceptance import normal_close_while_connected
from worker_client import WorkerClient


RUN_LIVE = os.environ.get("RUN_AEDT_LIVE_TESTS") == "1"


@unittest.skipUnless(RUN_LIVE, "set RUN_AEDT_LIVE_TESTS=1 for live AEDT tests")
class Aedt2026R1LiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.aedt_root = os.environ["AEDT_INSTALL_DIR"]
        cls.port = int(os.environ.get("AEDT_TEST_PORT", "50061"))
        cls.artifacts = Path(__file__).resolve().parents[2] / "test-artifacts"
        cls.artifacts.mkdir(parents=True, exist_ok=True)
        cls.client = WorkerClient(log_dir=cls.artifacts / "logs")

    @classmethod
    def tearDownClass(cls):
        cls.client.close_all()

    def test_grpc_session_supports_repeated_broker_calls_and_normal_close(self):
        session = AedtLauncher(worker_client=self.client).launch(
            install_dir=self.aedt_root,
            port=self.port,
            timeout=120,
        )
        target = AedtTarget("port", session["port"])

        probes = [self.client.execute(target, "ping", {}, timeout=30) for _ in range(10)]
        self.assertTrue(all(item["connected"] for item in probes))
        self.assertTrue(all(item["target"]["value"] == self.port for item in probes))

        created = self.client.execute(
            target,
            "create_hfss_design",
            {
                "project_name": "McpAcceptanceProject",
                "design_name": "McpAcceptanceHFSS",
                "solution_type": "DrivenModal",
            },
            timeout=60,
        )
        self.assertEqual(created["design_name"], "McpAcceptanceHFSS")

        project_path = self.artifacts / "McpAcceptanceProject.aedt"
        saved = self.client.execute(
            target,
            "save_project",
            {"path": str(project_path)},
            timeout=60,
        )
        self.assertTrue(saved["saved"])
        self.assertTrue(project_path.exists())
        normal_close_while_connected(session["pid"])


if __name__ == "__main__":
    unittest.main()
