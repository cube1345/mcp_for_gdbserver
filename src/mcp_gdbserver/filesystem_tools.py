"""Workspace-scoped filesystem MCP tools."""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .tools import get_context
from .workspace import (
    result_dict,
    resolve_workspace_path,
    truncate_text,
    workspace_relative,
    workspace_roots,
)


def _roots() -> list[Path]:
    return workspace_roots(get_context().workspace_roots)


def _file_entry(path: Path, roots: list[Path]) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "relative_path": workspace_relative(path, roots),
        "name": path.name,
        "is_dir": path.is_dir(),
        "is_file": path.is_file(),
        "size": stat.st_size,
        "mtime": stat.st_mtime,
    }


def register_filesystem_tools(mcp: FastMCP) -> None:
    """Register filesystem tools constrained to configured workspace roots."""

    @mcp.tool()
    async def fs_workspace_roots() -> str:
        """Return the filesystem roots this MCP server may access."""
        roots = _roots()
        return str(result_dict(True, f"{len(roots)} workspace root(s)", roots=[str(root) for root in roots]))

    @mcp.tool()
    async def fs_list(
        path: Annotated[str, Field(description="Workspace-relative or absolute directory path")] = ".",
        recursive: Annotated[bool, Field(description="Whether to recurse into subdirectories")] = False,
        max_entries: Annotated[int, Field(description="Maximum entries to return")] = 200,
    ) -> str:
        """List files inside a workspace-scoped directory."""
        try:
            roots = _roots()
            directory = resolve_workspace_path(path, roots, must_exist=True, directory=True)
            iterator = directory.rglob("*") if recursive else directory.iterdir()
            entries = []
            for entry in iterator:
                if len(entries) >= max_entries:
                    break
                entries.append(_file_entry(entry, roots))
            return str(result_dict(True, f"{len(entries)} entrie(s)", path=str(directory), entries=entries))
        except Exception as exc:
            return str(result_dict(False, f"Filesystem list error: {exc}"))

    @mcp.tool()
    async def fs_stat(
        path: Annotated[str, Field(description="Workspace-relative or absolute path")],
    ) -> str:
        """Return file metadata for a workspace path."""
        try:
            roots = _roots()
            resolved = resolve_workspace_path(path, roots, must_exist=True)
            return str(result_dict(True, "File stat", entry=_file_entry(resolved, roots)))
        except Exception as exc:
            return str(result_dict(False, f"Filesystem stat error: {exc}"))

    @mcp.tool()
    async def fs_read_text(
        path: Annotated[str, Field(description="Workspace-relative or absolute file path")],
        max_chars: Annotated[int, Field(description="Maximum characters to return")] = 20000,
        encoding: Annotated[str, Field(description="Text encoding")] = "utf-8",
    ) -> str:
        """Read a text file from the workspace."""
        try:
            roots = _roots()
            file_path = resolve_workspace_path(path, roots, must_exist=True, directory=False)
            text = file_path.read_text(encoding=encoding, errors="replace")
            content, truncated = truncate_text(text, max_chars)
            return str(
                result_dict(
                    True,
                    f"Read {file_path}",
                    path=str(file_path),
                    relative_path=workspace_relative(file_path, roots),
                    content=content,
                    truncated=truncated,
                    size=file_path.stat().st_size,
                )
            )
        except Exception as exc:
            return str(result_dict(False, f"Filesystem read error: {exc}"))

    @mcp.tool()
    async def fs_write_text(
        path: Annotated[str, Field(description="Workspace-relative or absolute file path")],
        content: Annotated[str, Field(description="Text content to write")],
        create_dirs: Annotated[bool, Field(description="Create parent directories if missing")] = False,
        overwrite: Annotated[bool, Field(description="Allow overwriting an existing file")] = True,
        encoding: Annotated[str, Field(description="Text encoding")] = "utf-8",
    ) -> str:
        """Write a text file inside the workspace."""
        try:
            roots = _roots()
            file_path = resolve_workspace_path(path, roots, must_exist=False, directory=False)
            if file_path.exists() and not overwrite:
                return str(result_dict(False, f"File already exists: {file_path}"))
            if create_dirs:
                file_path.parent.mkdir(parents=True, exist_ok=True)
            if not file_path.parent.exists():
                return str(result_dict(False, f"Parent directory does not exist: {file_path.parent}"))
            file_path.write_text(content, encoding=encoding)
            return str(
                result_dict(
                    True,
                    f"Wrote {file_path}",
                    path=str(file_path),
                    relative_path=workspace_relative(file_path, roots),
                    bytes=file_path.stat().st_size,
                )
            )
        except Exception as exc:
            return str(result_dict(False, f"Filesystem write error: {exc}"))

    @mcp.tool()
    async def fs_replace_text(
        path: Annotated[str, Field(description="Workspace-relative or absolute file path")],
        old: Annotated[str, Field(description="Text to replace")],
        new: Annotated[str, Field(description="Replacement text")],
        expected_count: Annotated[int | None, Field(description="Expected replacement count")] = None,
        encoding: Annotated[str, Field(description="Text encoding")] = "utf-8",
    ) -> str:
        """Replace text in a workspace file."""
        try:
            roots = _roots()
            file_path = resolve_workspace_path(path, roots, must_exist=True, directory=False)
            text = file_path.read_text(encoding=encoding, errors="replace")
            count = text.count(old)
            if expected_count is not None and count != expected_count:
                return str(
                    result_dict(
                        False,
                        f"Expected {expected_count} occurrence(s), found {count}",
                        count=count,
                    )
                )
            if count == 0:
                return str(result_dict(False, "Text not found", count=0))
            file_path.write_text(text.replace(old, new), encoding=encoding)
            return str(
                result_dict(
                    True,
                    f"Replaced {count} occurrence(s)",
                    path=str(file_path),
                    relative_path=workspace_relative(file_path, roots),
                    count=count,
                )
            )
        except Exception as exc:
            return str(result_dict(False, f"Filesystem replace error: {exc}"))

    @mcp.tool()
    async def fs_find(
        pattern: Annotated[str, Field(description="Glob pattern, e.g. *.c or CMakeLists.txt")],
        path: Annotated[str, Field(description="Directory to search")] = ".",
        max_results: Annotated[int, Field(description="Maximum results to return")] = 100,
    ) -> str:
        """Find files by glob pattern inside the workspace."""
        try:
            roots = _roots()
            directory = resolve_workspace_path(path, roots, must_exist=True, directory=True)
            results = []
            for item in directory.rglob("*"):
                if len(results) >= max_results:
                    break
                if item.is_file() and fnmatch.fnmatch(item.name, pattern):
                    results.append(_file_entry(item, roots))
            return str(result_dict(True, f"{len(results)} result(s)", results=results))
        except Exception as exc:
            return str(result_dict(False, f"Filesystem find error: {exc}"))
