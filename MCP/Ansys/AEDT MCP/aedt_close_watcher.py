from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import os
import threading
from typing import Callable


BUSY_DIALOG_TEXT = "being used by another application, script or extension wizard"


@dataclass(frozen=True)
class WindowState:
    main_visible: bool
    busy_dialog: bool


def get_aedt_window_state(pid: int) -> WindowState:
    if os.name != "nt":
        return WindowState(False, False)

    user32 = ctypes.windll.user32
    main_visible = False
    busy_dialog = False
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def window_text(hwnd: int) -> str:
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, len(buffer))
        return buffer.value

    @callback_type
    def child_callback(hwnd, _):
        nonlocal busy_dialog
        if BUSY_DIALOG_TEXT in window_text(hwnd):
            busy_dialog = True
        return True

    @callback_type
    def top_callback(hwnd, _):
        nonlocal main_visible, busy_dialog
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value != pid:
            return True
        text = window_text(hwnd)
        if BUSY_DIALOG_TEXT in text:
            busy_dialog = True
        if user32.IsWindowVisible(hwnd) and "Electronics Desktop" in text:
            main_visible = True
        user32.EnumChildWindows(hwnd, child_callback, 0)
        return True

    user32.EnumWindows(top_callback, 0)
    return WindowState(main_visible, busy_dialog)


class AedtCloseWatcher:
    def __init__(
        self,
        *,
        session_pid: Callable[[], int | None],
        on_close_intent: Callable[[str], None],
        window_state: Callable[[int], WindowState] = get_aedt_window_state,
        poll_interval: float = 0.2,
    ) -> None:
        self._session_pid = session_pid
        self._on_close_intent = on_close_intent
        self._window_state = window_state
        self._poll_interval = poll_interval
        self._seen_pid: int | None = None
        self._seen_main_window = False
        self._triggered = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def poll_once(self) -> None:
        if self._triggered:
            return
        pid = self._session_pid()
        if pid is None:
            self._seen_pid = None
            self._seen_main_window = False
            return
        if pid != self._seen_pid:
            self._seen_pid = pid
            self._seen_main_window = False

        state = self._window_state(pid)
        if state.busy_dialog:
            self._trigger("busy_dialog")
        elif state.main_visible:
            self._seen_main_window = True
        elif self._seen_main_window:
            self._trigger("main_window_closed")

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run,
            name="aedt-close-watcher",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        while not self._stop.wait(self._poll_interval):
            try:
                self.poll_once()
            except Exception:
                continue

    def _trigger(self, reason: str) -> None:
        self._triggered = True
        self._on_close_intent(reason)
