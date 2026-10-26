from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import time

import psutil

from aedt_launcher import AedtLauncher
from aedt_target import AedtTarget
from worker_client import WorkerClient


BUSY_DIALOG_TEXT = "being used by another application, script or extension wizard"


def _window_text(hwnd: int) -> str:
    user32 = ctypes.windll.user32
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, len(buffer))
    return buffer.value


def _window_handles_and_texts(pid: int) -> tuple[list[int], list[str]]:
    user32 = ctypes.windll.user32
    handles: list[int] = []
    texts: list[str] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def child_callback(hwnd, _):
        text = _window_text(hwnd)
        if text:
            texts.append(text)
        return True

    @callback_type
    def top_callback(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            handles.append(int(hwnd))
            text = _window_text(hwnd)
            if text:
                texts.append(text)
            user32.EnumChildWindows(hwnd, child_callback, 0)
        return True

    user32.EnumWindows(top_callback, 0)
    return handles, texts


def normal_close_while_connected(pid: int, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + 10.0
    handles: list[int] = []
    while time.monotonic() < deadline and psutil.pid_exists(pid):
        handles, _ = _window_handles_and_texts(pid)
        visible = [handle for handle in handles if ctypes.windll.user32.IsWindowVisible(handle)]
        if visible:
            handles = visible
            break
        time.sleep(0.25)
    if not handles:
        raise RuntimeError(f"AEDT PID {pid} has no top-level window while broker is connected")

    ctypes.windll.user32.PostMessageW(handles[0], 0x0010, 0, 0)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not psutil.pid_exists(pid):
            return
        _, texts = _window_handles_and_texts(pid)
        if BUSY_DIALOG_TEXT in "\n".join(texts):
            raise RuntimeError(f"AEDT busy dialog detected for PID {pid}")
        time.sleep(0.25)
    raise RuntimeError(f"AEDT PID {pid} did not exit after normal close")


def run_operations(target: AedtTarget, client: WorkerClient, artifacts: Path) -> dict:
    probes = [client.execute(target, "ping", {}, timeout=30) for _ in range(10)]
    created = client.execute(
        target,
        "create_hfss_design",
        {
            "project_name": f"McpAcceptance{target.kind.title()}",
            "design_name": "McpAcceptanceHFSS",
            "solution_type": "DrivenModal",
        },
        timeout=60,
    )
    project_path = artifacts / f"McpAcceptance{target.kind.title()}.aedt"
    saved = client.execute(target, "save_project", {"path": str(project_path)}, timeout=60)
    return {
        "probe_count": len(probes),
        "all_connected": all(item.get("connected") for item in probes),
        "created": created,
        "saved": saved,
        "project_path": str(project_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("grpc", "pid"), required=True)
    parser.add_argument("--aedt-root", required=True)
    parser.add_argument("--port", type=int, default=50061)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.result.parent
    artifacts.mkdir(parents=True, exist_ok=True)
    client = WorkerClient(log_dir=artifacts / "logs")
    if args.mode == "grpc":
        session = AedtLauncher(worker_client=client).launch(
            install_dir=args.aedt_root,
            port=args.port,
            timeout=120,
        )
        target = AedtTarget("port", session["port"])
    else:
        session = AedtLauncher(worker_client=client).launch(
            install_dir=args.aedt_root,
            port=args.port + 1,
            timeout=120,
        )
        session["connection_mode"] = "pid"
        target = AedtTarget("pid", session["pid"])

    try:
        result = {"session": session, "operations": run_operations(target, client, artifacts)}
        args.result.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        normal_close_while_connected(session["pid"])
        result["normal_close_while_connected"] = True
        args.result.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
        return 0
    finally:
        client.close_all()


if __name__ == "__main__":
    raise SystemExit(main())
