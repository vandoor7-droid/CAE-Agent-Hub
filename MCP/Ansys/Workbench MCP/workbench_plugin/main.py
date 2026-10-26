# encoding: utf-8
"""ACT entry points for Workbench MCP.

The plugin supports two Mechanical-side transports:
- file queue processing on the Mechanical UI/script context
- a localhost socket timer bridge for repeated lightweight requests

Set WORKBENCH_MCP_ROOT to the cloned Workbench MCP folder when the plugin is
installed outside this repository, for example in the user's ACT extensions
directory.
"""

from __future__ import print_function

import os
import time

try:
    import __builtin__ as _builtins
except Exception:
    import builtins as _builtins


_PLUGIN_DIR = os.path.abspath(os.path.dirname(__file__))
_PROJECT_ROOT = os.environ.get("WORKBENCH_MCP_ROOT") or os.path.abspath(os.path.join(_PLUGIN_DIR, ".."))
_PLUGIN_ROOT = os.path.join(_PROJECT_ROOT, "workbench_plugin")
_QUEUE_ROOT = os.environ.get("WORKBENCH_MCP_QUEUE_ROOT") or os.path.join(_PROJECT_ROOT, "workbench_queue")

_QUEUE_PROCESSOR_PATH = os.path.join(_PLUGIN_ROOT, "mechanical_queue_processor.py")
_SOCKET_TIMER_PATH = os.path.join(_PLUGIN_ROOT, "mechanical_socket_timer_v7.py")
_AUTO_START_SOCKET_TIMER = os.environ.get("WORKBENCH_MCP_AUTO_START_SOCKET", "1") != "0"
_AUTO_START_QUEUE_TIMER = os.environ.get("WORKBENCH_MCP_AUTO_START_QUEUE", "1") != "0"
_QUEUE_TIMER_INTERVAL_MS = int(os.environ.get("WORKBENCH_MCP_QUEUE_INTERVAL_MS", "1500"))
_DEBUG_LOG_FILE = os.path.join(_QUEUE_ROOT, "act_main_debug.log")
_REQUEST_DIR = os.path.join(_QUEUE_ROOT, "requests")


def _mkdirs(path):
    if not path or os.path.isdir(path):
        return
    parent = os.path.dirname(path)
    if parent and parent != path and not os.path.isdir(parent):
        _mkdirs(parent)
    if not os.path.isdir(path):
        os.mkdir(path)


