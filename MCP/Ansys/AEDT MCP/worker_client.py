from __future__ import annotations

import atexit
import asyncio
from dataclasses import dataclass, field
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
from typing import Any, TextIO
import uuid

from aedt_target import AedtTarget
from worker_protocol import WorkerProtocolError, WorkerRequest, WorkerResponse


class WorkerClientError(RuntimeError):
    pass


class WorkerTimeoutError(WorkerClientError):
    pass


class WorkerProcessError(WorkerClientError):
    pass


class WorkerProtocolOutputError(WorkerClientError):
    pass


class WorkerRemoteError(WorkerClientError):
    def __init__(self, code: str, message: str, detail: Any = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.detail = detail


@dataclass
class _Broker:
    process: subprocess.Popen[str]
    primary_target: AedtTarget
    responses: queue.Queue[str | None]
    reader: threading.Thread
    log_handle: TextIO
    log_path: Path
    lock: threading.Lock = field(default_factory=threading.Lock)


class WorkerClient:
    def __init__(
        self,
        *,
        worker_script: str | Path | None = None,
        python_executable: str | Path | None = None,
        log_dir: str | Path | None = None,
        default_timeout: float | None = None,
    ) -> None:
        self.worker_script = Path(worker_script or Path(__file__).with_name("pyaedt_worker.py"))
        self.python_executable = Path(python_executable or sys.executable)
        configured_log_dir = log_dir or os.environ.get("AEDT_LOG_DIR")
        self.log_dir = Path(configured_log_dir or Path(tempfile.gettempdir()) / "aedt-mcp")
        self.default_timeout = float(
            default_timeout
            if default_timeout is not None
            else os.environ.get("AEDT_WORKER_TIMEOUT", "60")
        )
        self._brokers: dict[str, _Broker] = {}
        self._brokers_guard = threading.RLock()
        self._locks: dict[str, asyncio.Lock] = {}
        self._locks_guard = threading.Lock()
        self._closed = False
        atexit.register(self.close_all)

    def execute(
        self,
        target: AedtTarget,
        command: str,
        arguments: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        effective_timeout = self.default_timeout if timeout is None else timeout
        request = WorkerRequest.create(command, target, arguments or {}, effective_timeout)
        broker = self._broker_for(target)
        with broker.lock:
            return self._exchange(broker, request, effective_timeout)

    def release(
        self,
        target: AedtTarget,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        effective_timeout = self.default_timeout if timeout is None else timeout
        with self._brokers_guard:
            broker = self._brokers.get(target.key)
        if broker is None:
            return {
                "target": {"kind": target.kind, "value": target.value},
                "released": False,
            }

        request = WorkerRequest.create("release_connection", target, {}, effective_timeout)
        try:
            with broker.lock:
                result = self._exchange(broker, request, effective_timeout)
            if not isinstance(result, dict):
                raise WorkerProtocolOutputError("AEDT broker release returned a non-object result")
            return {
                "target": {"kind": target.kind, "value": target.value},
                **result,
            }
        finally:
            self._stop_broker(broker, graceful_timeout=2.0)

    async def execute_async(
        self,
        target: AedtTarget,
        command: str,
        arguments: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        lock = self._target_lock(target.key)
        async with lock:
            return await asyncio.to_thread(
                self.execute,
                target,
                command,
                arguments,
                timeout=timeout,
            )

    async def release_async(
        self,
        target: AedtTarget,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        lock = self._target_lock(target.key)
        async with lock:
            return await asyncio.to_thread(self.release, target, timeout=timeout)

    def close_all(self) -> None:
        with self._brokers_guard:
            brokers = list({id(item): item for item in self._brokers.values()}.values())
        for broker in brokers:
            try:
                self.release(broker.primary_target, timeout=min(self.default_timeout, 5.0))
            except Exception:
                self._stop_broker(broker, graceful_timeout=0.5)
        self._closed = True

    def _broker_for(self, target: AedtTarget) -> _Broker:
        with self._brokers_guard:
            broker = self._brokers.get(target.key)
            if broker is not None and broker.process.poll() is None:
                return broker
            if broker is not None:
                self._discard_broker(broker)
            broker = self._start_broker(target)
            self._brokers[target.key] = broker
            self._closed = False
            return broker

    def _start_broker(self, target: AedtTarget) -> _Broker:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        safe_target = target.key.replace(":", "-")
        log_path = self.log_dir / f"broker-{safe_target}-{uuid.uuid4()}.log"
        log_handle = log_path.open("a", encoding="utf-8")
        process = subprocess.Popen(
            [str(self.python_executable), str(self.worker_script), "--serve"],
            cwd=str(self.worker_script.parent),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=log_handle,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=self._worker_environment(),
            creationflags=self._creation_flags(),
        )
        responses: queue.Queue[str | None] = queue.Queue()

        def read_responses() -> None:
            assert process.stdout is not None
            try:
                for line in process.stdout:
                    responses.put(line)
            finally:
                responses.put(None)

        reader = threading.Thread(
            target=read_responses,
            name=f"aedt-broker-reader-{process.pid}",
            daemon=True,
        )
        reader.start()
        return _Broker(process, target, responses, reader, log_handle, log_path)

    def _exchange(
        self,
        broker: _Broker,
        request: WorkerRequest,
        timeout: float,
    ) -> Any:
        process = broker.process
        if process.poll() is not None or process.stdin is None:
            self._discard_broker(broker)
            raise WorkerProcessError(
                f"AEDT broker exited before request for {request.target.key}; log: {broker.log_path}"
            )
        try:
            process.stdin.write(request.to_json() + "\n")
            process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            self._stop_broker(broker, graceful_timeout=0)
            raise WorkerProcessError(
                f"AEDT broker pipe closed for {request.target.key}; log: {broker.log_path}"
            ) from exc

        try:
            line = broker.responses.get(timeout=timeout)
        except queue.Empty as exc:
            self._stop_broker(broker, graceful_timeout=0.5)
            raise WorkerTimeoutError(
                f"AEDT broker timed out after {timeout:g}s for {request.target.key}"
            ) from exc
        if line is None:
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                self._stop_broker(broker, graceful_timeout=0)
            returncode = process.returncode
            self._discard_broker(broker)
            raise WorkerProcessError(
                f"AEDT broker exited with code {returncode}; log: {broker.log_path}"
            )

        try:
            extra = broker.responses.get(timeout=0.02)
        except queue.Empty:
            extra = None
        if extra is not None:
            self._stop_broker(broker, graceful_timeout=0.5)
            raise WorkerProtocolOutputError(
                "AEDT broker must emit exactly one JSON response line per request"
            )

        try:
            response = WorkerResponse.from_json(line.strip())
        except WorkerProtocolError as exc:
            self._stop_broker(broker, graceful_timeout=0.5)
            raise WorkerProtocolOutputError(f"invalid AEDT broker response: {exc}") from exc
        if response.request_id != request.request_id:
            self._stop_broker(broker, graceful_timeout=0.5)
            raise WorkerProtocolOutputError("AEDT broker response request_id does not match")
        if not response.ok:
            error = response.error or {}
            raise WorkerRemoteError(
                str(error.get("code", "worker_error")),
                str(error.get("message", "AEDT broker failed")),
                error.get("detail"),
            )

        self._register_aliases(broker, response.result)
        return response.result

    def _register_aliases(self, broker: _Broker, result: Any) -> None:
        if not isinstance(result, dict):
            return
        aliases = []
        pid = result.get("pid")
        port = result.get("port")
        if type(pid) is int and pid > 0:
            aliases.append(f"pid:{pid}")
        if type(port) is int and 0 < port <= 65535:
            aliases.append(f"port:{port}")
        with self._brokers_guard:
            for key in aliases:
                existing = self._brokers.get(key)
                if existing is None or existing.process.poll() is not None:
                    self._brokers[key] = broker

    def _stop_broker(self, broker: _Broker, *, graceful_timeout: float) -> None:
        process = broker.process
        if process.poll() is None and graceful_timeout > 0:
            try:
                process.wait(timeout=graceful_timeout)
            except subprocess.TimeoutExpired:
                pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        self._discard_broker(broker)

    def _discard_broker(self, broker: _Broker) -> None:
        with self._brokers_guard:
            for key, value in list(self._brokers.items()):
                if value is broker:
                    del self._brokers[key]
        if broker.process.stdin is not None:
            try:
                broker.process.stdin.close()
            except OSError:
                pass
        if broker.process.poll() is not None:
            if broker.process.stdout is not None:
                try:
                    broker.process.stdout.close()
                except OSError:
                    pass
            if not broker.log_handle.closed:
                broker.log_handle.close()

    def _target_lock(self, key: str) -> asyncio.Lock:
        with self._locks_guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock
            return lock

    def _worker_environment(self) -> dict[str, str]:
        environment = dict(os.environ)
        environment.pop("PYTHONINSPECT", None)
        environment.pop("PYTHONSTARTUP", None)
        environment["PYTHONUTF8"] = "1"
        return environment

    @staticmethod
    def _creation_flags() -> int:
        if os.name == "nt":
            return subprocess.CREATE_NO_WINDOW
        return 0
