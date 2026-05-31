"""Serial-port MCP tools for firmware runtime logs."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import uuid4

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .workspace import result_dict


_serial_sessions: dict[str, Any] = {}


def _serial_module() -> Any:
    try:
        import serial
    except ImportError as exc:
        raise RuntimeError("pyserial is not installed. Install it with: python -m pip install pyserial") from exc
    return serial


def _list_ports() -> list[dict[str, Any]]:
    try:
        from serial.tools import list_ports
    except ImportError as exc:
        raise RuntimeError("pyserial is not installed. Install it with: python -m pip install pyserial") from exc

    ports = []
    for port in list_ports.comports():
        ports.append(
            {
                "device": port.device,
                "name": port.name,
                "description": port.description,
                "hwid": port.hwid,
                "vid": port.vid,
                "pid": port.pid,
                "serial_number": port.serial_number,
                "manufacturer": port.manufacturer,
                "product": port.product,
                "interface": port.interface,
            }
        )
    return ports


def _decode(data: bytes, encoding: str) -> dict[str, Any]:
    return {
        "bytes": len(data),
        "hex": data.hex(),
        "text": data.decode(encoding, errors="replace"),
    }


def register_serial_tools(mcp: FastMCP) -> None:
    """Register serial-port tools."""

    @mcp.tool()
    async def serial_list_ports() -> str:
        """List available serial ports."""
        try:
            ports = _list_ports()
            return str(result_dict(True, f"{len(ports)} serial port(s)", ports=ports))
        except Exception as exc:
            return str(result_dict(False, f"Serial list error: {exc}"))

    @mcp.tool()
    async def serial_open(
        port: Annotated[str, Field(description="Serial port name, e.g. COM3 or /dev/ttyACM0")],
        baudrate: Annotated[int, Field(description="Baud rate")] = 115200,
        timeout: Annotated[float, Field(description="Read timeout in seconds")] = 0.1,
        session_id: Annotated[str | None, Field(description="Optional serial session id")] = None,
    ) -> str:
        """Open a serial session."""
        try:
            serial = _serial_module()
            sid = session_id or uuid4().hex
            if sid in _serial_sessions:
                return str(result_dict(False, f"Serial session already exists: {sid}"))
            handle = serial.Serial(port=port, baudrate=baudrate, timeout=timeout)
            _serial_sessions[sid] = handle
            return str(
                result_dict(
                    True,
                    f"Opened serial session {sid}",
                    session_id=sid,
                    port=port,
                    baudrate=baudrate,
                )
            )
        except Exception as exc:
            return str(result_dict(False, f"Serial open error: {exc}"))

    @mcp.tool()
    async def serial_status() -> str:
        """Return open serial sessions."""
        sessions = []
        for sid, handle in _serial_sessions.items():
            sessions.append(
                {
                    "session_id": sid,
                    "port": getattr(handle, "port", None),
                    "baudrate": getattr(handle, "baudrate", None),
                    "is_open": getattr(handle, "is_open", None),
                    "in_waiting": getattr(handle, "in_waiting", None),
                }
            )
        return str(result_dict(True, f"{len(sessions)} serial session(s)", sessions=sessions))

    @mcp.tool()
    async def serial_read(
        session_id: Annotated[str, Field(description="Serial session id")],
        max_bytes: Annotated[int, Field(description="Maximum bytes to read")] = 4096,
        encoding: Annotated[str, Field(description="Text encoding for decoded output")] = "utf-8",
    ) -> str:
        """Read currently available serial bytes."""
        try:
            handle = _serial_sessions.get(session_id)
            if handle is None:
                return str(result_dict(False, f"Serial session not found: {session_id}"))
            waiting = getattr(handle, "in_waiting", 0) or 0
            count = max(1, min(max_bytes, waiting or max_bytes))
            data = handle.read(count)
            return str(result_dict(True, f"Read {len(data)} byte(s)", session_id=session_id, **_decode(data, encoding)))
        except Exception as exc:
            return str(result_dict(False, f"Serial read error: {exc}"))

    @mcp.tool()
    async def serial_write(
        session_id: Annotated[str, Field(description="Serial session id")],
        text: Annotated[str | None, Field(description="Text to write")] = None,
        hex_data: Annotated[str | None, Field(description="Hex bytes to write, e.g. 0d0a")] = None,
        encoding: Annotated[str, Field(description="Text encoding")] = "utf-8",
    ) -> str:
        """Write text or hex bytes to a serial session."""
        try:
            handle = _serial_sessions.get(session_id)
            if handle is None:
                return str(result_dict(False, f"Serial session not found: {session_id}"))
            if hex_data is None and text is None:
                return str(result_dict(False, "Provide text or hex_data"))
            data = bytes.fromhex(hex_data) if hex_data is not None else (text or "").encode(encoding)
            written = handle.write(data)
            return str(result_dict(True, f"Wrote {written} byte(s)", session_id=session_id, bytes=written))
        except Exception as exc:
            return str(result_dict(False, f"Serial write error: {exc}"))

    @mcp.tool()
    async def serial_close(
        session_id: Annotated[str, Field(description="Serial session id")],
    ) -> str:
        """Close a serial session."""
        handle = _serial_sessions.pop(session_id, None)
        if handle is None:
            return str(result_dict(False, f"Serial session not found: {session_id}"))
        try:
            handle.close()
            return str(result_dict(True, f"Closed serial session {session_id}"))
        except Exception as exc:
            return str(result_dict(False, f"Serial close error: {exc}"))
