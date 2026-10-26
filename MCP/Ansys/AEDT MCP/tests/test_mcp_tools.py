import json
import unittest

import mcp_server


class FakeWorkerClient:
    def __init__(self):
        self.calls = []

    async def execute_async(self, target, command, arguments, timeout=None):
        self.calls.append((target, command, arguments, timeout))
        return {
            "target": {"kind": target.kind, "value": target.value},
            "command": command,
            **arguments,
        }

    async def release_async(self, target, timeout=None):
        self.calls.append((target, "release_connection", {}, timeout))
        return {
            "target": {"kind": target.kind, "value": target.value},
            "released": True,
        }


class FakeDiscovery:
    def __init__(self):
        self.calls = 0

    def list_sessions(self):
        self.calls += 1
        return [{"pid": 101, "version": "2026.1", "listening_ports": [50051]}]


class FakeLauncher:
    def __init__(self):
        self.calls = []

    def launch(self, **kwargs):
        self.calls.append(kwargs)
        return {"pid": 202, "port": kwargs["port"] or 55000, "version": "2026.1"}


class McpToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.original_worker = mcp_server.worker_client
        self.original_discovery = mcp_server.session_discovery
        self.original_launcher = mcp_server.aedt_launcher
        self.worker = FakeWorkerClient()
        self.discovery = FakeDiscovery()
        self.launcher = FakeLauncher()
        mcp_server.worker_client = self.worker
        mcp_server.session_discovery = self.discovery
        mcp_server.aedt_launcher = self.launcher

    def tearDown(self):
        mcp_server.worker_client = self.original_worker
        mcp_server.session_discovery = self.original_discovery
        mcp_server.aedt_launcher = self.original_launcher

    async def test_list_sessions_is_discovery_only(self):
        result = await mcp_server.list_aedt_sessions()

        self.assertEqual(result["sessions"][0]["pid"], 101)
        self.assertEqual(self.worker.calls, [])

    async def test_launch_aedt_passes_visible_session_options(self):
        result = await mcp_server.launch_aedt(port=50051, install_dir="G:/AnsysEM")

        self.assertEqual(result["pid"], 202)
        self.assertEqual(self.launcher.calls[0]["version"], "2026.1")
        self.assertEqual(self.launcher.calls[0]["port"], 50051)

    async def test_every_targeted_tool_rejects_missing_or_double_target(self):
        calls = (
            lambda: mcp_server.check_aedt_connection(),
            lambda: mcp_server.release_connection(pid=1, port=50051),
            lambda: mcp_server.get_project_info(),
            lambda: mcp_server.save_project(pid=1, port=50051),
        )
        for call in calls:
            with self.subTest(call=call):
                with self.assertRaises(ValueError):
                    await call()
        self.assertEqual(self.worker.calls, [])

    async def test_check_uses_ping_and_release_stops_broker(self):
        checked = await mcp_server.check_aedt_connection(pid=101)
        released = await mcp_server.release_connection(port=50051)

        self.assertEqual(checked["target"], {"kind": "pid", "value": 101})
        self.assertEqual(self.worker.calls[0][1], "ping")
        self.assertEqual(self.worker.calls[1][0].key, "port:50051")
        self.assertEqual(self.worker.calls[1][1], "release_connection")
        self.assertTrue(released["released"])

    async def test_project_and_save_tools_preserve_explicit_target(self):
        info = await mcp_server.get_project_info(port=50051)
        saved = await mcp_server.save_project(pid=101, path="C:/demo.aedt")

        self.assertEqual(info["target"]["value"], 50051)
        self.assertEqual(saved["path"], "C:/demo.aedt")
        self.assertEqual(self.worker.calls[0][1], "project_info")
        self.assertEqual(self.worker.calls[1][1], "save_project")

    async def test_close_projects_forwards_exact_names_without_saving(self):
        result = await mcp_server.close_projects(
            pid=15488,
            project_names=["Old1", "Old2"],
            save=False,
        )

        self.assertEqual(result["target"], {"kind": "pid", "value": 15488})
        self.assertEqual(self.worker.calls[0][1], "close_projects")
        self.assertEqual(self.worker.calls[0][2]["project_names"], ["Old1", "Old2"])
        self.assertFalse(self.worker.calls[0][2]["save"])

    async def test_hfss_tools_forward_structured_arguments(self):
        created = await mcp_server.create_hfss_design(
            port=50051,
            project_name="P",
            design_name="D",
            solution_type="DrivenModal",
        )
        started = await mcp_server.start_analysis(
            pid=101,
            project_name="P",
            design_name="D",
            setup_name="Setup1",
        )
        status = await mcp_server.get_analysis_status(
            pid=101,
            project_name="P",
            design_name="D",
            setup_name="Setup1",
        )

        self.assertEqual(created["project_name"], "P")
        self.assertFalse(started["blocking"])
        self.assertEqual(status["setup_name"], "Setup1")
        self.assertEqual(
            [call[1] for call in self.worker.calls],
            ["create_hfss_design", "start_analysis", "analysis_status"],
        )

    async def test_wr90_tool_forwards_explicit_target_and_solve_options(self):
        result = await mcp_server.build_wr90_waveguide(
            port=50051,
            project_name="WR90_Modal",
            design_name="TE10_Through",
            output_dir="C:/temp/wr90",
            solve=True,
        )

        self.assertEqual(result["target"], {"kind": "port", "value": 50051})
        self.assertEqual(self.worker.calls[0][1], "build_wr90_waveguide")
        self.assertEqual(self.worker.calls[0][2]["project_name"], "WR90_Modal")
        self.assertEqual(self.worker.calls[0][2]["design_name"], "TE10_Through")
        self.assertEqual(self.worker.calls[0][2]["output_dir"], "C:/temp/wr90")
        self.assertTrue(self.worker.calls[0][2]["solve"])

    def test_status_resource_never_attaches(self):
        result = json.loads(mcp_server.aedt_status())

        self.assertFalse(result["connected"])
        self.assertEqual(result["sessions"][0]["pid"], 101)
        self.assertEqual(self.worker.calls, [])

    def test_agent_instructions_require_explicit_target(self):
        instructions = mcp_server.agent_instructions()

        self.assertIn("PID", instructions)
        self.assertIn("gRPC port", instructions)
        self.assertIn("no implicit", instructions.lower())


if __name__ == "__main__":
    unittest.main()
