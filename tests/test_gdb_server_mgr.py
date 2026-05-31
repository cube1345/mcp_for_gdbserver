import subprocess

from mcp_gdbserver import gdb_server_mgr
from mcp_gdbserver.config import GdbServerConfig
from mcp_gdbserver.gdb_server_mgr import GdbServerManager


class FakeProcess:
    def __init__(self, *, exit_on_terminate: bool = True) -> None:
        self.pid = 1234
        self.terminated = False
        self.killed = False
        self._alive = True
        self._exit_on_terminate = exit_on_terminate

    def poll(self) -> int | None:
        return None if self._alive else 0

    def terminate(self) -> None:
        self.terminated = True
        if self._exit_on_terminate:
            self._alive = False

    def kill(self) -> None:
        self.killed = True
        self._alive = False

    def wait(self, timeout: float | None = None) -> int:
        if self._alive:
            raise subprocess.TimeoutExpired("fake-gdb-server", timeout)
        return 0


def _manager_with_process(process: FakeProcess) -> GdbServerManager:
    manager = GdbServerManager(GdbServerConfig(mode="custom", command="fake-server"))
    manager._process = process
    return manager


def test_stop_uses_windows_process_termination(monkeypatch) -> None:
    process = FakeProcess()
    manager = _manager_with_process(process)

    monkeypatch.setattr(gdb_server_mgr.os, "name", "nt")
    monkeypatch.setattr(
        gdb_server_mgr.os,
        "getpgid",
        lambda _pid: (_ for _ in ()).throw(AssertionError("getpgid should not be used")),
        raising=False,
    )

    manager.stop()

    assert process.terminated
    assert not process.killed


def test_stop_kills_windows_process_after_timeout(monkeypatch) -> None:
    process = FakeProcess(exit_on_terminate=False)
    manager = _manager_with_process(process)

    monkeypatch.setattr(gdb_server_mgr.os, "name", "nt")
    monkeypatch.setattr(
        gdb_server_mgr.os,
        "getpgid",
        lambda _pid: (_ for _ in ()).throw(AssertionError("getpgid should not be used")),
        raising=False,
    )

    manager.stop()

    assert process.terminated
    assert process.killed
