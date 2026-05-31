"""Explicit AI watch-list MCP tools.

These tools maintain server-side watch expressions that can be synchronized by
VS Code extensions or other MCP clients. They are intentionally separate from
GDB's `display` command and from one-off `print` evaluations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .tools import get_context


def _result_dict(success: bool, message: str, **kwargs: Any) -> dict[str, Any]:
    result = {"success": success, "message": message}
    result.update(kwargs)
    return result


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class WatchEntry:
    """One server-side AI watch expression."""

    expression: str
    session_id: str | None = None
    enabled: bool = True
    format: str | None = None
    created_at: str = ""
    updated_at: str | None = None
    last_value: str | None = None
    last_error: str | None = None

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = _now()

    @property
    def key(self) -> tuple[str | None, str]:
        return (self.session_id, self.expression)

    def to_dict(self) -> dict[str, Any]:
        return {
            "expression": self.expression,
            "session_id": self.session_id,
            "enabled": self.enabled,
            "format": self.format,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_value": self.last_value,
            "last_error": self.last_error,
        }


class WatchStore:
    """In-memory watch-list state."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str | None, str], WatchEntry] = {}

    def add(
        self,
        expression: str,
        *,
        session_id: str | None = None,
        format: str | None = None,
        enabled: bool = True,
    ) -> tuple[WatchEntry, bool]:
        key = (session_id, expression)
        existing = self._entries.get(key)
        if existing is not None:
            existing.enabled = enabled
            existing.format = format
            existing.updated_at = _now()
            return existing, False

        entry = WatchEntry(
            expression=expression,
            session_id=session_id,
            format=format,
            enabled=enabled,
        )
        self._entries[key] = entry
        return entry, True

    def remove(self, expression: str, *, session_id: str | None = None) -> bool:
        return self._entries.pop((session_id, expression), None) is not None

    def clear(self, *, session_id: str | None = None) -> int:
        if session_id is None:
            count = len(self._entries)
            self._entries.clear()
            return count

        keys = [key for key in self._entries if key[0] == session_id]
        for key in keys:
            del self._entries[key]
        return len(keys)

    def list(self, *, session_id: str | None = None, enabled_only: bool = False) -> list[WatchEntry]:
        entries = list(self._entries.values())
        if session_id is not None:
            entries = [entry for entry in entries if entry.session_id == session_id]
        if enabled_only:
            entries = [entry for entry in entries if entry.enabled]
        return sorted(entries, key=lambda entry: (entry.session_id or "", entry.expression))

    def set_enabled(self, expression: str, enabled: bool, *, session_id: str | None = None) -> WatchEntry | None:
        entry = self._entries.get((session_id, expression))
        if entry is None:
            return None
        entry.enabled = enabled
        entry.updated_at = _now()
        return entry

    def get(self, expression: str, *, session_id: str | None = None) -> WatchEntry | None:
        return self._entries.get((session_id, expression))


_watch_store = WatchStore()


async def _evaluate_watch(entry: WatchEntry) -> WatchEntry:
    ctx = get_context()
    session = ctx.ensure_session(entry.session_id)
    try:
        output = await session.send_mi_command(
            f"-data-evaluate-expression {entry.expression}"
        )
        if output.is_error:
            entry.last_value = None
            entry.last_error = output.error_message or "GDB expression evaluation failed"
        else:
            entry.last_value = output.result.results.get("value", "") if output.result else ""
            entry.last_error = None
    except Exception as exc:
        entry.last_value = None
        entry.last_error = str(exc)
    entry.updated_at = _now()
    return entry


