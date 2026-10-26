from __future__ import annotations

import json
import os
import socket
from typing import Any


DEFAULT_HOST = os.environ.get("WORKBENCH_MCP_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("WORKBENCH_MCP_PORT", "9885"))


def _request(payload: dict[str, Any], timeout: float = 10.0) -> dict[str, Any]:
    data = (json.dumps(payload, ensure_ascii=False) + "\0").encode("utf-8")
    received = b""
    try:
        with socket.create_connection((DEFAULT_HOST, DEFAULT_PORT), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(data)
            while b"\0" not in received:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                received += chunk
        if not received:
            return {"ok": False, "connected": True, "error": "No response from Workbench MCP socket timer"}
        return {
            "ok": True,
            "connected": True,
            "host": DEFAULT_HOST,
            "port": DEFAULT_PORT,
            "response": json.loads(received.split(b"\0", 1)[0].decode("utf-8", errors="replace")),
        }
    except Exception as exc:
        return {
            "ok": False,
            "connected": False,
            "host": DEFAULT_HOST,
            "port": DEFAULT_PORT,
            "error": str(exc),
            "hint": "Open Mechanical and start Workbench MCP > Socket Timer Start, or enable plugin auto-start.",
        }


def socket_timer_ping(timeout: float = 10.0) -> dict[str, Any]:
    return _request({"action": "ping"}, timeout=timeout)


def socket_timer_state(timeout: float = 10.0) -> dict[str, Any]:
    return _request({"action": "state"}, timeout=timeout)


def socket_timer_execute_python(code: str, timeout: float = 60.0) -> dict[str, Any]:
    return _request({"action": "execute_python", "code": code}, timeout=timeout)


def socket_timer_stop(timeout: float = 10.0) -> dict[str, Any]:
    return _request({"action": "stop"}, timeout=timeout)
