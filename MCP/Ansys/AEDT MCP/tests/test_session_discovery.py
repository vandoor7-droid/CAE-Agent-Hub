from collections import namedtuple
import unittest

from session_discovery import SessionDiscovery


Address = namedtuple("Address", "ip port")
Connection = namedtuple("Connection", "pid status laddr")


class FakeProcess:
    def __init__(self, info):
        self.info = info


class FakeWorkerClient:
    def __init__(self):
        self.calls = []

    def execute(self, target, command, arguments, timeout=None):
        self.calls.append((target, command, arguments, timeout))
        return {"connected": True, "target": target.key}


class SessionDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.processes = [
            FakeProcess(
                {
                    "pid": 200,
                    "name": "ansysedt.exe",
                    "exe": r"G:\ANSYS206\ANSYS Inc\v261\AnsysEM\ansysedt.exe",
                    "create_time": 2000.0,
                }
            ),
            FakeProcess(
                {
                    "pid": 100,
                    "name": "ANSYSEDT.EXE",
                    "exe": r"G:\ANSYS206\ANSYS Inc\v261\AnsysEM\ansysedt.exe",
                    "create_time": 1000.0,
                }
            ),
            FakeProcess(
                {
                    "pid": 300,
                    "name": "python.exe",
                    "exe": r"C:\Python\python.exe",
                    "create_time": 3000.0,
                }
            ),
        ]
        self.connections = [
            Connection(200, "LISTEN", Address("127.0.0.1", 50052)),
            Connection(200, "ESTABLISHED", Address("127.0.0.1", 12345)),
            Connection(100, "LISTEN", Address("0.0.0.0", 50051)),
            Connection(300, "LISTEN", Address("127.0.0.1", 9000)),
            Connection(None, "LISTEN", Address("127.0.0.1", 7000)),
        ]
        self.worker = FakeWorkerClient()
        self.discovery = SessionDiscovery(
            process_iter=lambda attrs: iter(self.processes),
            net_connections=lambda kind: list(self.connections),
            worker_client=self.worker,
        )

    def test_lists_only_aedt_processes_with_stable_order(self):
        sessions = self.discovery.list_sessions()

        self.assertEqual([item["pid"] for item in sessions], [100, 200])
        self.assertEqual(sessions[0]["version"], "2026.1")
        self.assertEqual(sessions[0]["listening_ports"], [50051])
        self.assertEqual(sessions[1]["listening_ports"], [50052])
        self.assertNotIn("selected", sessions[0])
        self.assertNotIn("default", sessions[0])
        self.assertEqual(self.worker.calls, [])

    def test_access_denied_or_missing_process_fields_do_not_abort_discovery(self):
        processes = [
            FakeProcess({"pid": 7, "name": "ansysedt.exe", "exe": None, "create_time": None}),
            FakeProcess({"pid": None, "name": None, "exe": None, "create_time": None}),
        ]
        discovery = SessionDiscovery(
            process_iter=lambda attrs: iter(processes),
            net_connections=lambda kind: [],
            worker_client=self.worker,
        )

        sessions = discovery.list_sessions()

        self.assertEqual(sessions, [{
            "pid": 7,
            "version": None,
            "executable": None,
            "started_at": None,
            "listening_ports": [],
        }])

    def test_probe_requires_explicit_target_and_uses_worker(self):
        result = self.discovery.probe_session(pid=100, timeout=3.0)

        self.assertTrue(result["connected"])
        target, command, arguments, timeout = self.worker.calls[0]
        self.assertEqual(target.key, "pid:100")
        self.assertEqual(command, "ping")
        self.assertEqual(arguments, {})
        self.assertEqual(timeout, 3.0)

    def test_probe_by_port_never_selects_a_process_implicitly(self):
        result = self.discovery.probe_session(port=50051)

        self.assertEqual(result["target"], "port:50051")
        self.assertEqual(self.worker.calls[0][0].key, "port:50051")

    def test_probe_rejects_missing_or_double_target(self):
        for values in ({}, {"pid": 100, "port": 50051}):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    self.discovery.probe_session(**values)


if __name__ == "__main__":
    unittest.main()
