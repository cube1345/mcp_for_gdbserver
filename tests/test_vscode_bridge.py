from mcp_gdbserver.vscode_bridge import VscodeBridgeQueue


def test_bridge_queue_lists_and_acknowledges_commands() -> None:
    queue = VscodeBridgeQueue()

    first = queue.enqueue("debug.setSourceBreakpoint", {"file_path": "main.c", "line": 12})
    second = queue.enqueue("debug.setWatchExpression", {"expression": "counter"})

    assert queue.size == 2
    assert [item.id for item in queue.list()] == [first.id, second.id]

    assert queue.ack([first.id]) == 1
    assert queue.size == 1
    assert queue.list()[0].id == second.id


def test_bridge_queue_drains_in_fifo_order() -> None:
    queue = VscodeBridgeQueue()

    first = queue.enqueue("one")
    second = queue.enqueue("two")
    third = queue.enqueue("three")

    drained = queue.drain(2)

    assert [item.id for item in drained] == [first.id, second.id]
    assert queue.size == 1
    assert queue.list()[0].id == third.id