def register_watch_tools(mcp: FastMCP) -> None:
    """Register explicit server-side watch-list tools."""

    @mcp.tool()
    async def watch_add(
        expression: Annotated[str, Field(description="Expression to keep watching")],
        session_id: Annotated[str | None, Field(description="Optional GDB session id")] = None,
        format: Annotated[str | None, Field(description="Preferred display format hint, e.g. x/d/t")] = None,
        enabled: Annotated[bool, Field(description="Whether the watch is active")] = True,
        refresh: Annotated[bool, Field(description="Immediately evaluate after adding")] = True,
    ) -> str:
        """Add or update a server-side watch expression."""
        expression = expression.strip()
        if not expression:
            return str(_result_dict(False, "Expression must not be empty"))

        entry, created = _watch_store.add(
            expression,
            session_id=session_id,
            format=format,
            enabled=enabled,
        )
        if refresh and enabled:
            await _evaluate_watch(entry)
        return str(
            _result_dict(
                True,
                "Watch added" if created else "Watch updated",
                watch=entry.to_dict(),
                created=created,
            )
        )

    @mcp.tool()
    async def watch_remove(
        expression: Annotated[str, Field(description="Expression to remove")],
        session_id: Annotated[str | None, Field(description="Optional GDB session id")] = None,
    ) -> str:
        """Remove a server-side watch expression."""
        removed = _watch_store.remove(expression.strip(), session_id=session_id)
        return str(
            _result_dict(
                removed,
                "Watch removed" if removed else "Watch not found",
                expression=expression,
                session_id=session_id,
            )
        )

    @mcp.tool()
    async def watch_list(
        session_id: Annotated[str | None, Field(description="Optional GDB session id filter")] = None,
        enabled_only: Annotated[bool, Field(description="Only return enabled watches")] = False,
    ) -> str:
        """List server-side watch expressions and their last values."""
        watches = [
            entry.to_dict()
            for entry in _watch_store.list(session_id=session_id, enabled_only=enabled_only)
        ]
        return str(_result_dict(True, f"{len(watches)} watch(es)", watches=watches))

    @mcp.tool()
    async def watch_refresh(
        expression: Annotated[str | None, Field(description="Optional expression to refresh")] = None,
        session_id: Annotated[str | None, Field(description="Optional GDB session id filter")] = None,
        enabled_only: Annotated[bool, Field(description="Only refresh enabled watches")] = True,
    ) -> str:
        """Refresh watch values by evaluating expressions in GDB."""
        if expression:
            entry = _watch_store.get(expression.strip(), session_id=session_id)
            if entry is None:
                return str(
                    _result_dict(
                        False,
                        "Watch not found",
                        expression=expression,
                        session_id=session_id,
                    )
                )
            entries = [entry]
        else:
            entries = _watch_store.list(session_id=session_id, enabled_only=enabled_only)

        refreshed = []
        for entry in entries:
            if enabled_only and not entry.enabled:
                continue
            refreshed.append((await _evaluate_watch(entry)).to_dict())

        failed = [entry for entry in refreshed if entry.get("last_error")]
        return str(
            _result_dict(
                len(failed) == 0,
                f"Refreshed {len(refreshed)} watch(es)",
                watches=refreshed,
                failed_count=len(failed),
            )
        )

    @mcp.tool()
    async def watch_set_enabled(
        expression: Annotated[str, Field(description="Expression to enable or disable")],
        enabled: Annotated[bool, Field(description="New enabled state")],
        session_id: Annotated[str | None, Field(description="Optional GDB session id")] = None,
    ) -> str:
        """Enable or disable a watch without removing it."""
        entry = _watch_store.set_enabled(expression.strip(), enabled, session_id=session_id)
        if entry is None:
            return str(_result_dict(False, "Watch not found", expression=expression, session_id=session_id))
        return str(_result_dict(True, "Watch updated", watch=entry.to_dict()))

    @mcp.tool()
    async def watch_clear(
        session_id: Annotated[str | None, Field(description="Optional GDB session id filter")] = None,
    ) -> str:
        """Clear all server-side watches, or only watches for one session."""
        count = _watch_store.clear(session_id=session_id)
        return str(_result_dict(True, f"Cleared {count} watch(es)", cleared=count, session_id=session_id))
