"""Documentation helper MCP tools."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .tools import get_context
from .workspace import result_dict, resolve_workspace_path, truncate_text, workspace_roots


REFERENCE_LINKS: dict[str, list[dict[str, str]]] = {
    "stm32_hal": [
        {
            "title": "STM32Cube MCU packages",
            "url": "https://www.st.com/en/embedded-software/stm32cube-mcu-mpu-packages.html",
        },
        {
            "title": "STM32CubeF4 package",
            "url": "https://github.com/STMicroelectronics/STM32CubeF4",
        },
    ],
    "openocd": [
        {
            "title": "OpenOCD user guide",
            "url": "https://openocd.org/doc/html/index.html",
        },
        {
            "title": "OpenOCD source repository",
            "url": "https://github.com/openocd-org/openocd",
        },
    ],
    "cmake": [
        {
            "title": "CMake presets",
            "url": "https://cmake.org/cmake/help/latest/manual/cmake-presets.7.html",
        },
        {
            "title": "cmake --build",
            "url": "https://cmake.org/cmake/help/latest/manual/cmake.1.html",
        },
    ],
    "gdb": [
        {
            "title": "GDB manual",
            "url": "https://sourceware.org/gdb/current/onlinedocs/gdb.html/",
        },
        {
            "title": "GDB/MI interface",
            "url": "https://sourceware.org/gdb/current/onlinedocs/gdb.html/GDB_002fMI.html",
        },
    ],
    "pyocd": [
        {
            "title": "pyOCD documentation",
            "url": "https://pyocd.io/docs/",
        },
    ],
    "cmsis_svd": [
        {
            "title": "CMSIS-SVD specification",
            "url": "https://arm-software.github.io/CMSIS_5/SVD/html/index.html",
        },
    ],
}


DOC_SUFFIXES = {".md", ".txt", ".rst", ".cmake", ".json", ".cfg", ".ini"}


def _roots() -> list[Path]:
    return workspace_roots(get_context().workspace_roots)


def _match_lines(path: Path, query: str, max_matches: int) -> list[dict[str, Any]]:
    matches = []
    needle = query.casefold()
    try:
        for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if needle in line.casefold():
                matches.append({"line": line_no, "text": line.strip()})
                if len(matches) >= max_matches:
                    break
    except OSError:
        return []
    return matches


def register_docs_tools(mcp: FastMCP) -> None:
    """Register docs helper tools."""

    @mcp.tool()
    async def docs_reference(
        topic: Annotated[str | None, Field(description="Topic key, e.g. stm32_hal/openocd/cmake/gdb/pyocd/cmsis_svd")] = None,
    ) -> str:
        """Return curated official documentation links for embedded debug topics."""
        if topic is None:
            return str(
                result_dict(
                    True,
                    f"{len(REFERENCE_LINKS)} topic(s)",
                    topics=sorted(REFERENCE_LINKS),
                    references=REFERENCE_LINKS,
                )
            )
        key = topic.casefold()
        matches = {name: links for name, links in REFERENCE_LINKS.items() if key in name.casefold()}
        if not matches:
            return str(result_dict(False, f"No reference topic matched: {topic}", topics=sorted(REFERENCE_LINKS)))
        return str(result_dict(True, f"{len(matches)} matching topic(s)", references=matches))

    @mcp.tool()
    async def docs_search_workspace(
        query: Annotated[str, Field(description="Text to search for")],
        path: Annotated[str, Field(description="Directory to search")] = ".",
        max_files: Annotated[int, Field(description="Maximum matching files")] = 50,
        max_matches_per_file: Annotated[int, Field(description="Maximum matches per file")] = 5,
    ) -> str:
        """Search local workspace documentation and config files."""
        try:
            roots = _roots()
            directory = resolve_workspace_path(path, roots, must_exist=True, directory=True)
            results = []
            for item in directory.rglob("*"):
                if len(results) >= max_files:
                    break
                if not item.is_file() or item.suffix.lower() not in DOC_SUFFIXES:
                    continue
                matches = _match_lines(item, query, max_matches_per_file)
                if matches:
                    results.append({"path": str(item), "matches": matches})
            return str(result_dict(True, f"{len(results)} matching file(s)", results=results))
        except Exception as exc:
            return str(result_dict(False, f"Docs search error: {exc}"))

    @mcp.tool()
    async def docs_read_workspace(
        path: Annotated[str, Field(description="Workspace documentation/config path")],
        max_chars: Annotated[int, Field(description="Maximum characters to return")] = 20000,
    ) -> str:
        """Read a local workspace documentation or config file."""
        try:
            file_path = resolve_workspace_path(path, _roots(), must_exist=True, directory=False)
            if file_path.suffix.lower() not in DOC_SUFFIXES:
                return str(result_dict(False, f"Unsupported docs file type: {file_path.suffix}"))
            text = file_path.read_text(encoding="utf-8", errors="replace")
            content, truncated = truncate_text(text, max_chars)
            return str(
                result_dict(
                    True,
                    f"Read docs file: {file_path}",
                    path=str(file_path),
                    content=content,
                    truncated=truncated,
                )
            )
        except Exception as exc:
            return str(result_dict(False, f"Docs read error: {exc}"))