def _debug_log(message):
    try:
        _mkdirs(os.path.dirname(_DEBUG_LOG_FILE))
        with open(_DEBUG_LOG_FILE, "a") as fp:
            fp.write("%s [WorkbenchMCP main.py] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), str(message)))
    except Exception:
        pass


def _log(message):
    _debug_log(message)
    try:
        ExtAPI.Log.WriteMessage("[WorkbenchMCP] " + str(message))
    except Exception:
        print("[WorkbenchMCP] " + str(message))


def process_mcp_queue(analysis=None):
    _debug_log("process_mcp_queue callback entered")
    _log("Processing MCP queue with: " + _QUEUE_PROCESSOR_PATH)
    namespace = {}
    namespace.update(globals())
    with open(_QUEUE_PROCESSOR_PATH, "r") as stream:
        code = stream.read()
    exec(compile(code, _QUEUE_PROCESSOR_PATH, "exec"), namespace, namespace)
    _log("MCP queue processing finished")


def _pending_request_count():
    try:
        if not os.path.isdir(_REQUEST_DIR):
            return 0
        return len([name for name in os.listdir(_REQUEST_DIR) if name.lower().endswith(".json")])
    except Exception as exc:
        _debug_log("pending request count failed: " + str(exc))
        return 0


def _auto_queue_tick(sender=None, args=None):
    sentinel = "_WORKBENCH_MCP_AUTO_QUEUE_PROCESSING"
    if getattr(_builtins, sentinel, False):
        return
    count = _pending_request_count()
    if count <= 0:
        return
    setattr(_builtins, sentinel, True)
    try:
        _log("Auto queue timer found %d request(s); processing now" % count)
        process_mcp_queue()
    except Exception as exc:
        _log("Auto queue processing failed: " + str(exc))
    finally:
        setattr(_builtins, sentinel, False)


def start_auto_queue_timer(analysis=None):
    if getattr(_builtins, "_WORKBENCH_MCP_AUTO_QUEUE_TIMER_RUNNING", False):
        _debug_log("auto queue timer already running")
        return
    import clr
    clr.AddReference("System.Windows.Forms")
    from System.Windows.Forms import Timer
    timer = Timer()
    timer.Interval = _QUEUE_TIMER_INTERVAL_MS
    timer.Tick += _auto_queue_tick
    timer.Start()
    setattr(_builtins, "_WORKBENCH_MCP_AUTO_QUEUE_TIMER", timer)
    setattr(_builtins, "_WORKBENCH_MCP_AUTO_QUEUE_TIMER_RUNNING", True)
    _log("Auto MCP queue timer started; interval=%d ms" % _QUEUE_TIMER_INTERVAL_MS)


def stop_auto_queue_timer(analysis=None):
    timer = getattr(_builtins, "_WORKBENCH_MCP_AUTO_QUEUE_TIMER", None)
    if timer is not None:
        try:
            timer.Stop()
        except Exception:
            pass
    setattr(_builtins, "_WORKBENCH_MCP_AUTO_QUEUE_TIMER", None)
    setattr(_builtins, "_WORKBENCH_MCP_AUTO_QUEUE_TIMER_RUNNING", False)
    _log("Auto MCP queue timer stopped")


def show_mcp_queue_info(analysis=None):
    _debug_log("show_mcp_queue_info callback entered")
    _log("MCP project root: " + _PROJECT_ROOT)
    _log("MCP queue root: " + _QUEUE_ROOT)
    _log("Submit requests through the MCP queue tools, then use Process MCP Queue or the auto queue timer.")


def _load_socket_timer_namespace():
    namespace = globals()
    namespace["WORKBENCH_MCP_LOAD_ONLY"] = True
    with open(_SOCKET_TIMER_PATH, "r") as stream:
        code = stream.read()
    exec(compile(code, _SOCKET_TIMER_PATH, "exec"), namespace, namespace)
    return namespace


def start_mcp_socket_timer(analysis=None):
    _debug_log("start_mcp_socket_timer callback entered")
    _log("Starting non-blocking socket timer with: " + _SOCKET_TIMER_PATH)
    namespace = _load_socket_timer_namespace()
    state = namespace["start_socket_timer_bridge"]()
    _log("Socket Timer Start state: " + str(state))
    try:
        start_auto_queue_timer()
    except Exception as exc:
        _log("Auto queue timer start after socket start failed: " + str(exc))


def stop_mcp_socket_timer(analysis=None):
    _debug_log("stop_mcp_socket_timer callback entered")
    _log("Stopping non-blocking socket timer")
    namespace = _load_socket_timer_namespace()
    state = namespace["stop_socket_timer_bridge"]()
    _log("Socket Timer Stop state: " + str(state))


def _auto_start_mcp_socket_timer():
    if not _AUTO_START_SOCKET_TIMER:
        return
    sentinel = "_WORKBENCH_MCP_MAIN_AUTOSTART_ATTEMPTED"
    if getattr(_builtins, sentinel, False):
        return
    setattr(_builtins, sentinel, True)
    try:
        _log("Auto-starting Workbench MCP Socket Timer v7")
        start_mcp_socket_timer()
    except Exception as exc:
        _log("Auto-start skipped or failed: " + str(exc))


def _auto_start_queue_timer():
    if not _AUTO_START_QUEUE_TIMER:
        return
    sentinel = "_WORKBENCH_MCP_AUTO_QUEUE_TIMER_ATTEMPTED"
    if getattr(_builtins, sentinel, False):
        return
    setattr(_builtins, sentinel, True)
    try:
        start_auto_queue_timer()
    except Exception as exc:
        _log("Auto queue timer start skipped or failed: " + str(exc))


_debug_log("main.py imported from " + __file__)
_auto_start_mcp_socket_timer()
_auto_start_queue_timer()
