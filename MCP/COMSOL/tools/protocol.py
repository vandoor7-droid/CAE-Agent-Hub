from __future__ import annotations

import json
import uuid
from typing import Any, TextIO


class ProtocolError(RuntimeError):
    """Raised when the COMSOL bridge returns malformed protocol data."""


def make_request(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "method": method,
        "params": dict(params or {}),
    }


def write_message(stream: TextIO, payload: dict[str, Any]) -> None:
    stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    stream.flush()


def read_message(stream: TextIO) -> dict[str, Any]:
    line = stream.readline()
    if not line:
        raise ProtocolError("bridge closed before a complete message was received")
    message = json.loads(line)
    if not isinstance(message, dict):
        raise ProtocolError("protocol message must be a JSON object")
    return message


def unwrap_response(response: dict[str, Any], request_id: str) -> dict[str, Any]:
    if response.get("id") != request_id:
        raise ProtocolError("COMSOL bridge returned a mismatched response id")
    if not response.get("ok", False):
        error = response.get("error") or {}
        if isinstance(error, dict):
            raise RuntimeError(error.get("message") or json.dumps(error, ensure_ascii=False))
        raise RuntimeError(str(error))
    result = response.get("result")
    if not isinstance(result, dict):
        raise ProtocolError("COMSOL bridge returned an invalid result envelope")
    return result
