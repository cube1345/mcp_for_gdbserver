# MCP GDB Server Handoff

## Project Purpose

This project exposes GDB and gdbserver debugging capabilities as an MCP server.
Its main value is letting an AI client, such as Codex, Cursor, Claude Desktop, or a
custom VS Code extension, control an embedded debug session through structured MCP
tools instead of manually driving a terminal.

The intended flow is:

```text
AI client or UI
  -> MCP GDB Server
  -> GDB MI3
  -> gdbserver-compatible backend
  -> MCU target
```

Supported backend types include standard GNU `gdbserver` and custom GDB servers
such as pyOCD, OpenOCD, ST-LINK GDB Server, or J-Link GDB Server.

For STM32 + DAPLink, the practical local flow is:

```text
Codex or VS Code extension
  -> http://127.0.0.1:8765/mcp
  -> mcp-gdbserver
  -> arm-none-eabi-gdb
  -> pyocd gdbserver
  -> CMSIS-DAP / DAPLink probe
  -> STM32 target
```

## Repository Layout

Important files:

- `run.py`: no-install launcher that prepends `src/` to `PYTHONPATH`.
- `src/mcp_gdbserver/main.py`: CLI entry point.
- `src/mcp_gdbserver/config.py`: config loading and merge logic.
- `src/mcp_gdbserver/server.py`: FastMCP server creation and transport startup.
- `src/mcp_gdbserver/tools.py`: MCP tool registration and tool implementations.
- `src/mcp_gdbserver/resources.py`: MCP resource registration.
- `src/mcp_gdbserver/session.py`: GDB process lifecycle and MI command handling.
- `src/mcp_gdbserver/gdb_server_mgr.py`: external GDB server process management.
- `src/mcp_gdbserver/mi_parser.py`: GDB MI output parser.
- `config.example.json`: standard gdbserver example.
- `config.example.stlink.json`: ST-LINK custom server example.

Local-only files such as `config.json` may contain machine-specific tool paths and
should not be committed upstream unless converted into a safe example file.

## Current Local Enhancements

This working copy contains changes beyond the original project:

- Windows-native GDB session support in `session.py`.
- Optional MCP transport selection through `transport`.
- Streamable HTTP support for Codex using `/mcp`.
- Local DAPLink/pyOCD configuration in `config.json`.
- Workspace-scoped filesystem, CMake build, probe, serial, SVD, VS Code bridge,
  Git, docs, and explicit AI Watch tools.
- Server-side AI Watch list via `watch_add`, `watch_list`, `watch_refresh`,
  `watch_remove`, `watch_set_enabled`, and `watch_clear`.

If contributing upstream, split these into focused pull requests. The Windows GDB
session support can stand alone. The Streamable HTTP transport support should be a
separate PR.

## Basic Usage

Install dependencies from the repository root:

```powershell
python -m pip install -e .[dev]
```

Run the MCP server:

```powershell
python run.py --config config.json
```

For Codex Streamable HTTP usage, the server should log something similar to:

```text
Starting MCP streamable_http server on 127.0.0.1:8765
```

Register the MCP server with Codex:

```powershell
codex mcp add gdb --url http://127.0.0.1:8765/mcp
codex mcp get gdb
```

Expected Codex MCP configuration:

```text
gdb
  transport: streamable_http
  url: http://127.0.0.1:8765/mcp
```

If Codex shows `Tools: (none)`, check that it is not using the old `/sse` URL.
The local Codex config is usually:

```text
C:\Users\<user>\.codex\config.toml
```

The `gdb` entry should point to:

```toml
[mcp_servers.gdb]
url = "http://127.0.0.1:8765/mcp"
```

## Example DAPLink Configuration

For a DAPLink/CMSIS-DAP probe using pyOCD:

```json
{
  "gdb_path": "E:/EmbeddedDevelopment/SoftWare/STM32CubeCLT_1.18.0/GNU-tools-for-STM32/bin/arm-none-eabi-gdb.exe",
  "host": "127.0.0.1",
  "port": 8765,
  "transport": "streamable_http",
  "default_target": "localhost:50000",
  "gdb_init_commands": [
    "set pagination off",
    "set confirm off"
  ],
  "timeout_seconds": 30,
  "log_level": "INFO",
  "workspace_roots": [
    "E:/EmbeddedDevelopment/WorkSpace/F407VGT6"
  ],
  "cmake_path": "cmake",
  "pyocd_path": "pyocd",
  "openocd_path": "openocd",
  "git_path": "git",
  "gdbserver": {
    "mode": "custom",
    "command": "pyocd gdbserver --target cortex_m --port 50000 --frequency 4000000"
  }
}
```

Use full executable paths if tools are not on `PATH`.

The generic `cortex_m` target is useful for initial connection, halt, register
inspection, and stepping. Reliable STM32F407 flash programming may require a
proper pyOCD target pack or OpenOCD with `cmsis-dap.cfg` and `stm32f4x.cfg`.

Useful checks:

```powershell
Get-Command arm-none-eabi-gdb, pyocd, openocd -ErrorAction SilentlyContinue
pyocd list
pyocd list --targets
```

## Typical Debug Flow Through MCP

Once the MCP tools are visible to the client, the expected tool sequence is:

