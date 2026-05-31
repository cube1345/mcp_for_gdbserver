"""Probe, OpenOCD, pyOCD, and port-diagnostic MCP tools."""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .tools import get_context
from .workspace import (
    result_dict,
    resolve_workspace_path,
    run_process,
    truncate_text,
    workspace_roots,
)


def _roots() -> list[Path]:
    return workspace_roots(get_context().workspace_roots)


def _pyocd_path() -> str:
    return get_context().pyocd_path


def _openocd_path() -> str:
    return get_context().openocd_path


def _port_status(host: str, port: int, timeout: float) -> dict[str, Any]:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
    return {
        "host": host,
        "port": port,
        "busy": result == 0,
        "connect_ex": result,
    }


def register_probe_tools(mcp: FastMCP) -> None:
    """Register probe and backend diagnostics tools."""

    @mcp.tool()
    async def probe_check_ports(
        ports: Annotated[list[int] | None, Field(description="Ports to check")] = None,
        host: Annotated[str, Field(description="Host to check")] = "127.0.0.1",
        timeout: Annotated[float, Field(description="Socket timeout in seconds")] = 0.5,
    ) -> str:
        """Check whether common debug ports are accepting TCP connections."""
        selected_ports = ports or [3333, 50000, 8765]
        try:
            statuses = [_port_status(host, int(port), timeout) for port in selected_ports]
            busy = [entry for entry in statuses if entry["busy"]]
            return str(
                result_dict(
                    True,
                    f"{len(busy)} busy port(s)",
                    host=host,
                    ports=statuses,
                )
            )
        except Exception as exc:
            return str(result_dict(False, f"Port check error: {exc}"))

    @mcp.tool()
    async def pyocd_list(
        timeout: Annotated[float, Field(description="Timeout in seconds")] = 20.0,
        max_output: Annotated[int, Field(description="Maximum output characters")] = 20000,
    ) -> str:
        """Run `pyocd list` to detect connected CMSIS-DAP/DAPLink probes."""
        result = run_process([_pyocd_path(), "list"], timeout=timeout, max_output=max_output)
        return str(result_dict(bool(result["ok"]), "pyOCD list completed" if result["ok"] else "pyOCD list failed", **result))

    @mcp.tool()
    async def pyocd_targets(
        timeout: Annotated[float, Field(description="Timeout in seconds")] = 20.0,
        max_output: Annotated[int, Field(description="Maximum output characters")] = 20000,
    ) -> str:
        """Run `pyocd list --targets`."""
        result = run_process([_pyocd_path(), "list", "--targets"], timeout=timeout, max_output=max_output)
        return str(result_dict(bool(result["ok"]), "pyOCD targets listed" if result["ok"] else "pyOCD targets failed", **result))

    @mcp.tool()
    async def openocd_version(
        timeout: Annotated[float, Field(description="Timeout in seconds")] = 10.0,
        max_output: Annotated[int, Field(description="Maximum output characters")] = 12000,
    ) -> str:
        """Run `openocd --version`."""
        result = run_process([_openocd_path(), "--version"], timeout=timeout, max_output=max_output)
        return str(result_dict(bool(result["ok"]), "OpenOCD version completed" if result["ok"] else "OpenOCD version failed", **result))

    @mcp.tool()
    async def openocd_probe_scan(
        interface_config: Annotated[str, Field(description="OpenOCD interface cfg, e.g. interface/cmsis-dap.cfg")],
        target_config: Annotated[str, Field(description="OpenOCD target cfg, e.g. target/stm32f4x.cfg")],
        extra_args: Annotated[list[str] | None, Field(description="Additional OpenOCD args")] = None,
        timeout: Annotated[float, Field(description="Timeout in seconds")] = 20.0,
        max_output: Annotated[int, Field(description="Maximum output characters")] = 30000,
    ) -> str:
        """Run a short OpenOCD init/shutdown probe scan."""
        args = [
            _openocd_path(),
            "-f",
            interface_config,
            "-f",
            target_config,
        ]
        if extra_args:
            args.extend(extra_args)
        args.extend(["-c", "init; shutdown"])
        result = run_process(args, timeout=timeout, max_output=max_output)
        return str(result_dict(bool(result["ok"]), "OpenOCD scan completed" if result["ok"] else "OpenOCD scan failed", **result))

    @mcp.tool()
    async def gdb_server_read_output() -> str:
        """Read available stdout/stderr from the managed GDB server process."""
        ctx = get_context()
        if not ctx.server_mgr:
            return str(result_dict(False, "GDB server manager is not active"))
        try:
            stdout, stderr = ctx.server_mgr.read_output()
            return str(
                result_dict(
                    True,
                    "GDB server output read",
                    stdout=stdout,
                    stderr=stderr,
                    running=ctx.server_mgr.is_running,
                    pid=ctx.server_mgr.pid,
                )
            )
        except Exception as exc:
            return str(result_dict(False, f"GDB server output error: {exc}"))

    @mcp.tool()
    async def probe_tail_log(
        log_path: Annotated[str, Field(description="Workspace log file path")],
        max_chars: Annotated[int, Field(description="Maximum characters to return")] = 20000,
        encoding: Annotated[str, Field(description="Text encoding")] = "utf-8",
    ) -> str:
        """Read the tail of a workspace log file, useful for OpenOCD/backend logs."""
        try:
            path = resolve_workspace_path(log_path, _roots(), must_exist=True, directory=False)
            text = path.read_text(encoding=encoding, errors="replace")
            tail, truncated = truncate_text(text[-max_chars:], max_chars)
            return str(
                result_dict(
                    True,
                    f"Read log tail: {path}",
                    path=str(path),
                    content=tail,
                    truncated=truncated or len(text) > len(tail),
                    size=path.stat().st_size,
                )
            )
        except Exception as exc:
            return str(result_dict(False, f"Probe log tail error: {exc}"))
