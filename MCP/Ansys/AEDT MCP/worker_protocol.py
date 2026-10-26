from collections.abc import Mapping
from dataclasses import dataclass
import json
import math
from typing import Any
import uuid

from aedt_target import AedtTarget, TargetValidationError


class WorkerProtocolError(ValueError):
    pass


_REQUEST_FIELDS = {
    "request_id",
    "command",
    "target",
    "arguments",
    "timeout_seconds",
}
_RESPONSE_FIELDS = {"request_id", "ok", "result", "error"}
_ERROR_REQUIRED_FIELDS = {"code", "message"}
_ERROR_OPTIONAL_FIELDS = {"detail"}


def _require_exact_fields(payload: Mapping[str, Any], expected: set[str], name: str) -> None:
    fields = set(payload)
    unknown = fields - expected
    missing = expected - fields
    if unknown:
        raise WorkerProtocolError(
            f"{name} contains unknown fields: {', '.join(sorted(map(str, unknown)))}"
        )
    if missing:
        raise WorkerProtocolError(
            f"{name} is missing fields: {', '.join(sorted(missing))}"
        )


def _require_non_empty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise WorkerProtocolError(f"{name} must be a non-empty string")
    return value


def _validate_json_compatible(value: Any, name: str) -> None:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise WorkerProtocolError(f"{name} is not JSON-compatible: {exc}") from exc

    def validate(item: Any, path: str) -> None:
        if item is None or type(item) in {bool, int, str}:
            return
        if type(item) is float:
            if not math.isfinite(item):
                raise WorkerProtocolError(
                    f"{name} is not JSON-compatible: {path} must be finite"
                )
            return
        if isinstance(item, list):
            for index, child in enumerate(item):
                validate(child, f"{path}[{index}]")
            return
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str):
                    raise WorkerProtocolError(
                        f"{name} is not JSON-compatible: object keys must be strings"
                    )
                validate(child, f"{path}.{key}")
            return
        raise WorkerProtocolError(
            f"{name} is not JSON-compatible: unsupported {type(item).__name__} value at {path}"
        )

    validate(value, name)


def _normalize_target(target: Any) -> AedtTarget:
    if isinstance(target, AedtTarget):
        return target
    if not isinstance(target, Mapping):
        raise WorkerProtocolError("target must be an object with kind and value")

    _require_exact_fields(target, {"kind", "value"}, "target")
    if not isinstance(target["kind"], str):
        raise WorkerProtocolError("invalid target: kind must be a string")
    try:
        return AedtTarget(kind=target["kind"], value=target["value"])
    except TargetValidationError as exc:
        raise WorkerProtocolError(f"invalid target: {exc}") from exc


