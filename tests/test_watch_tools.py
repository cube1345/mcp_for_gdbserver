from mcp_gdbserver.watch_tools import WatchStore


def test_watch_store_adds_and_updates_without_duplicates() -> None:
    store = WatchStore()

    first, created = store.add("num1", session_id="default", format="x")
    second, created_again = store.add("num1", session_id="default", format="d", enabled=False)

    assert created is True
    assert created_again is False
    assert first is second
    assert second.format == "d"
    assert second.enabled is False
    assert len(store.list()) == 1


def test_watch_store_keeps_session_scopes_separate() -> None:
    store = WatchStore()

    store.add("uwTick", session_id="default")
    store.add("uwTick", session_id="motor")

    assert len(store.list()) == 2
    assert len(store.list(session_id="default")) == 1
    assert len(store.list(session_id="motor")) == 1


def test_watch_store_remove_enable_and_clear() -> None:
    store = WatchStore()

    store.add("counter", session_id="default", enabled=True)
    entry = store.set_enabled("counter", False, session_id="default")

    assert entry is not None
    assert entry.enabled is False
    assert store.list(enabled_only=True) == []

    assert store.remove("missing", session_id="default") is False
    assert store.remove("counter", session_id="default") is True

    store.add("a", session_id="default")
    store.add("b", session_id="motor")
    assert store.clear(session_id="default") == 1
    assert [entry.expression for entry in store.list()] == ["b"]
    assert store.clear() == 1
