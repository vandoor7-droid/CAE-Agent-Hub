from __future__ import annotations

import json
import os
import socket
import time
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
QUEUE_ROOT = Path(os.environ.get("WORKBENCH_MCP_QUEUE_ROOT", ROOT / "workbench_queue"))
REQUEST_DIR = QUEUE_ROOT / "requests"
RESPONSE_DIR = QUEUE_ROOT / "responses"
ARCHIVE_DIR = QUEUE_ROOT / "archive"
PROCESSOR_SCRIPT = ROOT / "workbench_plugin" / "mechanical_queue_processor.py"
SOCKET_HOST = os.environ.get("WORKBENCH_MCP_HOST", "127.0.0.1")
SOCKET_PORT = int(os.environ.get("WORKBENCH_MCP_PORT", "9885"))


def _ensure_dirs() -> None:
    for path in (QUEUE_ROOT, REQUEST_DIR, RESPONSE_DIR, ARCHIVE_DIR):
        path.mkdir(parents=True, exist_ok=True)


def queue_install_info() -> dict[str, Any]:
    _ensure_dirs()
    return {
        "queue_root": str(QUEUE_ROOT),
        "request_dir": str(REQUEST_DIR),
        "response_dir": str(RESPONSE_DIR),
        "processor_script": str(PROCESSOR_SCRIPT),
        "mechanical_step": "In Mechanical: Automation > Scripting > Run Script > mechanical_queue_processor.py",
        "mode": "file_queue_main_thread_once",
        "safety": "No socket, no background thread, no long-running loop inside Mechanical.",
    }


def submit_request(action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    _ensure_dirs()
    request_id = uuid.uuid4().hex
    request = {
        "id": request_id,
        "action": action,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if payload:
        request.update(payload)
    path = REQUEST_DIR / f"{request_id}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return {
        "ok": True,
        "request_id": request_id,
        "request_path": str(path),
        "response_path": str(RESPONSE_DIR / f"{request_id}.json"),
        "next_step": f"Run {PROCESSOR_SCRIPT} inside Mechanical to process the queue.",
    }


def trigger_socket_process_queue(timeout: float = 2.0) -> dict[str, Any]:
    request = {"action": "process_queue"}
    data = (json.dumps(request) + "\0").encode("utf-8")
    try:
        with socket.create_connection((SOCKET_HOST, SOCKET_PORT), timeout=timeout) as client:
            client.settimeout(timeout)
            client.sendall(data)
            chunks: list[bytes] = []
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
                if b"\0" in chunk:
                    break
        raw = b"".join(chunks).split(b"\0", 1)[0].decode("utf-8", errors="replace")
        return {"ok": True, "socket": f"{SOCKET_HOST}:{SOCKET_PORT}", "response": json.loads(raw) if raw else None}
    except Exception as exc:
        return {"ok": False, "socket": f"{SOCKET_HOST}:{SOCKET_PORT}", "error": str(exc)}


def read_response(request_id: str) -> dict[str, Any]:
    _ensure_dirs()
    path = RESPONSE_DIR / f"{request_id}.json"
    if not path.exists():
        return {
            "ok": False,
            "ready": False,
            "request_id": request_id,
            "response_path": str(path),
            "hint": f"Run {PROCESSOR_SCRIPT} inside Mechanical, then read this response again.",
        }
    try:
        return {
            "ok": True,
            "ready": True,
            "request_id": request_id,
            "response": json.loads(path.read_text(encoding="utf-8")),
            "response_path": str(path),
        }
    except Exception as exc:
        return {
            "ok": False,
            "ready": True,
            "request_id": request_id,
            "error": str(exc),
            "response_path": str(path),
        }


def wait_for_response(request_id: str, timeout: float = 2.0, poll_interval: float = 0.2) -> dict[str, Any]:
    deadline = time.time() + max(0.0, timeout)
    while time.time() <= deadline:
        result = read_response(request_id)
        if result.get("ready"):
            return result
        time.sleep(poll_interval)
    result = read_response(request_id)
    result["timed_out"] = True
    return result


def list_queue() -> dict[str, Any]:
    _ensure_dirs()
    return {
        "queue_root": str(QUEUE_ROOT),
        "pending": sorted(p.name for p in REQUEST_DIR.glob("*.json")),
        "responses": sorted(p.name for p in RESPONSE_DIR.glob("*.json")),
        "archive": sorted(p.name for p in ARCHIVE_DIR.glob("*.json"))[-20:],
    }


def queue_ping(wait_timeout: float = 2.0) -> dict[str, Any]:
    submitted = submit_request("ping")
    response = wait_for_response(submitted["request_id"], timeout=wait_timeout)
    return {"submitted": submitted, "response": response}


def queue_get_state(wait_timeout: float = 2.0) -> dict[str, Any]:
    submitted = submit_request("get_state")
    response = wait_for_response(submitted["request_id"], timeout=wait_timeout)
    return {"submitted": submitted, "response": response}


def queue_execute_python(code: str, wait_timeout: float = 2.0) -> dict[str, Any]:
    submitted = submit_request("execute_python", {"code": code})
    response = wait_for_response(submitted["request_id"], timeout=wait_timeout)
    return {"submitted": submitted, "response": response}


def queue_execute_python_via_socket_timer(code: str, wait_timeout: float = 2.0) -> dict[str, Any]:
    submitted = submit_request("execute_python", {"code": code})
    trigger = {
        "ok": True,
        "mode": "ui_queue_timer",
        "note": "Request submitted only. Mechanical UI timer started by Socket Timer Start should process it automatically.",
    }
    response = wait_for_response(submitted["request_id"], timeout=wait_timeout)
    return {"submitted": submitted, "trigger": trigger, "response": response}