def _parse_json(payload: Any, name: str) -> dict[str, Any]:
    if not isinstance(payload, str):
        raise WorkerProtocolError(f"{name} JSON must be a string")
    try:
        value = json.loads(payload, parse_constant=lambda token: _reject_constant(token, name))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        if isinstance(exc, WorkerProtocolError):
            raise
        raise WorkerProtocolError(f"invalid {name} JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise WorkerProtocolError(f"{name} JSON must contain an object")
    return value


def _reject_constant(token: str, name: str) -> None:
    raise WorkerProtocolError(f"invalid {name} JSON: {token} is not permitted")


def _to_json(payload: dict[str, Any], name: str) -> str:
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise WorkerProtocolError(f"{name} is not JSON-compatible: {exc}") from exc


@dataclass(frozen=True)
class WorkerRequest:
    request_id: str
    command: str
    target: AedtTarget
    arguments: dict[str, Any]
    timeout_seconds: int | float

    def __post_init__(self) -> None:
        _require_non_empty_string(self.request_id, "request_id")
        _require_non_empty_string(self.command, "command")
        if not isinstance(self.target, AedtTarget):
            raise WorkerProtocolError("target must be an AedtTarget")
        if not isinstance(self.arguments, dict):
            raise WorkerProtocolError("arguments must be an object")
        _validate_json_compatible(self.arguments, "arguments")
        timeout_type = type(self.timeout_seconds)
        invalid_timeout = timeout_type not in {int, float}
        if timeout_type is int:
            invalid_timeout = self.timeout_seconds <= 0
        elif timeout_type is float:
            invalid_timeout = (
                not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0
            )
        if invalid_timeout:
            raise WorkerProtocolError(
                "timeout_seconds must be a finite positive number and not a boolean"
            )

    @classmethod
    def create(
        cls,
        command: str,
        target: AedtTarget | Mapping[str, Any],
        arguments: dict[str, Any],
        timeout_seconds: int | float,
    ) -> "WorkerRequest":
        return cls(
            request_id=str(uuid.uuid4()),
            command=command,
            target=_normalize_target(target),
            arguments=arguments,
            timeout_seconds=timeout_seconds,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "command": self.command,
            "target": {"kind": self.target.kind, "value": self.target.value},
            "arguments": self.arguments,
            "timeout_seconds": self.timeout_seconds,
        }

    def to_json(self) -> str:
        return _to_json(self.to_dict(), "worker request")

    @classmethod
    def from_dict(cls, payload: Any) -> "WorkerRequest":
        if not isinstance(payload, dict):
            raise WorkerProtocolError("worker request must be an object")
        _require_exact_fields(payload, _REQUEST_FIELDS, "worker request")
        return cls(
            request_id=payload["request_id"],
            command=payload["command"],
            target=_normalize_target(payload["target"]),
            arguments=payload["arguments"],
            timeout_seconds=payload["timeout_seconds"],
        )

    @classmethod
    def from_json(cls, payload: Any) -> "WorkerRequest":
        return cls.from_dict(_parse_json(payload, "worker request"))


@dataclass(frozen=True)
class WorkerResponse:
    request_id: str
    ok: bool
    result: Any
    error: dict[str, Any] | None

    def __post_init__(self) -> None:
        _require_non_empty_string(self.request_id, "request_id")
        if type(self.ok) is not bool:
            raise WorkerProtocolError("ok must be a boolean")

        if self.ok:
            if self.error is not None:
                raise WorkerProtocolError("successful response must not contain an error")
            _validate_json_compatible(self.result, "result")
            return

        if self.result is not None:
            raise WorkerProtocolError("failed response must not contain a result")
        self._validate_error(self.error)

    @staticmethod
    def _validate_error(error: Any) -> None:
        if not isinstance(error, dict):
            raise WorkerProtocolError("failed response error must be an object")
        allowed = _ERROR_REQUIRED_FIELDS | _ERROR_OPTIONAL_FIELDS
        fields = set(error)
        unknown = fields - allowed
        missing = _ERROR_REQUIRED_FIELDS - fields
        if unknown:
            raise WorkerProtocolError(
                "error contains unknown fields: " + ", ".join(sorted(map(str, unknown)))
            )
        if missing:
            raise WorkerProtocolError(
                "error is missing fields: " + ", ".join(sorted(missing))
            )
        _require_non_empty_string(error["code"], "error code")
        _require_non_empty_string(error["message"], "error message")
        if "detail" in error:
            _validate_json_compatible(error["detail"], "error detail")

    @classmethod
    def success(cls, request_id: str, result: Any) -> "WorkerResponse":
        return cls(request_id=request_id, ok=True, result=result, error=None)

    @classmethod
    def failure(
        cls,
        request_id: str,
        code: str,
        message: str,
        detail: Any = None,
    ) -> "WorkerResponse":
        error = {"code": code, "message": message}
        if detail is not None:
            error["detail"] = detail
        return cls(request_id=request_id, ok=False, result=None, error=error)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "ok": self.ok,
            "result": self.result,
            "error": self.error,
        }

    def to_json(self) -> str:
        return _to_json(self.to_dict(), "worker response")

    @classmethod
    def from_dict(cls, payload: Any) -> "WorkerResponse":
        if not isinstance(payload, dict):
            raise WorkerProtocolError("worker response must be an object")
        _require_exact_fields(payload, _RESPONSE_FIELDS, "worker response")
        return cls(
            request_id=payload["request_id"],
            ok=payload["ok"],
            result=payload["result"],
            error=payload["error"],
        )

    @classmethod
    def from_json(cls, payload: Any) -> "WorkerResponse":
        return cls.from_dict(_parse_json(payload, "worker response"))
