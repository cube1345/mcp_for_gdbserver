"""MCP tools for CMSIS-SVD peripheral register inspection."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .svd import SVDDevice, SVDPeripheral, SVDRegister
from .tools import get_context


_svd_device: SVDDevice | None = None


def _result_dict(success: bool, message: str, **kwargs: Any) -> dict[str, Any]:
    result = {"success": success, "message": message}
    result.update(kwargs)
    return result


def _require_svd() -> SVDDevice:
    if _svd_device is None:
        raise ValueError("No SVD file loaded. Call svd_load first.")
    return _svd_device


def _find_peripheral(device: SVDDevice, name: str) -> SVDPeripheral:
    peripheral = device.peripheral_by_name(name)
    if peripheral is None:
        raise ValueError(f"Peripheral not found in SVD: {name}")
    return peripheral


def _find_register(peripheral: SVDPeripheral, name: str) -> SVDRegister:
    register = peripheral.register_by_name(name)
    if register is None:
        raise ValueError(f"Register not found in {peripheral.name}: {name}")
    return register


def _decode_register(
    peripheral: SVDPeripheral,
    register: SVDRegister,
    value: int,
) -> dict[str, Any]:
    return {
        "peripheral": peripheral.name,
        "register": register.name,
        "address": hex(register.absolute_address(peripheral)),
        "address_offset": hex(register.address_offset),
        "size": register.size,
        "access": register.access,
        "value": value,
        "hex": hex(value),
        "reset_value": hex(register.reset_value) if register.reset_value is not None else None,
        "fields": [field.to_dict(value) for field in register.fields],
    }


def _extract_memory_contents(memory: Any) -> str:
    if isinstance(memory, dict):
        contents = memory.get("contents")
        return str(contents or "")

    if isinstance(memory, list):
        chunks = []
        for item in memory:
            if isinstance(item, dict):
                contents = item.get("contents")
                if contents is not None:
                    chunks.append(str(contents))
        return "".join(chunks)

    return ""


async def _read_register_value(
    peripheral: SVDPeripheral,
    register: SVDRegister,
    session_id: str | None,
    byte_order: str,
) -> int:
    ctx = get_context()
    session = ctx.ensure_session(session_id)
    byte_count = register.byte_size
    address = register.absolute_address(peripheral)

    output = await session.send_mi_command(
        f"-data-read-memory-bytes 0x{address:X} {byte_count}"
    )
    if output.is_error:
        raise ValueError(output.error_message or "GDB memory read failed")

    memory = output.result.results.get("memory", []) if output.result else []
    contents = _extract_memory_contents(memory)
    if len(contents) < byte_count * 2:
        raise ValueError(f"GDB returned too little memory data for 0x{address:X}")

    data = bytes.fromhex(contents[: byte_count * 2])
    return int.from_bytes(data, byteorder=byte_order)


def register_svd_tools(mcp: FastMCP) -> None:
    """Register CMSIS-SVD peripheral register tools."""

    @mcp.tool()
    async def svd_load(
        file_path: Annotated[str, Field(description="CMSIS-SVD XML file path")],
    ) -> str:
        """Load a CMSIS-SVD file for peripheral/register decoding."""
        global _svd_device

        path = Path(file_path)
        if not path.is_file():
            return str(_result_dict(False, f"SVD file not found: {file_path}"))

        try:
            _svd_device = SVDDevice.from_file(path)
            return str(
                _result_dict(
                    True,
                    f"Loaded SVD: {_svd_device.name}",
                    device=_svd_device.name,
                    source_path=_svd_device.source_path,
                    peripheral_count=len(_svd_device.peripherals),
                )
            )
        except Exception as exc:
            _svd_device = None
            return str(_result_dict(False, f"SVD load error: {exc}"))

    @mcp.tool()
    async def svd_status() -> str:
        """Return the loaded SVD status."""
        if _svd_device is None:
            return str(_result_dict(False, "No SVD loaded"))
        return str(
            _result_dict(
                True,
                f"SVD loaded: {_svd_device.name}",
                device=_svd_device.name,
                source_path=_svd_device.source_path,
                peripheral_count=len(_svd_device.peripherals),
            )
        )

    @mcp.tool()
    async def svd_list_peripherals(
        filter_text: Annotated[str | None, Field(description="Optional name filter")] = None,
    ) -> str:
        """List peripherals from the loaded SVD."""
        try:
            device = _require_svd()
            peripherals = [
                peripheral.to_dict()
                for peripheral in device.list_peripherals(filter_text)
            ]
            return str(
                _result_dict(
                    True,
                    f"{len(peripherals)} peripheral(s)",
                    peripherals=peripherals,
                )
            )
        except Exception as exc:
            return str(_result_dict(False, f"SVD list peripherals error: {exc}"))

    @mcp.tool()
    async def svd_list_registers(
        peripheral: Annotated[str, Field(description="Peripheral name, e.g. I2C1")],
    ) -> str:
        """List registers for a peripheral."""
        try:
            device = _require_svd()
            periph = _find_peripheral(device, peripheral)
            registers = [register.to_dict(periph) for register in periph.registers]
            return str(
                _result_dict(
                    True,
                    f"{len(registers)} register(s) in {periph.name}",
                    peripheral=periph.to_dict(),
                    registers=registers,
                )
            )
        except Exception as exc:
            return str(_result_dict(False, f"SVD list registers error: {exc}"))

    @mcp.tool()
    async def svd_decode_register_value(
        peripheral: Annotated[str, Field(description="Peripheral name, e.g. I2C1")],
        register: Annotated[str, Field(description="Register name, e.g. CR1")],
        value: Annotated[str, Field(description="Raw register value, e.g. 0x00000001")],
    ) -> str:
        """Decode a raw register value using the loaded SVD field definitions."""
        try:
            device = _require_svd()
            periph = _find_peripheral(device, peripheral)
            reg = _find_register(periph, register)
            decoded = _decode_register(periph, reg, int(value, 0))
            return str(_result_dict(True, f"Decoded {periph.name}.{reg.name}", decoded=decoded))
        except Exception as exc:
            return str(_result_dict(False, f"SVD decode error: {exc}"))

    @mcp.tool()
    async def svd_read_register(
        peripheral: Annotated[str, Field(description="Peripheral name, e.g. I2C1")],
        register: Annotated[str, Field(description="Register name, e.g. CR1")],
        session_id: Annotated[str | None, Field(description="GDB session id")] = None,
        byte_order: Annotated[str, Field(description="Target byte order")] = "little",
    ) -> str:
        """Read and decode one peripheral register through GDB memory access."""
        if byte_order not in ("little", "big"):
            return str(_result_dict(False, "byte_order must be 'little' or 'big'"))

        try:
            device = _require_svd()
            periph = _find_peripheral(device, peripheral)
            reg = _find_register(periph, register)
            value = await _read_register_value(periph, reg, session_id, byte_order)
            decoded = _decode_register(periph, reg, value)
            return str(_result_dict(True, f"Read {periph.name}.{reg.name}", decoded=decoded))
        except Exception as exc:
            return str(_result_dict(False, f"SVD read register error: {exc}"))

    @mcp.tool()
    async def svd_read_peripheral(
        peripheral: Annotated[str, Field(description="Peripheral name, e.g. I2C1")],
        registers: Annotated[list[str] | None, Field(description="Optional register names")] = None,
        max_registers: Annotated[int, Field(description="Maximum registers to read")] = 32,
        session_id: Annotated[str | None, Field(description="GDB session id")] = None,
        byte_order: Annotated[str, Field(description="Target byte order")] = "little",
    ) -> str:
        """Read and decode several registers from one peripheral."""
        if byte_order not in ("little", "big"):
            return str(_result_dict(False, "byte_order must be 'little' or 'big'"))

        try:
            device = _require_svd()
            periph = _find_peripheral(device, peripheral)
            if registers:
                selected = [_find_register(periph, name) for name in registers]
            else:
                selected = list(periph.registers[: max(0, max_registers)])

            decoded_registers = []
            for reg in selected:
                value = await _read_register_value(periph, reg, session_id, byte_order)
                decoded_registers.append(_decode_register(periph, reg, value))

            return str(
                _result_dict(
                    True,
                    f"Read {len(decoded_registers)} register(s) from {periph.name}",
                    peripheral=periph.to_dict(),
                    registers=decoded_registers,
                )
            )
        except Exception as exc:
            return str(_result_dict(False, f"SVD read peripheral error: {exc}"))
