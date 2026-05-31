"""CMake/build MCP tools for embedded debug workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .tools import get_context
from .workspace import result_dict, resolve_workspace_path, run_process, workspace_roots


SOURCE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".h",
    ".hh",
    ".hpp",
    ".s",
    ".S",
    ".ld",
    ".cmake",
}

SKIP_DIRS = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "cmake-build-debug",
    "cmake-build-release",
}


def _roots() -> list[Path]:
    return workspace_roots(get_context().workspace_roots)


def _cmake_path() -> str:
    return get_context().cmake_path


def _build_response(process_result: dict[str, Any], success_message: str, failure_message: str) -> str:
    ok = bool(process_result["ok"])
    return str(
        result_dict(
            ok,
            success_message if ok else failure_message,
            **process_result,
        )
    )


def _iter_sources(root: Path) -> list[Path]:
    sources: list[Path] = []
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file() and (path.name == "CMakeLists.txt" or path.suffix in SOURCE_SUFFIXES):
            sources.append(path)
    return sources


def _is_elf_stale(elf_path: Path, source_paths: list[Path]) -> tuple[bool, list[str]]:
    if not elf_path.exists():
        return True, ["ELF does not exist"]

    elf_mtime = elf_path.stat().st_mtime
    newer = [str(path) for path in source_paths if path.exists() and path.stat().st_mtime > elf_mtime]
    return bool(newer), newer


def register_build_tools(mcp: FastMCP) -> None:
    """Register CMake build tools."""

    @mcp.tool()
    async def cmake_configure(
        preset: Annotated[str, Field(description="CMake configure preset")] = "Debug",
        cwd: Annotated[str, Field(description="Workspace directory containing CMakePresets.json")] = ".",
        timeout: Annotated[float, Field(description="Timeout in seconds")] = 120.0,
        max_output: Annotated[int, Field(description="Maximum stdout/stderr characters each")] = 20000,
    ) -> str:
        """Run `cmake --preset <preset>` inside a workspace directory."""
        try:
            directory = resolve_workspace_path(cwd, _roots(), must_exist=True, directory=True)
            result = run_process(
                [_cmake_path(), "--preset", preset],
                cwd=directory,
                timeout=timeout,
                max_output=max_output,
            )
            return _build_response(result, "CMake configure completed", "CMake configure failed")
        except Exception as exc:
            return str(result_dict(False, f"CMake configure error: {exc}"))

    @mcp.tool()
    async def cmake_build(
        preset: Annotated[str, Field(description="CMake build preset")] = "Debug",
        cwd: Annotated[str, Field(description="Workspace directory containing CMakePresets.json")] = ".",
        target: Annotated[str | None, Field(description="Optional build target")] = None,
        clean_first: Annotated[bool, Field(description="Pass --clean-first")] = False,
        timeout: Annotated[float, Field(description="Timeout in seconds")] = 300.0,
        max_output: Annotated[int, Field(description="Maximum stdout/stderr characters each")] = 30000,
    ) -> str:
        """Run `cmake --build --preset <preset>` inside a workspace directory."""
        try:
            directory = resolve_workspace_path(cwd, _roots(), must_exist=True, directory=True)
            args = [_cmake_path(), "--build", "--preset", preset]
            if target:
                args.extend(["--target", target])
            if clean_first:
                args.append("--clean-first")
            result = run_process(args, cwd=directory, timeout=timeout, max_output=max_output)
            return _build_response(result, "CMake build completed", "CMake build failed")
        except Exception as exc:
            return str(result_dict(False, f"CMake build error: {exc}"))

    @mcp.tool()
    async def build_check_elf_stale(
        elf_path: Annotated[str, Field(description="ELF/AXF path to check")],
        cwd: Annotated[str, Field(description="Source root to scan when source_paths is omitted")] = ".",
        source_paths: Annotated[list[str] | None, Field(description="Optional source files to compare")] = None,
    ) -> str:
        """Check whether an ELF/AXF appears older than project sources."""
        try:
            roots = _roots()
            elf = resolve_workspace_path(elf_path, roots, must_exist=False, directory=False)
            if source_paths:
                sources = [
                    resolve_workspace_path(path, roots, must_exist=True, directory=False)
                    for path in source_paths
                ]
            else:
                source_root = resolve_workspace_path(cwd, roots, must_exist=True, directory=True)
                sources = _iter_sources(source_root)
            stale, reasons = _is_elf_stale(elf, sources)
            return str(
                result_dict(
                    True,
                    "ELF is stale" if stale else "ELF is up to date",
                    stale=stale,
                    elf_path=str(elf),
                    checked_sources=len(sources),
                    newer_sources=reasons[:100],
                    newer_source_count=len(reasons),
                )
            )
        except Exception as exc:
            return str(result_dict(False, f"ELF stale check error: {exc}"))

    @mcp.tool()
    async def cmake_build_if_stale(
        elf_path: Annotated[str, Field(description="ELF/AXF path to check before building")],
        preset: Annotated[str, Field(description="CMake build preset")] = "Debug",
        cwd: Annotated[str, Field(description="Workspace directory containing CMakePresets.json")] = ".",
        source_paths: Annotated[list[str] | None, Field(description="Optional source files to compare")] = None,
        timeout: Annotated[float, Field(description="Timeout in seconds")] = 300.0,
        max_output: Annotated[int, Field(description="Maximum stdout/stderr characters each")] = 30000,
    ) -> str:
        """Build with CMake only when the ELF/AXF is missing or stale."""
        try:
            roots = _roots()
            directory = resolve_workspace_path(cwd, roots, must_exist=True, directory=True)
            elf = resolve_workspace_path(elf_path, roots, must_exist=False, directory=False)
            if source_paths:
                sources = [
                    resolve_workspace_path(path, roots, must_exist=True, directory=False)
                    for path in source_paths
                ]
            else:
                sources = _iter_sources(directory)
            stale, reasons = _is_elf_stale(elf, sources)
            if not stale:
                return str(
                    result_dict(
                        True,
                        "ELF is up to date; build skipped",
                        built=False,
                        stale=False,
                        elf_path=str(elf),
                        checked_sources=len(sources),
                    )
                )

            result = run_process(
                [_cmake_path(), "--build", "--preset", preset],
                cwd=directory,
                timeout=timeout,
                max_output=max_output,
            )
            return str(
                result_dict(
                    bool(result["ok"]),
                    "CMake build completed" if result["ok"] else "CMake build failed",
                    built=True,
                    stale=True,
                    stale_reasons=reasons[:100],
                    newer_source_count=len(reasons),
                    **result,
                )
            )
        except Exception as exc:
            return str(result_dict(False, f"CMake build-if-stale error: {exc}"))
