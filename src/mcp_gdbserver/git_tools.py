"""Workspace-scoped Git MCP tools."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .tools import get_context
from .workspace import result_dict, resolve_workspace_path, run_process, workspace_roots


def _roots() -> list[Path]:
    return workspace_roots(get_context().workspace_roots)


def _git_path() -> str:
    return get_context().git_path


def _cwd(path: str) -> Path:
    return resolve_workspace_path(path, _roots(), must_exist=True, directory=True)


def _relative_paths(paths: list[str], cwd: Path) -> list[str]:
    roots = _roots()
    resolved = [resolve_workspace_path(path, roots, must_exist=False) for path in paths]
    return [os.path.relpath(path, cwd) for path in resolved]


def register_git_tools(mcp: FastMCP) -> None:
    """Register Git tools."""

    @mcp.tool()
    async def git_status(
        cwd: Annotated[str, Field(description="Workspace directory inside the git repo")] = ".",
        max_output: Annotated[int, Field(description="Maximum output characters")] = 20000,
    ) -> str:
        """Run `git status --short --branch`."""
        try:
            directory = _cwd(cwd)
            result = run_process(
                [_git_path(), "status", "--short", "--branch"],
                cwd=directory,
                max_output=max_output,
            )
            return str(result_dict(bool(result["ok"]), "Git status completed" if result["ok"] else "Git status failed", **result))
        except Exception as exc:
            return str(result_dict(False, f"Git status error: {exc}"))

    @mcp.tool()
    async def git_diff(
        cwd: Annotated[str, Field(description="Workspace directory inside the git repo")] = ".",
        paths: Annotated[list[str] | None, Field(description="Optional paths to diff")] = None,
        staged: Annotated[bool, Field(description="Show staged diff")] = False,
        max_output: Annotated[int, Field(description="Maximum output characters")] = 30000,
    ) -> str:
        """Run `git diff` for optional workspace paths."""
        try:
            directory = _cwd(cwd)
            args = [_git_path(), "diff"]
            if staged:
                args.append("--staged")
            if paths:
                args.append("--")
                args.extend(_relative_paths(paths, directory))
            result = run_process(args, cwd=directory, max_output=max_output)
            return str(result_dict(bool(result["ok"]), "Git diff completed" if result["ok"] else "Git diff failed", **result))
        except Exception as exc:
            return str(result_dict(False, f"Git diff error: {exc}"))

    @mcp.tool()
    async def git_recent_commits(
        cwd: Annotated[str, Field(description="Workspace directory inside the git repo")] = ".",
        limit: Annotated[int, Field(description="Number of commits")] = 10,
        max_output: Annotated[int, Field(description="Maximum output characters")] = 20000,
    ) -> str:
        """List recent commits."""
        try:
            directory = _cwd(cwd)
            result = run_process(
                [_git_path(), "log", f"-{limit}", "--oneline", "--decorate"],
                cwd=directory,
                max_output=max_output,
            )
            return str(result_dict(bool(result["ok"]), "Git log completed" if result["ok"] else "Git log failed", **result))
        except Exception as exc:
            return str(result_dict(False, f"Git log error: {exc}"))

    @mcp.tool()
    async def git_commit_paths(
        message: Annotated[str, Field(description="Commit message")],
        paths: Annotated[list[str], Field(description="Workspace paths to stage and commit")],
        cwd: Annotated[str, Field(description="Workspace directory inside the git repo")] = ".",
        max_output: Annotated[int, Field(description="Maximum output characters")] = 30000,
    ) -> str:
        """Stage explicit paths and create a commit."""
        if not paths:
            return str(result_dict(False, "Provide at least one path to commit"))
        try:
            directory = _cwd(cwd)
            rel_paths = _relative_paths(paths, directory)
            add_result = run_process(
                [_git_path(), "add", "--", *rel_paths],
                cwd=directory,
                max_output=max_output,
            )
            if not add_result["ok"]:
                return str(result_dict(False, "Git add failed", add=add_result))
            commit_result = run_process(
                [_git_path(), "commit", "-m", message],
                cwd=directory,
                max_output=max_output,
            )
            return str(
                result_dict(
                    bool(commit_result["ok"]),
                    "Git commit completed" if commit_result["ok"] else "Git commit failed",
                    add=add_result,
                    commit=commit_result,
                )
            )
        except Exception as exc:
            return str(result_dict(False, f"Git commit error: {exc}"))

    @mcp.tool()
    async def git_restore_paths(
        paths: Annotated[list[str], Field(description="Workspace paths to restore")],
        confirm_token: Annotated[str, Field(description="Must be discard-local-changes")],
        cwd: Annotated[str, Field(description="Workspace directory inside the git repo")] = ".",
        staged: Annotated[bool, Field(description="Also unstage changes")] = False,
        max_output: Annotated[int, Field(description="Maximum output characters")] = 20000,
    ) -> str:
        """Discard local changes for explicit paths after a confirmation token."""
        if confirm_token != "discard-local-changes":
            return str(result_dict(False, "Refusing to restore paths without confirm_token=discard-local-changes"))
        if not paths:
            return str(result_dict(False, "Provide at least one path to restore"))
        try:
            directory = _cwd(cwd)
            rel_paths = _relative_paths(paths, directory)
            results = []
            if staged:
                results.append(
                    run_process(
                        [_git_path(), "restore", "--staged", "--", *rel_paths],
                        cwd=directory,
                        max_output=max_output,
                    )
                )
            results.append(
                run_process(
                    [_git_path(), "restore", "--", *rel_paths],
                    cwd=directory,
                    max_output=max_output,
                )
            )
            ok = all(result["ok"] for result in results)
            return str(
                result_dict(
                    ok,
                    "Git restore completed" if ok else "Git restore failed",
                    results=results,
                )
            )
        except Exception as exc:
            return str(result_dict(False, f"Git restore error: {exc}"))

    @mcp.tool()
    async def git_debug_report(
        cwd: Annotated[str, Field(description="Workspace directory inside the git repo")] = ".",
        max_output: Annotated[int, Field(description="Maximum output characters per command")] = 20000,
    ) -> str:
        """Generate a compact Git report for debugging changes."""
        try:
            directory = _cwd(cwd)
            status = run_process(
                [_git_path(), "status", "--short", "--branch"],
                cwd=directory,
                max_output=max_output,
            )
            diff_stat = run_process(
                [_git_path(), "diff", "--stat"],
                cwd=directory,
                max_output=max_output,
            )
            recent = run_process(
                [_git_path(), "log", "-5", "--oneline", "--decorate"],
                cwd=directory,
                max_output=max_output,
            )
            ok = bool(status["ok"] and diff_stat["ok"] and recent["ok"])
            return str(
                result_dict(
                    ok,
                    "Git debug report generated" if ok else "Git debug report has errors",
                    status=status,
                    diff_stat=diff_stat,
                    recent=recent,
                )
            )
        except Exception as exc:
            return str(result_dict(False, f"Git report error: {exc}"))
