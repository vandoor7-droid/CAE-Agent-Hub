import unittest

from aedt_target import AedtTarget
from pyaedt_backend import BackendCommandError, PyAedtBackend


class FakeDesign:
    def __init__(self, name="HFSSDesign1"):
        self.name = name

    def GetName(self):
        return self.name


class FakeProject:
    def __init__(self, name="Demo", design=None):
        self.name = name
        self.design = design or FakeDesign()

    def GetName(self):
        return self.name

    def GetActiveDesign(self):
        return self.design


class FakeDesktop:
    def __init__(self, *, fail_projects=False, is_grpc_api=None, **kwargs):
        self.kwargs = kwargs
        self.fail_projects = fail_projects
        self.releases = []
        self.saved = []
        self.closed = []
        self.quit_calls = 0
        self.odesktop = self
        self.aedt_version_id = "2026.1"
        self.aedt_process_id = kwargs.get("aedt_process_id", 4321)
        self.port = kwargs.get("port", 0)
        self.is_grpc_api = (
            kwargs.get("port") is not None if is_grpc_api is None else is_grpc_api
        )
        self.project = FakeProject()
        self.projects = ["Demo"]

    @property
    def project_list(self):
        if self.fail_projects:
            raise RuntimeError("project lookup failed")
        return list(self.projects)

    def active_project(self, name=None):
        return self.project

    def active_design(self, project=None):
        if self.project.design is None:
            raise IndexError("no designs")
        return self.project.design

    def design_type(self, project_name=None, design_name=None):
        return "HFSS"

    def design_list(self, project_name=None):
        return [self.project.design.GetName()] if self.project.design is not None else []

    def save_project(self, project_name=None, project_path=None):
        self.saved.append((project_name, project_path))
        return True

    def CloseProject(self, project_name):
        self.closed.append(project_name)
        self.projects.remove(project_name)

    def release_desktop(self, close_projects=False, close_on_exit=False):
        self.releases.append((close_projects, close_on_exit))
        return True

    def QuitApplication(self):
        self.quit_calls += 1
        return True


class FakeHfss:
    def __init__(self, desktop, **kwargs):
        self.desktop_class = desktop
        self.kwargs = kwargs
        self.project_name = kwargs.get("project")
        self.design_name = kwargs.get("design")
        self.solution_type = kwargs.get("solution_type")
        self.analysis_calls = []
        self.are_there_simulations_running = False

    def analyze_setup(self, name=None, blocking=True):
        self.analysis_calls.append((name, blocking))
        return True

    def get_setups(self):
        return ["Setup1"]


