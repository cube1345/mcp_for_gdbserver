from pathlib import Path

import pytest

from mcp_gdbserver.workspace import resolve_workspace_path, run_process, workspace_roots


def test_resolve_workspace_path_allows_paths_inside_root(tmp_path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    source = root / "Core" / "Src" / "main.c"
    source.parent.mkdir(parents=True)
    source.write_text("int main(void) { return 0; }\n", encoding="utf-8")

    roots = workspace_roots([str(root)])

    assert resolve_workspace_path("Core/Src/main.c", roots, must_exist=True) == source.resolve()


def test_resolve_workspace_path_rejects_paths_outside_root(tmp_path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("nope", encoding="utf-8")

    roots = workspace_roots([str(root)])

    with pytest.raises(ValueError, match="outside workspace roots"):
        resolve_workspace_path(str(outside), roots, must_exist=True)


def test_run_process_captures_nonzero_exit() -> None:
    result = run_process(
        ["python", "-c", "import sys; print('bad'); sys.exit(7)"],
        timeout=10,
    )

    assert result["ok"] is False
    assert result["returncode"] == 7
    assert "bad" in result["stdout"]


def test_workspace_roots_falls_back_when_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    roots = workspace_roots([str(tmp_path / "missing")])

    assert roots == [Path.cwd().resolve()]
