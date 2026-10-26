from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import psutil


def _tool_result(result, name: str) -> dict:
    if result.isError:
        text = "\n".join(getattr(item, "text", "") for item in result.content)
        raise RuntimeError(f"MCP tool {name} failed: {text}")
    if not isinstance(result.structuredContent, dict):
        raise RuntimeError(f"MCP tool {name} returned no structured object")
    return result.structuredContent


async def run(args: argparse.Namespace) -> int:
    module_root = Path(__file__).resolve().parents[1]
    python = module_root / ".venv" / "Scripts" / "python.exe"
    server = module_root / "mcp_server.py"
    params = StdioServerParameters(
        command=str(python),
        args=[str(server)],
        cwd=str(module_root),
        env={
            **os.environ,
            "AEDT_INSTALL_DIR": str(args.aedt_root),
            "AEDT_VERSION": "2026.1",
        },
    )

    async with stdio_client(params) as streams:
        session_timeout = max(args.timeout, 1800.0 if args.run_wr90 else args.timeout)
        async with ClientSession(
            *streams,
            read_timeout_seconds=timedelta(seconds=session_timeout),
        ) as session:
            await session.initialize()
            tools = await session.list_tools()
            launched = None
            if not args.attach:
                launched = _tool_result(
                    await session.call_tool(
                        "launch_aedt",
                        {
                            "version": "2026.1",
                            "port": args.port,
                            "install_dir": str(args.aedt_root),
                            "timeout": args.timeout,
                        },
                    ),
                    "launch_aedt",
                )
            target = {"pid": args.pid} if args.pid else {"port": args.port}
            checked = _tool_result(
                await session.call_tool(
                    "check_aedt_connection",
                    {**target, "timeout": 30},
                ),
                "check_aedt_connection",
            )
            pid = int(checked["pid"] if launched is None else launched["pid"])
            raw_port = checked.get("port") if launched is None else launched["port"]
            port = int(raw_port) if raw_port else None
            status = {
                "connected": bool(checked.get("connected")),
                "phase": "solving_wr90" if args.run_wr90 else "connected",
                "holder_pid": os.getpid(),
                "aedt_pid": pid,
                "grpc_port": port,
                "aedt_version": checked.get("aedt_version"),
                "active_project": checked.get("active_project"),
                "active_design": checked.get("active_design"),
                "tools": sorted(tool.name for tool in tools.tools),
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
            args.status.parent.mkdir(parents=True, exist_ok=True)
            args.status.write_text(
                json.dumps(status, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            if args.run_wr90:
                wr90_output = args.wr90_output or args.status.parent / "WR90_Waveguide"
                status["wr90"] = _tool_result(
                    await session.call_tool(
                        "build_wr90_waveguide",
                        {
                            **target,
                            "project_name": args.wr90_project,
                            "design_name": args.wr90_design,
                            "output_dir": str(wr90_output),
                            "solve": True,
                            "timeout": 1800.0,
                        },
                    ),
                    "build_wr90_waveguide",
                )
                status["phase"] = "complete"
                status["completed_at"] = datetime.now(timezone.utc).isoformat()
                args.status.write_text(
                    json.dumps(status, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            print(json.dumps(status, ensure_ascii=False), flush=True)

            if args.exit_after_run:
                return 0

            while psutil.pid_exists(pid):
                await asyncio.sleep(0.5)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aedt-root", type=Path, required=True)
    parser.add_argument("--port", type=int)
    parser.add_argument("--pid", type=int)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--attach", action="store_true")
    parser.add_argument("--run-wr90", action="store_true")
    parser.add_argument("--wr90-project", default="Classic_WR90_Waveguide")
    parser.add_argument("--wr90-design", default="WR90_TE10")
    parser.add_argument("--wr90-output", type=Path)
    parser.add_argument("--exit-after-run", action="store_true")
    args = parser.parse_args()
    if bool(args.pid) == bool(args.port):
        parser.error("specify exactly one of --pid or --port")
    if not args.attach and not args.port:
        parser.error("launch mode requires --port")
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