class PyAedtBackendTests(unittest.TestCase):
    def setUp(self):
        self.desktops = []
        self.apps = []
        self.wr90_calls = []

        def desktop_factory(**kwargs):
            desktop = FakeDesktop(**kwargs)
            self.desktops.append(desktop)
            return desktop

        def hfss_factory(**kwargs):
            desktop = self.desktops[0]
            app = FakeHfss(desktop, **kwargs)
            self.apps.append(app)
            return app

        def wr90_builder(app, output_dir, solve):
            self.wr90_calls.append((app, output_dir, solve))
            return {
                "success": True,
                "project": app.project_name,
                "design": app.design_name,
                "output_dir": str(output_dir),
                "solved": solve,
            }

        self.backend = PyAedtBackend(
            desktop_factory=desktop_factory,
            hfss_factory=hfss_factory,
            wr90_builder=wr90_builder,
        )

    def test_pid_connection_arguments_and_explicit_release(self):
        result = self.backend.execute(AedtTarget("pid", 66276), "ping", {})

        self.assertTrue(result["connected"])
        self.assertEqual(result["target"], {"kind": "pid", "value": 66276})
        self.assertEqual(self.desktops[0].kwargs["aedt_process_id"], 66276)
        self.assertNotIn("port", self.desktops[0].kwargs)
        self.assertEqual(self.desktops[0].releases, [])

        self.assertTrue(self.backend.release())
        self.assertEqual(self.desktops[0].releases, [(False, False)])

    def test_port_connection_arguments_and_explicit_release(self):
        self.backend.execute(AedtTarget("port", 50051), "ping", {})

        kwargs = self.desktops[0].kwargs
        self.assertEqual(kwargs["machine"], "localhost")
        self.assertEqual(kwargs["port"], 50051)
        self.assertNotIn("aedt_process_id", kwargs)
        self.assertEqual(self.desktops[0].releases, [])
        self.assertTrue(self.backend.release())
        self.assertEqual(self.desktops[0].releases, [(False, False)])

    def test_multiple_commands_reuse_one_desktop_connection(self):
        target = AedtTarget("port", 50051)

        self.backend.execute(target, "ping", {})
        self.backend.execute(target, "project_info", {})

        self.assertEqual(len(self.desktops), 1)

    def test_user_close_request_uses_graceful_quit_without_release(self):
        target = AedtTarget("port", 50051)
        self.backend.execute(target, "ping", {})

        self.assertTrue(self.backend.close_for_user_request())

        self.assertEqual(self.desktops[0].quit_calls, 1)
        self.assertEqual(self.desktops[0].releases, [])
        self.assertIsNone(self.backend.session_pid)

    def test_ping_handles_project_without_design(self):
        desktop = FakeDesktop(aedt_process_id=1234)
        desktop.project.design = None
        backend = PyAedtBackend(desktop_factory=lambda **kwargs: desktop)

        result = backend.execute(AedtTarget("pid", 1234), "ping", {})

        self.assertEqual(result["active_project"], "Demo")
        self.assertIsNone(result["active_design"])

    def test_project_info_is_json_compatible(self):
        result = self.backend.execute(AedtTarget("port", 50051), "project_info", {})

        self.assertEqual(result["projects"], ["Demo"])
        self.assertEqual(result["active_project"], "Demo")
        self.assertEqual(result["active_design"], "HFSSDesign1")
        self.assertEqual(result["design_type"], "HFSS")

    def test_command_error_keeps_connection_until_explicit_release(self):
        desktop = FakeDesktop(fail_projects=True)
        backend = PyAedtBackend(desktop_factory=lambda **kwargs: desktop)

        with self.assertRaisesRegex(RuntimeError, "project lookup failed"):
            backend.execute(AedtTarget("pid", 1234), "project_info", {})

        self.assertEqual(desktop.releases, [])
        self.assertTrue(backend.release())
        self.assertEqual(desktop.releases, [(False, False)])

    def test_unknown_command_does_not_connect(self):
        with self.assertRaisesRegex(BackendCommandError, "unsupported command"):
            self.backend.execute(AedtTarget("pid", 1234), "unknown", {})

        self.assertEqual(self.desktops, [])

    def test_create_hfss_design_uses_explicit_names_and_solution_mapping(self):
        result = self.backend.execute(
            AedtTarget("port", 50051),
            "create_hfss_design",
            {
                "project_name": "FilterProject",
                "design_name": "FilterDesign",
                "solution_type": "DrivenModal",
            },
        )

        app = self.apps[0]
        self.assertEqual(app.kwargs["project"], "FilterProject")
        self.assertEqual(app.kwargs["design"], "FilterDesign")
        self.assertEqual(app.kwargs["solution_type"], "Modal")
        self.assertEqual(result["project_name"], "FilterProject")
        self.assertEqual(result["design_name"], "FilterDesign")
        self.assertEqual(app.desktop_class.releases, [])

    def test_hfss_commands_reject_missing_project_or_design_before_connect(self):
        for command, arguments in (
            ("create_hfss_design", {"project_name": "P"}),
            ("start_analysis", {"project_name": "P", "design_name": "D"}),
            ("analysis_status", {"project_name": "P"}),
        ):
            with self.subTest(command=command):
                with self.assertRaises(BackendCommandError):
                    self.backend.execute(AedtTarget("pid", 1234), command, arguments)
        self.assertEqual(self.apps, [])

    def test_save_project_uses_active_project_and_optional_path(self):
        result = self.backend.execute(
            AedtTarget("pid", 1234),
            "save_project",
            {"path": "C:/temp/demo.aedt"},
        )

        self.assertTrue(result["saved"])
        self.assertEqual(self.desktops[0].saved, [("Demo", "C:/temp/demo.aedt")])

    def test_close_projects_only_closes_explicit_existing_names(self):
        desktop = FakeDesktop(aedt_process_id=15488)
        desktop.projects = ["Keep", "Old1", "Old2"]
        backend = PyAedtBackend(desktop_factory=lambda **kwargs: desktop)

        result = backend.execute(
            AedtTarget("pid", 15488),
            "close_projects",
            {"project_names": ["Old1", "Missing", "Old2"], "save": False},
        )

        self.assertEqual(desktop.closed, ["Old1", "Old2"])
        self.assertEqual(result["closed"], ["Old1", "Old2"])
        self.assertEqual(result["not_found"], ["Missing"])
        self.assertEqual(result["remaining"], ["Keep"])
        self.assertFalse(result["saved_before_close"])

    def test_start_analysis_is_non_blocking(self):
        result = self.backend.execute(
            AedtTarget("port", 50051),
            "start_analysis",
            {
                "project_name": "Demo",
                "design_name": "HFSSDesign1",
                "setup_name": "Setup1",
                "blocking": False,
            },
        )

        self.assertTrue(result["started"])
        self.assertEqual(self.apps[0].analysis_calls, [("Setup1", False)])
        self.assertEqual(self.apps[0].desktop_class.releases, [])

    def test_analysis_status_reports_running_state_and_setups(self):
        result = self.backend.execute(
            AedtTarget("pid", 1234),
            "analysis_status",
            {"project_name": "Demo", "design_name": "HFSSDesign1"},
        )

        self.assertFalse(result["running"])
        self.assertEqual(result["setups"], ["Setup1"])
        self.assertEqual(result["project_name"], "Demo")
        self.assertEqual(result["design_name"], "HFSSDesign1")

    def test_repeated_hfss_commands_reuse_application_wrapper(self):
        target = AedtTarget("port", 50051)
        arguments = {"project_name": "Demo", "design_name": "HFSSDesign1"}

        self.backend.execute(target, "analysis_status", arguments)
        self.backend.execute(target, "analysis_status", arguments)

        self.assertEqual(len(self.apps), 1)

    def test_wr90_command_runs_builder_in_bound_hfss_session(self):
        result = self.backend.execute(
            AedtTarget("port", 50051),
            "build_wr90_waveguide",
            {
                "project_name": "Classic_WR90_Waveguide",
                "design_name": "WR90_TE10",
                "output_dir": "C:/temp/wr90",
                "solve": True,
            },
        )

        self.assertTrue(result["success"])
        self.assertEqual(self.apps[0].kwargs["solution_type"], "Modal")
        self.assertEqual(self.wr90_calls[0][1], "C:/temp/wr90")
        self.assertTrue(self.wr90_calls[0][2])


if __name__ == "__main__":
    unittest.main()
