"""Workspace path and subprocess helpers for auxiliary MCP tools."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any


DEFAULT_MAX_OUTPUT = 20000


def result_dict(success: bool, message: str, **kwargs: Any) -> dict[str, Any]:
    """Create a standard tool result dictionary."""
    result = {"success": success, "message": message}
    result.update(kwargs)
    return result


def workspace_roots(configured_roots: list[str]) -> list[Path]:
    """Normalize configured workspace roots to absolute existing paths."""
    roots = configured_roots or ["."]
    normalized: list[Path] = []
    for root in roots:
        path = Path(root).expanduser()
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved.exists() and resolved.is_dir() and resolved not in normalized:
            normalized.append(resolved)
    if not normalized:
        normalized.append(Path.cwd().resolve())
    return normalized


def is_relative_to(path: Path, root: Path) -> bool:
    """Return whether path is inside root, compatible with Python 3.10."""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_workspace_path(
    requested_path: str | None,
    roots: list[Path],
    *,
    must_exist: bool = False,
    directory: bool | None = None,
) -> Path:
    """Resolve a path and ensure it stays inside one configured workspace root."""
    raw = requested_path or "."
    input_path = Path(raw).expanduser()

    candidates: list[Path]
    if input_path.is_absolute():
        candidates = [input_path]
    else:
        existing = [(root / input_path) for root in roots if (root / input_path).exists()]
        candidates = existing or [roots[0] / input_path]

    last_candidate = candidates[0].resolve()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate.absolute()
        last_candidate = resolved
        if any(is_relative_to(resolved, root) for root in roots):
            if must_exist and not resolved.exists():
                raise ValueError(f"Path does not exist: {requested_path}")
            if directory is True and resolved.exists() and not resolved.is_dir():
                raise ValueError(f"Path is not a directory: {requested_path}")
            if directory is False and resolved.exists() and not resolved.is_file():
                raise ValueError(f"Path is not a file: {requested_path}")
            return resolved

    root_list = ", ".join(str(root) for root in roots)
    raise ValueError(f"Path is outside workspace roots: {last_candidate} (roots: {root_list})")


def workspace_relative(path: Path, roots: list[Path]) -> str:
    """Return a stable workspace-relative display path when possible."""
    for root in roots:
        if is_relative_to(path, root):
            return str(path.relative_to(root)).replace("\\", "/")
    return str(path)


def truncate_text(text: str, max_chars: int = DEFAULT_MAX_OUTPUT) -> tuple[str, bool]:
    """Truncate command output while preserving whether truncation happened."""
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def run_process(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout: float = 120.0,
    max_output: int = DEFAULT_MAX_OUTPUT,
) -> dict[str, Any]:
    """Run a subprocess without invoking a shell."""
    try:
        completed = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        stdout, stdout_truncated = truncate_text(completed.stdout or "", max_output)
        stderr, stderr_truncated = truncate_text(completed.stderr or "", max_output)
        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "truncated": stdout_truncated or stderr_truncated,
            "command": args,
            "cwd": str(cwd) if cwd else os.getcwd(),
        }
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
            "truncated": False,
            "command": args,
            "cwd": str(cwd) if cwd else os.getcwd(),
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        stdout, stdout_truncated = truncate_text(stdout, max_output)
        stderr, stderr_truncated = truncate_text(stderr, max_output)
        return {
            "ok": False,
            "returncode": None,
            "stdout": stdout,
            "stderr": stderr or f"Timed out after {timeout} seconds",
            "truncated": stdout_truncated or stderr_truncated,
            "command": args,
            "cwd": str(cwd) if cwd else os.getcwd(),
            "timeout": timeout,
        }
