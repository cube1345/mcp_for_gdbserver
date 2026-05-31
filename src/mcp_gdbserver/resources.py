"""MCP Resource definitions and implementations.

Registers GDB-related resources with the FastMCP server.
Resources provide read-only views of the current debug session state.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from .session import GDBSession
from .tools import get_context

logger = logging.getLogger(__name__)


DEBUG_FLOW_GUIDE = {
    "purpose": "Standard order for using this MCP server to control a GDB debug session.",
    "recommended_sequence": [
        {
            "step": 1,
            "tool": "start_gdb_server",
            "intent": "Start the remote GDB protocol server, such as pyOCD, OpenOCD, ST-LINK GDB Server, J-Link GDB Server, or standard gdbserver.",
            "example": 'start_gdb_server() when config.json already defines gdbserver, or start_gdb_server(command="pyocd gdbserver --target cortex_m --port 50000")',
        },
        {
            "step": 2,
            "tool": "start_gdb",
            "intent": "Start the configured GDB executable in MI3 mode.",
            "example": "start_gdb()",
        },
        {
            "step": 3,
            "tool": "load_file",
            "intent": "Load debug symbols from an ELF or AXF file. Use an absolute path whenever possible.",
            "example": 'load_file("E:/project/build/firmware.elf")',
        },
        {
            "step": 4,
            "tool": "connect_target",
            "intent": "Connect GDB to the remote target exposed by the GDB server.",
            "example": 'connect_target("localhost:50000")',
        },
        {
            "step": 5,
            "tool": "break_insert",
            "intent": "Set a breakpoint before running. For embedded targets, main is usually the first useful breakpoint.",
            "example": 'break_insert("main") or break_insert("Core/Src/main.c:120")',
        },
        {
            "step": 6,
            "tool": "continue_execution",
            "intent": "Run until a breakpoint, signal, or target stop event.",
            "example": "continue_execution()",
        },
        {
            "step": 7,
            "tool": "inspect_state",
            "intent": "After the target stops, inspect frame, variables, registers, memory, and call stack.",
            "example": "frame_info(), list_locals(), info_registers(), backtrace()",
        },
    ],
    "notes": [
        "Keil .axf files are ELF files and can be used with load_file.",
        "Call get_status before continuing an unknown session.",
        "Use run_command only when no dedicated MCP tool exists.",
        "For multiple independent GDB processes, pass session_id to tools that support it.",
    ],
}


TOOL_GUIDE = {
    "purpose": "Explain what each tool category is for so an AI client can choose the correct tool.",
    "categories": [
        {
            "name": "lifecycle",
            "tools": [
                "start_gdb_server",
                "stop_gdb_server",
                "start_gdb",
                "connect_target",
                "disconnect",
                "load_file",
                "quit",
                "get_status",
                "switch_session",
                "list_sessions",
            ],
            "when_to_use": "Use these to create, connect, inspect, switch, or tear down debug sessions.",
        },
        {
            "name": "execution_control",
            "tools": [
                "continue_execution",
                "interrupt",
                "step",
                "stepi",
                "next",
                "nexti",
                "finish",
                "until",
                "restart",
            ],
            "when_to_use": "Use these after GDB is started and connected to control target execution.",
        },
        {
            "name": "breakpoints",
            "tools": [
                "break_insert",
                "break_delete",
                "break_disable",
                "break_enable",
                "break_list",
                "catch",
            ],
            "when_to_use": "Use these to stop execution at functions, file lines, addresses, or events.",
            "examples": [
                'break_insert("main")',
                'break_insert("Core/Src/main.c:85")',
                'break_insert("*0x08001234")',
            ],
        },
        {
            "name": "data_and_memory",
            "tools": [
                "print",
                "examine",
                "watch_add",
                "watch_remove",
                "watch_list",
                "watch_refresh",
                "watch_set_enabled",
                "watch_clear",
                "display",
                "set_variable",
                "memory_read",
                "memory_write",
            ],
            "when_to_use": "Use these to inspect, watch, or modify variables, expressions, and raw memory.",
            "examples": [
                'print("motor_speed")',
                'watch_add("motor_speed") then watch_refresh()',
                'memory_read("0x20000000", 64)',
                'set_variable("debug_flag", "1")',
            ],
        },
        {
            "name": "stack_and_threads",
            "tools": [
                "backtrace",
                "select_frame",
                "frame_info",
                "list_locals",
                "list_args",
                "thread_info",
                "thread_select",
            ],
            "when_to_use": "Use these after the target stops to understand where execution is and what local state is visible.",
        },
        {
            "name": "source_disassembly_registers",
            "tools": [
                "disassemble",
                "list_source",
                "info_registers",
                "info_types",
            ],
            "when_to_use": "Use these to inspect code around the current PC, register state, source lines, and type information.",
        },
        {
            "name": "advanced",
            "tools": [
                "run_command",
                "define_hook",
                "flash_and_run",
                "attach",
                "reset_target",
            ],
            "when_to_use": "Use these for backend-specific operations, custom GDB CLI commands, flashing, attaching, or reset flows.",
        },
    ],
    "selection_rules": [
        "Prefer a dedicated structured tool over run_command.",
        "Before using execution-control tools, ensure start_gdb and connect_target have succeeded.",
        "Before inspecting locals or frames, ensure the target is stopped.",
        "For embedded firmware, load_file should normally happen before connect_target so symbols are available.",
    ],
}


TOOL_REFERENCE = {
    "purpose": "Per-tool reference for AI clients. Read this when deciding which MCP tool to call.",
    "tools": {
        "start_gdb_server": {
            "purpose": "Start the remote GDB protocol server process.",
            "use_when": "Use first when the backend server is not already running.",
            "examples": [
                "start_gdb_server()",
                'start_gdb_server(command="pyocd gdbserver --target cortex_m --port 50000")',
            ],
        },
        "stop_gdb_server": {
            "purpose": "Stop the GDB server process started by this MCP server.",
            "use_when": "Use when ending a debug session or changing backend configuration.",
        },
        "start_gdb": {
            "purpose": "Start a GDB process in MI3 mode.",
            "use_when": "Use after the GDB server is ready and before loading symbols or connecting.",
            "examples": ["start_gdb()", 'start_gdb(session_id="motor")'],
        },
        "connect_target": {
            "purpose": "Connect GDB to a remote target such as localhost:50000.",
            "use_when": "Use after start_gdb and usually after load_file.",
            "examples": ['connect_target("localhost:50000")'],
        },
        "disconnect": {
            "purpose": "Disconnect the current GDB session from the remote target.",
            "use_when": "Use before reconnecting to another target or ending target interaction.",
        },
        "attach": {
            "purpose": "Attach GDB to an existing process or target context when supported by the backend.",
            "use_when": "Use for native/process debugging or backends that support attach semantics.",
        },
        "load_file": {
            "purpose": "Load ELF/AXF symbols into GDB.",
            "use_when": "Use before setting source-level breakpoints or inspecting symbols.",
            "examples": ['load_file("E:/project/build/firmware.elf")', 'load_file("E:/project/MDK-ARM/app.axf")'],
        },
        "quit": {
            "purpose": "Quit the GDB process and clean up the session.",
            "use_when": "Use when the debug session is complete or wedged.",
        },
        "get_status": {
            "purpose": "Return current session state, target address, loaded file, GDB PID, and server status.",
            "use_when": "Use before taking action if the current debug state is unknown.",
        },
        "switch_session": {
            "purpose": "Switch the active named GDB session.",
            "use_when": "Use when multiple independent GDB sessions are active.",
        },
        "list_sessions": {
            "purpose": "List tracked GDB sessions and their status.",
            "use_when": "Use to discover existing sessions before switching or cleaning up.",
        },
        "continue_execution": {
            "purpose": "Resume target execution until a breakpoint, signal, exit, or interrupt.",
            "use_when": "Use after connecting and setting desired breakpoints.",
        },
        "interrupt": {
            "purpose": "Interrupt a running target through GDB.",
            "use_when": "Use when target is running and you need to inspect current state.",
        },
        "step": {
            "purpose": "Source-level step into.",
            "use_when": "Use when stopped and you want to enter function calls.",
        },
        "next": {
            "purpose": "Source-level step over.",
            "use_when": "Use when stopped and you want to execute the next source line without entering calls.",
        },
        "stepi": {
            "purpose": "Instruction-level step into.",
            "use_when": "Use for startup code, fault analysis, or code without source lines.",
        },
        "nexti": {
            "purpose": "Instruction-level step over.",
            "use_when": "Use for assembly-level debugging while stepping over calls.",
        },
        "finish": {
            "purpose": "Run until the current function returns.",
            "use_when": "Use after stepping into a function that you want to leave.",
        },
        "until": {
            "purpose": "Run until a specified source line, address, or location.",
            "use_when": "Use to skip forward to a known location without creating a persistent breakpoint.",
        },
        "restart": {
            "purpose": "Restart the inferior or target execution flow when supported.",
            "use_when": "Use when rerunning a debug scenario from the beginning.",
        },
        "break_insert": {
            "purpose": "Create a breakpoint at a function, file:line, or address.",
            "use_when": "Use before continue_execution to stop at an expected point.",
            "examples": ['break_insert("main")', 'break_insert("Core/Src/main.c:120")', 'break_insert("*0x08001234")'],
        },
        "break_delete": {
            "purpose": "Delete one or more breakpoints.",
            "use_when": "Use when a breakpoint is no longer needed or is causing unwanted stops.",
        },
        "break_disable": {
            "purpose": "Temporarily disable one or more breakpoints.",
            "use_when": "Use when a breakpoint should be kept but ignored for now.",
        },
        "break_enable": {
            "purpose": "Re-enable disabled breakpoints.",
            "use_when": "Use when a previously disabled breakpoint should stop execution again.",
        },
        "break_list": {
            "purpose": "List current breakpoints.",
            "use_when": "Use to understand where the AI or user has configured stops.",
        },
        "catch": {
            "purpose": "Set a GDB catchpoint for events such as exceptions, syscalls, or throws when supported.",
            "use_when": "Use for event-driven debugging rather than source-location breakpoints.",
        },
        "print": {
            "purpose": "Evaluate and print an expression in the current frame.",
            "use_when": "Use to inspect variables, pointers, constants, and expressions.",
            "examples": ['print("counter")', 'print("*uart_handle")'],
        },
        "examine": {
            "purpose": "Examine memory using GDB's x command semantics.",
            "use_when": "Use for formatted memory inspection such as words, bytes, strings, or instructions.",
        },
        "display": {
            "purpose": "Configure an expression to be displayed whenever execution stops.",
            "use_when": "Use only when you want GDB's own display command. Prefer watch_add for AI/UI watch lists.",
        },
        "watch_add": {
            "purpose": "Add or update an explicit server-side AI watch expression.",
            "use_when": "Use when the AI or user wants a variable/expression to stay visible across refreshes.",
            "examples": ['watch_add("num1")', 'watch_add("uwTick", refresh=True)'],
        },
        "watch_remove": {
            "purpose": "Remove an expression from the server-side AI watch list.",
            "use_when": "Use when the expression should no longer appear in AI watch/sidebar UI.",
        },
        "watch_list": {
            "purpose": "List watched expressions and their last values/errors.",
            "use_when": "Use to synchronize plugin sidebars or debug UI watch scopes.",
        },
        "watch_refresh": {
            "purpose": "Evaluate watched expressions and update their cached values.",
            "use_when": "Use after target stops, after stepping, or before syncing watch UI.",
        },
        "watch_set_enabled": {
            "purpose": "Enable or disable a watch without removing it.",
            "use_when": "Use to temporarily suppress refreshes while keeping the expression in the list.",
        },
        "watch_clear": {
            "purpose": "Clear all server-side watches, optionally scoped by session.",
            "use_when": "Use when resetting a debug scenario or clearing AI-selected observations.",
        },
        "set_variable": {
            "purpose": "Set a variable or expression value through GDB.",
            "use_when": "Use to modify runtime state for experiments or recovery.",
        },
        "memory_read": {
            "purpose": "Read raw target memory.",
            "use_when": "Use to inspect RAM, peripheral registers, stack, heap, or flash bytes.",
            "examples": ['memory_read("0x20000000", 64)', 'memory_read("0x40021000", 32)'],
        },
        "memory_write": {
            "purpose": "Write raw target memory.",
            "use_when": "Use carefully to patch RAM, registers, or test values during debugging.",
        },
        "backtrace": {
            "purpose": "Show the call stack.",
            "use_when": "Use after a stop, fault, breakpoint, or interrupt to understand how execution arrived there.",
        },
        "select_frame": {
            "purpose": "Select a stack frame for local variable and argument inspection.",
            "use_when": "Use before list_locals, list_args, or print when inspecting non-current frames.",
        },
        "frame_info": {
            "purpose": "Show information about the current stack frame.",
            "use_when": "Use to identify current function, file, line, and address.",
        },
        "list_locals": {
            "purpose": "List local variables in the selected frame.",
            "use_when": "Use after stopping at a source location or selecting a frame.",
        },
        "list_args": {
            "purpose": "List function arguments in the selected frame.",
            "use_when": "Use to inspect call inputs at the current or selected frame.",
        },
        "thread_info": {
            "purpose": "List threads known to GDB.",
            "use_when": "Use for RTOS/native debugging when multiple threads are visible.",
        },
        "thread_select": {
            "purpose": "Select a thread for inspection and control.",
            "use_when": "Use before stack or variable inspection for a specific thread.",
        },
        "disassemble": {
            "purpose": "Disassemble code for a function, address range, or current PC.",
            "use_when": "Use for startup code, optimized code, hard faults, or missing source.",
        },
        "list_source": {
            "purpose": "List source code around a location.",
            "use_when": "Use to inspect nearby source lines after stopping or before setting breakpoints.",
        },
        "info_registers": {
            "purpose": "Show CPU register values.",
            "use_when": "Use after faults, interrupts, breakpoints, or when checking peripheral setup side effects.",
        },
        "info_types": {
            "purpose": "Show C/C++ type information known to GDB.",
            "use_when": "Use when constructing expressions or understanding struct layouts.",
        },
        "run_command": {
            "purpose": "Run an arbitrary GDB CLI command.",
            "use_when": "Use only when no dedicated structured MCP tool exists.",
            "examples": ['run_command("monitor reset halt")', 'run_command("info files")'],
        },
        "define_hook": {
            "purpose": "Define a GDB hook command.",
            "use_when": "Use for repeated custom behavior on GDB events or commands.",
        },
        "flash_and_run": {
            "purpose": "Flash firmware and run the target using backend-specific GDB commands.",
            "use_when": "Use for embedded workflows after loading an ELF/AXF and connecting to target.",
        },
        "reset_target": {
            "purpose": "Reset or reset-halt the embedded target when supported by the GDB server.",
            "use_when": "Use before rerunning firmware or recovering a target in a bad state.",
        },
    },
}


EMBEDDED_TASK_GUIDE = {
    "purpose": "Common embedded-debugging tasks and the tools normally needed for each task.",
    "tasks": [
        {
            "task": "Stop at main",
            "tools": ["start_gdb_server", "start_gdb", "load_file", "connect_target", "break_insert", "continue_execution"],
            "example": 'break_insert("main") then continue_execution()',
        },
        {
            "task": "Check why firmware faults",
            "tools": ["interrupt", "backtrace", "info_registers", "frame_info", "list_source", "disassemble"],
            "example": "Read PC/LR/xPSR and inspect the current frame and surrounding assembly.",
        },
        {
            "task": "Inspect peripheral registers",
            "tools": ["memory_read", "examine", "print", "info_registers"],
            "example": 'memory_read("0x40021000", 64)',
        },
        {
            "task": "Watch a variable through stepping",
            "tools": ["watch_add", "watch_refresh", "step", "next", "continue_execution", "list_locals"],
            "example": 'watch_add("encoder_count") then watch_refresh() after each stop/step',
        },
        {
            "task": "Recover from an unknown running state",
            "tools": ["get_status", "interrupt", "backtrace", "info_registers"],
            "example": "Call get_status; if running, interrupt; then inspect stack and registers.",
        },
    ],
}


def _json_resource(data: dict[str, Any]) -> str:
    """Format a resource response as JSON string."""
    return json.dumps(data, indent=2, ensure_ascii=False)


def _ensure_session() -> GDBSession:
    """Get the GDB session from context, raising if not available."""
    ctx = get_context()
    if not ctx.session.is_alive:
        raise ValueError("GDB session is not started")
    return ctx.session


def register_resources(mcp: FastMCP) -> None:
    """Register all MCP resources with the FastMCP server."""

    @mcp.resource("gdb://guide/overview")
    async def gdb_guide_overview() -> str:
        """AI 使用本 MCP Server 前应读取的总览说明。"""
        return _json_resource({
            "name": "MCP GDB Server",
            "purpose": (
                "Expose GDB/gdbserver debugging through MCP tools so an AI client can "
                "start sessions, connect targets, set breakpoints, inspect variables, "
                "read registers, and control execution."
            ),
            "read_first": [
                "gdb://guide/debug-flow",
                "gdb://guide/tools",
                "gdb://guide/tool-reference",
                "gdb://guide/embedded-tasks",
            ],
            "minimum_successful_flow": [
                "start_gdb_server",
                "start_gdb",
                "load_file",
                "connect_target",
                "break_insert",
                "continue_execution",
            ],
            "important_rule": "Use dedicated MCP tools before falling back to run_command.",
        })

    @mcp.resource("gdb://guide/debug-flow")
    async def gdb_guide_debug_flow() -> str:
        """标准 GDB/MCP 调试流程，帮助 AI 正确排序工具调用。"""
        return _json_resource(DEBUG_FLOW_GUIDE)

    @mcp.resource("gdb://guide/tools")
    async def gdb_guide_tools() -> str:
        """工具分类、用途和选择规则，帮助 AI 理解每个工具该何时使用。"""
        return _json_resource(TOOL_GUIDE)

    @mcp.resource("gdb://guide/tool-reference")
    async def gdb_guide_tool_reference() -> str:
        """逐个工具的作用、使用时机和示例，帮助 AI 精确选择工具。"""
        return _json_resource(TOOL_REFERENCE)

    @mcp.resource("gdb://guide/embedded-tasks")
    async def gdb_guide_embedded_tasks() -> str:
        """嵌入式调试常见任务和推荐工具组合。"""
        return _json_resource(EMBEDDED_TASK_GUIDE)

    @mcp.resource("gdb://status")
    async def gdb_status() -> str:
        """当前调试器状态。"""
        ctx = get_context()
        status = ctx.session.get_status()
        if ctx.server_mgr:
            status["gdb_server"] = ctx.server_mgr.get_status()
        return _json_resource(status)

    @mcp.resource("gdb://registers")
    async def gdb_registers() -> str:
        """当前寄存器值。"""
        session = _ensure_session()
        try:
            text = await session.send_raw_command("info registers")
            # Parse register output
            registers = []
            for line in text.strip().splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    reg_entry = {
                        "name": parts[0],
                        "value": parts[1],
                        "hex": parts[1] if parts[1].startswith("0x") else None,
                    }
                    if len(parts) >= 3 and parts[2].startswith("0x"):
                        reg_entry["hex"] = parts[2]
                    registers.append(reg_entry)
            return _json_resource({"registers": registers})
        except Exception as e:
            return _json_resource({"error": str(e), "registers": []})

    @mcp.resource("gdb://backtrace")
    async def gdb_backtrace() -> str:
        """当前调用栈。"""
        session = _ensure_session()
        try:
            output = await session.send_mi_command("-stack-list-frames")
            frames = []
            if output.result and not output.is_error:
                stack = output.result.results.get("stack", [])
                for entry in stack:
                    frame = entry.get("frame", entry) if isinstance(entry, dict) else entry
                    frames.append({
                        "frame_num": frame.get("level", "?"),
                        "func": frame.get("func", "??"),
                        "file": frame.get("file", frame.get("fullname", "??")),
                        "line": frame.get("line", "?"),
                        "addr": frame.get("addr", "??"),
                    })
            return _json_resource({"frames": frames})
        except Exception as e:
            return _json_resource({"error": str(e), "frames": []})

    @mcp.resource("gdb://breakpoints")
    async def gdb_breakpoints() -> str:
        """当前断点列表。"""
        session = _ensure_session()
        try:
            output = await session.send_mi_command("-break-list")
            breakpoints = []
            if output.result and not output.is_error:
                table = output.result.results.get("BreakpointTable", {})
                body = table.get("body", [])
                for entry in body:
                    bkpt = entry.get("bkpt", entry) if isinstance(entry, dict) else entry
                    breakpoints.append(bkpt)
            return _json_resource({"breakpoints": breakpoints})
        except Exception as e:
            return _json_resource({"error": str(e), "breakpoints": []})

    @mcp.resource("gdb://threads")
    async def gdb_threads() -> str:
        """线程列表。"""
        session = _ensure_session()
        try:
            output = await session.send_mi_command("-thread-info")
            threads = []
            current = None
            if output.result and not output.is_error:
                threads = output.result.results.get("threads", [])
                current = output.result.results.get("current-thread-id")
            return _json_resource({
                "threads": threads,
                "current_thread": current,
            })
        except Exception as e:
            return _json_resource({"error": str(e), "threads": []})

    @mcp.resource("gdb://memory/{address}/{size}")
    async def gdb_memory(address: str, size: str) -> str:
        """读取指定地址和大小的内存数据。

        Args:
            address: 起始地址 (如 "0x20000000")
            size: 读取的字节数
        """
        session = _ensure_session()
        try:
            num_bytes = int(size)
            output = await session.send_mi_command(
                f"-data-read-memory-bytes {address} {num_bytes}"
            )
            if output.result and not output.is_error:
                memory = output.result.results.get("memory", [])
                return _json_resource({"address": address, "size": num_bytes, "memory": memory})
            return _json_resource({"error": output.error_message, "address": address})
        except Exception as e:
            return _json_resource({"error": str(e), "address": address})

    @mcp.resource("gdb://locals")
    async def gdb_locals() -> str:
        """局部变量。"""
        session = _ensure_session()
        try:
            output = await session.send_mi_command("-stack-list-variables --all-values")
            variables = []
            if output.result and not output.is_error:
                variables = output.result.results.get("variables", [])
            return _json_resource({"locals": variables})
        except Exception as e:
            return _json_resource({"error": str(e), "locals": []})

    @mcp.resource("gdb://args")
    async def gdb_args() -> str:
        """函数参数。"""
        session = _ensure_session()
        try:
            output = await session.send_mi_command("-stack-list-arguments --all-values 0 0")
            args = []
            if output.result and not output.is_error:
                stack_args = output.result.results.get("stack-args", [])
                for entry in stack_args:
                    frame = entry.get("frame", {})
                    args.extend(frame.get("args", []))
            return _json_resource({"args": args})
        except Exception as e:
            return _json_resource({"error": str(e), "args": []})

    @mcp.resource("gdb://frame")
    async def gdb_frame() -> str:
        """当前帧信息。"""
        session = _ensure_session()
        try:
            output = await session.send_mi_command("-stack-info-frame")
            if output.result and not output.is_error:
                frame = output.result.results.get("frame", {})
                return _json_resource(frame)
            return _json_resource({"error": output.error_message})
        except Exception as e:
            return _json_resource({"error": str(e)})

    @mcp.resource("gdb://sections")
    async def gdb_sections() -> str:
        """目标节区信息。"""
        session = _ensure_session()
        try:
            text = await session.send_raw_command("info files")
            sections = []
            for line in text.strip().splitlines():
                line = line.strip()
                if line and not line.startswith(" ") and "0x" in line:
                    sections.append(line)
            return _json_resource({"sections": sections, "raw": text.strip()})
        except Exception as e:
            return _json_resource({"error": str(e), "sections": []})