```text
start_gdb_server
start_gdb
load_file("<absolute path to firmware.elf or firmware.axf>")
connect_target("localhost:50000")
break_insert("main")
watch_add("variable_to_track")
continue_execution
```

After stopping at `main`, useful tools include:

```text
info_registers
backtrace
list_locals
watch_refresh
watch_list
step
next
memory_read
run_command
```

Use `print` for one-off expression inspection. Use `watch_add` only when the AI
or user wants an expression to remain visible and refresh across stops/steps.
The VS Code extension should treat `watch_list` as the canonical AI Watch state.

Keil `.axf` files are ELF files and can usually be passed to `load_file`.

## Windows Notes

The original implementation used Unix PTYs for GDB:

```python
pty.openpty()
```

That path depends on Unix-only modules such as `termios`, so it fails on native
Windows Python. The Windows-compatible approach is:

- avoid importing `pty` and `select` on Windows;
- launch GDB with `subprocess.PIPE`;
- read GDB output from a background thread;
- write commands through `stdin`;
- use `CTRL_BREAK_EVENT` for interrupt handling.

This preserves the PTY path for Linux/macOS while allowing native Windows use.

## VS Code Extension Direction

A VS Code extension is a good fit because this server is already process-based
and workspace-oriented. The extension should be written in TypeScript using the
standard VS Code Extension API.

Recommended stack:

- TypeScript for the extension.
- `@types/vscode` and the VS Code extension host.
- `esbuild` or `tsup` for fast bundling.
- Node `child_process` for starting and stopping `python run.py --config ...`.
- VS Code `TreeView` or `WebviewView` for status, sessions, targets, and logs.
- Workspace configuration under `.vscode/` or a generated project `config.json`.

The first MVP should not reimplement GDB. It should orchestrate this Python MCP
server.

Suggested MVP features:

- Find `.elf` and `.axf` files in the active workspace.
- Generate or edit an MCP GDB config.
- Start and stop the Python MCP server.
- Show server logs in a VS Code output channel.
- Detect DAPLink through `pyocd list`.
- Copy or apply the Codex MCP registration command.
- Provide commands such as `Start Server`, `Stop Server`, `Open Config`, and
  `Copy MCP URL`.

Later features:

- One-click `connect target`.
- One-click `flash and run`.
- Stop at `main`.
- Registers view.
- Breakpoints view.
- Memory read panel.
- AI Watch view backed by MCP `watch_*` tools.
- AI prompt templates for common embedded debugging tasks.

Recommended extension architecture:

```text
VS Code commands
  -> Extension service layer
  -> Process manager for mcp-gdbserver
  -> Config manager
  -> Optional MCP client wrapper
  -> UI: TreeView/Webview/OutputChannel
```

The extension can either:

- only manage the MCP server and let Codex use the MCP tools directly; or
- also act as an MCP client and expose GUI buttons that call MCP tools itself.

For a first version, prefer the first option. It is simpler and keeps the debug
logic centralized in this Python project.

### Watch and VS Code UI Contract

The Python MCP server cannot call VS Code APIs directly. It exposes two related
but separate mechanisms:

- `watch_*` tools: server-side state for AI-selected persistent expressions.
  These are the source of truth for the MCU auto-debug sidebar and any debug
  variable scope that mirrors AI Watch values.
- `vscode_*` bridge tools: queued UI commands for a VS Code extension to drain
  and execute with the native VS Code API.

Recommended extension behavior:

```text
target stopped or step completed
  -> call watch_refresh()
  -> call watch_list()
  -> render AI Watch sidebar/scope from watch_list()
  -> optionally drain vscode_bridge_* commands for editor/UI actions
```

Do not infer persistent watches from every `print` call. `print` means inspect
once; `watch_add` means keep observing.

## Common Failure Modes

`ModuleNotFoundError: No module named 'pydantic'`

The `pip` and `python` commands are using different Python environments. Use:

```powershell
python -m pip install -e .[dev]
```

`ModuleNotFoundError: No module named 'termios'`

The original Unix PTY implementation is being used on Windows. Apply the Windows
session compatibility changes.

Codex shows `gdb Tools: (none)`

Check:

- the MCP server is running before Codex starts;
- Codex is configured with `/mcp`, not `/sse`;
- the server is using `transport: "streamable_http"`;
- restart the Codex session after changing MCP config.

Validate the server independently:

```powershell
python -c "from mcp_gdbserver.session import GDBSession; print('ok')"
python run.py --help
```

Use an MCP client probe to confirm tool registration if needed. A healthy server
should expose tools such as `start_gdb_server`, `start_gdb`, `load_file`, and
`connect_target`. For the current expanded build it should also expose tools
such as `watch_add`, `fs_read_text`, `cmake_build_if_stale`,
`vscode_sync_debug_state`, and `svd_read_register`.

## Contribution Guidance

For an upstream PR, keep changes focused:

- Windows support PR: only `session.py`.
- Transport support PR: `config.py`, `server.py`, `main.py`, and docs.
- Do not commit local `config.json` with machine-specific paths.
- Add a safe example config if needed.

Validation before submitting:

```powershell
python run.py --help
python -c "from mcp_gdbserver.session import GDBSession; print('ok')"
ruff check src tests
pytest
```
