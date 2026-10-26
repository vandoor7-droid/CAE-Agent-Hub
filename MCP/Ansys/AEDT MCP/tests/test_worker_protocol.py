from dataclasses import FrozenInstanceError
import json
import math
import unittest
import uuid

from aedt_target import AedtTarget
from worker_protocol import (
    WorkerProtocolError,
    WorkerRequest,
    WorkerResponse,
)


class WorkerRequestTests(unittest.TestCase):
    def test_request_round_trip_normalizes_target_mapping(self):
        request = WorkerRequest.create(
            command="project.info",
            target={"kind": "pid", "value": 4321},
            arguments={"include_designs": True},
            timeout_seconds=15,
        )

        restored = WorkerRequest.from_json(request.to_json())

        self.assertEqual(restored, request)
        self.assertEqual(restored.target, AedtTarget(kind="pid", value=4321))
        self.assertEqual(
            restored.to_dict(),
            {
                "request_id": request.request_id,
                "command": "project.info",
                "target": {"kind": "pid", "value": 4321},
                "arguments": {"include_designs": True},
                "timeout_seconds": 15,
            },
        )

    def test_request_accepts_aedt_target_and_preserves_unicode(self):
        request = WorkerRequest.create(
            command="design.rename",
            target=AedtTarget(kind="port", value=50051),
            arguments={"name": "天线设计"},
            timeout_seconds=2.5,
        )

        payload = request.to_json()

        self.assertIn("天线设计", payload)
        self.assertNotIn("\\u", payload)
        self.assertNotIn("\n", payload)
        self.assertNotIn(": ", payload)
        self.assertEqual(WorkerRequest.from_json(payload), request)

    def test_create_generates_uuid_request_id(self):
        request = WorkerRequest.create(
            command="ping",
            target={"kind": "pid", "value": 1},
            arguments={},
            timeout_seconds=1,
        )

        parsed = uuid.UUID(request.request_id)

        self.assertEqual(parsed.version, 4)
        self.assertEqual(str(parsed), request.request_id)

    def test_request_is_immutable(self):
        request = WorkerRequest.create(
            command="ping",
            target={"kind": "pid", "value": 1},
            arguments={},
            timeout_seconds=1,
        )

        with self.assertRaises(FrozenInstanceError):
            request.command = "other"

    def test_request_rejects_malformed_json(self):
        with self.assertRaisesRegex(WorkerProtocolError, "invalid worker request JSON"):
            WorkerRequest.from_json("{")

    def test_request_rejects_unknown_and_missing_fields(self):
        valid = self._valid_request_dict()
        cases = {
            "unknown": {**valid, "extra": True},
            "missing": {key: value for key, value in valid.items() if key != "command"},
        }

        for name, payload in cases.items():
            with self.subTest(name=name):
                with self.assertRaisesRegex(WorkerProtocolError, name):
                    WorkerRequest.from_dict(payload)

    def test_request_requires_non_empty_request_id_and_command(self):
        for field, value in (
            ("request_id", ""),
            ("request_id", 123),
            ("command", ""),
            ("command", None),
        ):
            with self.subTest(field=field, value=value):
                payload = self._valid_request_dict()
                payload[field] = value
                with self.assertRaisesRegex(WorkerProtocolError, field):
                    WorkerRequest.from_dict(payload)

    def test_request_rejects_bad_target(self):
        for target in (
            "pid:123",
            {"kind": "pid"},
            {"kind": "pid", "value": 123, "extra": True},
            {"kind": [], "value": 123},
            {"kind": "process", "value": 123},
            {"kind": "port", "value": 65536},
        ):
            with self.subTest(target=target):
                payload = self._valid_request_dict()
                payload["target"] = target
                with self.assertRaisesRegex(WorkerProtocolError, "target"):
                    WorkerRequest.from_dict(payload)

    def test_request_rejects_non_object_arguments(self):
        for arguments in (None, [], "value", 1):
            with self.subTest(arguments=arguments):
                payload = self._valid_request_dict()
                payload["arguments"] = arguments
                with self.assertRaisesRegex(WorkerProtocolError, "arguments"):
                    WorkerRequest.from_dict(payload)

    def test_request_rejects_invalid_timeout(self):
        for timeout in (0, -1, True, math.nan, math.inf, -math.inf, "1"):
            with self.subTest(timeout=timeout):
                payload = self._valid_request_dict()
                payload["timeout_seconds"] = timeout
                with self.assertRaisesRegex(WorkerProtocolError, "timeout_seconds"):
                    WorkerRequest.from_dict(payload)

    def test_request_accepts_arbitrarily_large_positive_integer_timeout(self):
        payload = self._valid_request_dict()
        payload["timeout_seconds"] = 10**1000

        request = WorkerRequest.from_dict(payload)

        self.assertEqual(request.timeout_seconds, 10**1000)

    def test_request_rejects_non_json_argument_values(self):
        for value in ({1, 2}, object(), math.nan, math.inf):
            with self.subTest(value=repr(value)):
                payload = self._valid_request_dict()
                payload["arguments"] = {"value": value}
                with self.assertRaisesRegex(WorkerProtocolError, "arguments"):
                    WorkerRequest.from_dict(payload)

    @staticmethod
    def _valid_request_dict():
        return {
            "request_id": "request-1",
            "command": "ping",
            "target": {"kind": "pid", "value": 123},
            "arguments": {},
            "timeout_seconds": 1.0,
        }


