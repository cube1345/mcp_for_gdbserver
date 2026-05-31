"""VS Code bridge tools.

The Python MCP server cannot call the VS Code Extension API directly.  These
tools expose a small command queue that a VS Code extension can poll and execute
inside the extension host.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated, Any
from uuid import uuid4

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .tools import get_context


def _result_dict(success: bool, message: str, **kwargs: Any) -> dict[str, Any]:
    result = {"success": success, "message": message}
    result.update(kwargs)
    return result


@dataclass(frozen=True)
class BridgeCommand:
    """A command that should be executed by the VS Code extension side."""

    id: str
    command: str
    payload: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "command": self.command,
            "payload": self.payload,
            "created_at": self.created_at,
        }


class VscodeBridgeQueue:
    """In-memory command queue consumed by a VS Code extension."""

    def __init__(self) -> None:
        self._commands: list[BridgeCommand] = []

    def enqueue(self, command: str, payload: dict[str, Any] | None = None) -> BridgeCommand:
        item = BridgeCommand(
            id=uuid4().hex,
            command=command,
            payload=payload or {},
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._commands.append(item)
        return item

    def list(self, limit: int = 50) -> list[BridgeCommand]:
        return self._commands[: max(0, limit)]

    def drain(self, limit: int = 50) -> list[BridgeCommand]:
        count = max(0, limit)
        items = self._commands[:count]
        del self._commands[:count]
        return items

    def ack(self, command_ids: list[str]) -> int:
        ids = set(command_ids)
        before = len(self._commands)
        self._commands = [item for item in self._commands if item.id not in ids]
        return before - len(self._commands)

    def clear(self) -> int:
        count = len(self._commands)
        self._commands.clear()
        return count

    @property
    def size(self) -> int:
        return len(self._commands)


_bridge = VscodeBridgeQueue()


def _command_response(item: BridgeCommand) -> dict[str, Any]:
    return _result_dict(True, f"Queued VS Code command: {item.command}", command=item.to_dict())


def _current_debug_state() -> dict[str, Any]:
    ctx = get_context()
    sessions: dict[str, Any] = {}
    for session_id, session in ctx.sessions.items():
        sessions[session_id] = session.get_status()
        sessions[session_id]["gdb_path"] = ctx.gdb_path

    state: dict[str, Any] = {
        "active_session": ctx.active_session_id,
        "sessions": sessions,
    }
    if ctx.server_mgr:
        state["gdb_server"] = ctx.server_mgr.get_status()
    return state


def register_vscode_bridge_tools(mcp: FastMCP) -> None:
    """Register VS Code bridge command-queue tools."""

    @mcp.tool()
    async def vscode_bridge_enqueue(
        command: Annotated[str, Field(description="Extension-side command name")],
        payload: Annotated[dict[str, Any] | None, Field(description="JSON payload")] = None,
    ) -> str:
        """Queue a raw VS Code bridge command for the extension host."""
        item = _bridge.enqueue(command, payload)
        return str(_command_response(item))

    @mcp.tool()
    async def vscode_bridge_list_commands(
        limit: Annotated[int, Field(description="Maximum pending commands to return")] = 50,
    ) -> str:
        """List pending bridge commands without removing them."""
        items = [item.to_dict() for item in _bridge.list(limit)]
        return str(_result_dict(True, f"{len(items)} pending command(s)", commands=items))

    @mcp.tool()
    async def vscode_bridge_drain_commands(
        limit: Annotated[int, Field(description="Maximum pending commands to drain")] = 50,
    ) -> str:
        """Return and remove pending bridge commands."""
        items = [item.to_dict() for item in _bridge.drain(limit)]
        return str(_result_dict(True, f"Drained {len(items)} command(s)", commands=items))

    @mcp.tool()
    async def vscode_bridge_ack(
        command_ids: Annotated[list[str], Field(description="Bridge command IDs to acknowledge")],
    ) -> str:
        """Remove commands after the extension has executed them."""
        count = _bridge.ack(command_ids)
        return str(_result_dict(True, f"Acknowledged {count} command(s)", acknowledged=count))

    @mcp.tool()
    async def vscode_bridge_clear_commands() -> str:
        """Clear all pending VS Code bridge commands."""
        count = _bridge.clear()
        return str(_result_dict(True, f"Cleared {count} command(s)", cleared=count))

    @mcp.tool()
    async def vscode_set_source_breakpoint(
        file_path: Annotated[str, Field(description="Absolute or workspace-relative source path")],
        line: Annotated[int, Field(description="1-based source line")],
        condition: Annotated[str | None, Field(description="Optional breakpoint condition")] = None,
        hit_condition: Annotated[str | None, Field(description="Optional hit count condition")] = None,
        log_message: Annotated[str | None, Field(description="Optional logpoint message")] = None,
        enabled: Annotated[bool, Field(description="Whether the breakpoint should be enabled")] = True,
    ) -> str:
        """Ask VS Code to show a source breakpoint red dot."""
        item = _bridge.enqueue(
            "debug.setSourceBreakpoint",
            {
                "file_path": file_path,
                "line": line,
                "condition": condition,
                "hit_condition": hit_condition,
                "log_message": log_message,
                "enabled": enabled,
            },
        )
        return str(_command_response(item))

    @mcp.tool()
    async def vscode_remove_source_breakpoint(
        file_path: Annotated[str, Field(description="Absolute or workspace-relative source path")],
        line: Annotated[int, Field(description="1-based source line")],
    ) -> str:
        """Ask VS Code to remove a source breakpoint red dot."""
        item = _bridge.enqueue(
            "debug.removeSourceBreakpoint",
            {
                "file_path": file_path,
                "line": line,
            },
        )
        return str(_command_response(item))

    @mcp.tool()
    async def vscode_set_watch(
        expression: Annotated[str, Field(description="Expression to add to the Watch view")],
    ) -> str:
        """Ask VS Code to add or focus a Watch expression."""
        item = _bridge.enqueue("debug.setWatchExpression", {"expression": expression})
        return str(_command_response(item))

    @mcp.tool()
    async def vscode_remove_watch(
        expression: Annotated[str, Field(description="Expression to remove from the Watch view")],
    ) -> str:
        """Ask VS Code to remove a Watch expression."""
        item = _bridge.enqueue("debug.removeWatchExpression", {"expression": expression})
        return str(_command_response(item))

    @mcp.tool()
    async def vscode_open_run_and_debug() -> str:
        """Ask VS Code to reveal the Run and Debug view."""
        item = _bridge.enqueue("workbench.view.debug", {})
        return str(_command_response(item))

    @mcp.tool()
    async def vscode_reveal_location(
        file_path: Annotated[str, Field(description="Absolute or workspace-relative source path")],
        line: Annotated[int, Field(description="1-based source line")],
        column: Annotated[int, Field(description="1-based source column")] = 1,
        focus: Annotated[bool, Field(description="Whether to focus the editor")] = True,
    ) -> str:
        """Ask VS Code to open a file and reveal a source location."""
        item = _bridge.enqueue(
            "editor.revealLocation",
            {
                "file_path": file_path,
                "line": line,
                "column": column,
                "focus": focus,
            },
        )
        return str(_command_response(item))

    @mcp.tool()
    async def vscode_sync_debug_state() -> str:
        """Ask VS Code to sync its UI with the current MCP GDB state."""
        item = _bridge.enqueue("mcpGdb.syncDebugState", _current_debug_state())
        return str(_command_response(item))