class WorkerResponseTests(unittest.TestCase):
    def test_success_round_trip(self):
        response = WorkerResponse.success(
            "request-1", {"design": "天线", "values": [1, 2, 3]}
        )

        payload = response.to_json()
        restored = WorkerResponse.from_json(payload)

        self.assertIn("天线", payload)
        self.assertEqual(restored, response)
        self.assertEqual(
            restored.to_dict(),
            {
                "request_id": "request-1",
                "ok": True,
                "result": {"design": "天线", "values": [1, 2, 3]},
                "error": None,
            },
        )

    def test_failure_round_trip_with_code_message_and_detail(self):
        response = WorkerResponse.failure(
            "request-2",
            code="AEDT_ATTACH_FAILED",
            message="Could not attach",
            detail={"pid": 4321},
        )

        restored = WorkerResponse.from_dict(response.to_dict())

        self.assertEqual(restored, response)
        self.assertEqual(
            response.error,
            {
                "code": "AEDT_ATTACH_FAILED",
                "message": "Could not attach",
                "detail": {"pid": 4321},
            },
        )
        self.assertIsNone(response.result)

    def test_failure_omits_absent_detail(self):
        response = WorkerResponse.failure(
            "request-3", code="TIMEOUT", message="Worker timed out"
        )

        self.assertEqual(
            response.error,
            {"code": "TIMEOUT", "message": "Worker timed out"},
        )

    def test_response_is_immutable(self):
        response = WorkerResponse.success("request-1", {})

        with self.assertRaises(FrozenInstanceError):
            response.ok = False

    def test_response_rejects_malformed_json(self):
        with self.assertRaisesRegex(WorkerProtocolError, "invalid worker response JSON"):
            WorkerResponse.from_json("not-json")

    def test_response_rejects_unknown_and_missing_fields(self):
        valid = WorkerResponse.success("request-1", {}).to_dict()
        cases = {
            "unknown": {**valid, "extra": True},
            "missing": {key: value for key, value in valid.items() if key != "error"},
        }

        for name, payload in cases.items():
            with self.subTest(name=name):
                with self.assertRaisesRegex(WorkerProtocolError, name):
                    WorkerResponse.from_dict(payload)

    def test_response_rejects_invalid_states(self):
        cases = (
            {
                "request_id": "request-1",
                "ok": True,
                "result": {},
                "error": {"code": "BAD", "message": "bad"},
            },
            {
                "request_id": "request-1",
                "ok": False,
                "result": {},
                "error": {"code": "BAD", "message": "bad"},
            },
            {
                "request_id": "request-1",
                "ok": False,
                "result": None,
                "error": None,
            },
            {
                "request_id": "request-1",
                "ok": 1,
                "result": None,
                "error": None,
            },
        )

        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(WorkerProtocolError):
                    WorkerResponse.from_dict(payload)

    def test_response_rejects_invalid_error_shape(self):
        for error in (
            "failure",
            {"message": "bad"},
            {"code": "BAD"},
            {"code": "", "message": "bad"},
            {"code": "BAD", "message": ""},
            {"code": "BAD", "message": "bad", "extra": True},
        ):
            with self.subTest(error=error):
                payload = {
                    "request_id": "request-1",
                    "ok": False,
                    "result": None,
                    "error": error,
                }
                with self.assertRaisesRegex(WorkerProtocolError, "error"):
                    WorkerResponse.from_dict(payload)

    def test_response_rejects_non_json_result_and_detail(self):
        for payload in (
            {
                "request_id": "request-1",
                "ok": True,
                "result": object(),
                "error": None,
            },
            {
                "request_id": "request-1",
                "ok": False,
                "result": None,
                "error": {"code": "BAD", "message": "bad", "detail": math.nan},
            },
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(WorkerProtocolError):
                    WorkerResponse.from_dict(payload)

    def test_to_json_wraps_non_json_values_in_protocol_error(self):
        response = object.__new__(WorkerResponse)
        object.__setattr__(response, "request_id", "request-1")
        object.__setattr__(response, "ok", True)
        object.__setattr__(response, "result", math.inf)
        object.__setattr__(response, "error", None)

        with self.assertRaisesRegex(WorkerProtocolError, "not JSON-compatible"):
            response.to_json()

    def test_response_requires_non_empty_request_id(self):
        payload = WorkerResponse.success("request-1", {}).to_dict()
        payload["request_id"] = ""

        with self.assertRaisesRegex(WorkerProtocolError, "request_id"):
            WorkerResponse.from_dict(payload)


if __name__ == "__main__":
    unittest.main()
