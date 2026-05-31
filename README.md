# MCP GDB Server

基于 [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) 的 GDB 远程调试服务器。

通过 SSE/HTTP 传输协议暴露 GDB 调试能力，支持标准 GNU gdbserver 和自定义 GDB Server（ST-LINK、OpenOCD、J-Link 等）。

## 特性

- **完整调试工具覆盖** — GDB、Watch、Filesystem、CMake、Probe、Serial、SVD、VS Code Bridge、Git、Docs 等 100+ MCP 工具
- **双模式 GDB Server** — 标准 gdbserver 和自定义 GDB Server（ST-LINK 等）
- **SSE/HTTP 传输** — 兼容所有 MCP 客户端（Claude Desktop、Cursor 等）
- **ELF 文件路径加载** — 通过文件系统绝对路径加载，无需 base64 编码
- **灵活配置** — CLI 参数 / JSON 配置文件 / 环境变量，优先级递减
- **GDB MI3 协议** — 使用 Machine Interface 实现结构化通信
- **显式 AI Watch 列表** — `watch_add` / `watch_refresh` / `watch_list` 让 AI 选择的变量可持续同步到侧边栏和调试 UI

## 系统要求

- Python 3.10+
- GDB（如 `arm-none-eabi-gdb`）已安装
- gdbserver 或自定义 GDB Server（如 ST-LINK_gdbserver）

## 安装依赖

```bash
pip install mcp>=1.0.0 anyio>=4.0 httpx>=0.27 pydantic>=2.0 starlette uvicorn
```

## 快速开始

### 直接运行（无需安装）

```bash
# 标准 gdbserver 模式
python3 run.py \
  --gdb-path arm-none-eabi-gdb \
  --gdbserver-port 50000 \
  --gdbserver-multi

# ST-LINK 模式
python3 run.py \
  --gdb-path arm-none-eabi-gdb \
  --target localhost:50000 \
  --gdb-server-cmd "/path/to/ST-LINK_gdbserver -p 50000 -cp /path --swd"

# 或赋予执行权限后直接运行
chmod +x run.py
./run.py --config config.example.json
```

### 安装后运行（可选）

```bash
# 开发模式安装
pip install -e .

# 然后可以直接使用 mcp-gdbserver 命令
mcp-gdbserver \
  --gdb-path arm-none-eabi-gdb \
  --gdbserver-port 50000 \
  --gdbserver-multi
```

### 2. ST-LINK GDB Server 模式

```bash
# 使用配置文件启动
mcp-gdbserver --config config.example.stlink.json

# 或通过命令行指定
mcp-gdbserver \
  --gdb-path arm-none-eabi-gdb \
  --target localhost:50000 \
  --gdb-server-cmd "/path/to/ST-LINK_gdbserver -p 50000 -cp /path --swd --serial-number xxx --halt --apid 1"
```

### 3. MCP 客户端配置

在 Claude Desktop 或其他 MCP 客户端的配置文件中添加：

```json
{
  "mcpServers": {
    "gdb": {
      "url": "http://localhost:8765/sse"
    }
  }
}
```

## CLI 参数

```
usage: mcp-gdbserver [-h] [--gdb-path PATH] [--host HOST] [--port PORT]
                     [--target HOST:PORT] [--gdbserver-port PORT]
                     [--gdbserver-multi] [--gdbserver-once]
                     [--gdbserver-attach PID] [--gdb-server-cmd CMD]
                     [--config FILE] [--verbose]

选项:
  --gdb-path              GDB 可执行文件路径 (默认: arm-none-eabi-gdb)
  --host                  MCP SSE 服务器绑定地址 (默认: 0.0.0.0)
  --port, -p              MCP SSE 服务器端口 (默认: 8765)
  --target, -t            默认远程目标 (格式: host:port)

标准 GNU gdbserver 参数:
  --gdbserver-port        gdbserver 监听端口 (默认: 50000)
  --gdbserver-multi       启用 --multi 扩展远程模式
  --gdbserver-once        启用 --once 单次会话模式
  --gdbserver-attach PID  附加到指定进程

自定义 GDB Server 参数:
  --gdb-server-cmd, -g    GDB Server 完整命令行

通用参数:
  --config, -c            JSON 配置文件路径
  --verbose, -v           启用 DEBUG 级别日志
```

## 环境变量

所有配置项均可通过 `MCP_GDB_` 前缀的环境变量设置：

| 环境变量                      | 对应配置项            |
| ----------------------------- | --------------------- |
| `MCP_GDB_GDB_PATH`          | `gdb_path`          |
| `MCP_GDB_HOST`              | `host`              |
| `MCP_GDB_PORT`              | `port`              |
| `MCP_GDB_TARGET`            | `default_target`    |
| `MCP_GDB_TIMEOUT`           | `timeout_seconds`   |
| `MCP_GDB_LOG_LEVEL`         | `log_level`         |
| `MCP_GDB_GDBSERVER_PORT`    | `gdbserver.port`    |
| `MCP_GDB_GDBSERVER_MULTI`   | `gdbserver.multi`   |
| `MCP_GDB_GDBSERVER_ONCE`    | `gdbserver.once`    |
| `MCP_GDB_GDBSERVER_MODE`    | `gdbserver.mode`    |
| `MCP_GDB_GDBSERVER_COMMAND` | `gdbserver.command` |

配置优先级：**CLI 参数 > 环境变量 > 配置文件 > 默认值**

## MCP 工具列表

本节列出主要工具类别。完整用途可通过 MCP 资源 `gdb://guide/tools` 和
`gdb://guide/tool-reference` 查看。

### 生命周期工具

| 工具                 | 说明                                    |
| -------------------- | --------------------------------------- |
| `start_gdb_server` | 启动 GDB Server 进程（标准/自定义模式） |
| `stop_gdb_server`  | 停止 GDB Server 进程                    |
| `start_gdb`        | 启动 GDB 进程（MI3 模式）               |
| `connect_target`   | 连接到远程目标                          |
| `disconnect`       | 断开远程目标连接                        |
| `load_file`        | 加载 ELF 可执行文件（通过绝对路径）     |
| `quit`             | 退出 GDB 会话                           |
| `get_status`       | 获取当前调试器状态                      |

### 执行控制工具

| 工具                   | 说明               |
| ---------------------- | ------------------ |
| `continue_execution` | 继续执行程序       |
| `interrupt`          | 中断正在运行的程序 |
| `stepi`              | 汇编级单步进入     |
| `step`               | 源码级单步进入     |
| `nexti`              | 汇编级单步跳过     |
| `next`               | 源码级单步跳过     |
| `finish`             | 执行到当前函数返回 |
| `until`              | 执行到指定位置     |
| `restart`            | 重新启动程序       |

### 断点工具

| 工具              | 说明                          |
| ----------------- | ----------------------------- |
| `break_insert`  | 插入断点                      |
| `break_delete`  | 删除断点                      |
| `break_disable` | 禁用断点                      |
| `break_enable`  | 启用断点                      |
| `break_list`    | 列出所有断点                  |
| `catch`         | 设置捕获点（异常/系统调用等） |

### 数据查看工具

| 工具                  | 说明                                                             |
| --------------------- | ---------------------------------------------------------------- |
| `print`             | 计算并打印表达式                                                 |
| `examine`           | 检查内存内容                                                     |
| `watch_add`         | 将表达式加入 MCP Server 维护的 AI Watch 列表                     |
| `watch_remove`      | 从 AI Watch 列表移除表达式                                       |
| `watch_list`        | 列出 Watch 表达式及最近一次值/错误                               |
| `watch_refresh`     | 重新求值 Watch 表达式                                            |
| `watch_set_enabled` | 启用/禁用某个 Watch 表达式                                       |
| `watch_clear`       | 清空 Watch 列表                                                  |
| `display`           | 设置 GDB 自身 display 表达式；AI/UI 长期观察优先用 `watch_add` |
| `set_variable`      | 修改变量值                                                       |
| `memory_read`       | 读取内存（十六进制）                                             |
| `memory_write`      | 写入内存                                                         |

`print` 表示一次性查看。AI 或用户希望变量持续出现在 MCU 自动调试侧边栏、
调试变量 Scope 或插件 UI 中时，应使用 `watch_add`，并在每次停止/单步后调用
`watch_refresh`。

### 堆栈/线程工具

| 工具              | 说明             |
| ----------------- | ---------------- |
| `backtrace`     | 显示调用栈       |
| `select_frame`  | 选择栈帧         |
| `frame_info`    | 显示当前栈帧信息 |
| `list_locals`   | 列出局部变量     |
| `list_args`     | 列出函数参数     |
| `thread_info`   | 显示线程信息     |
| `thread_select` | 选择线程         |

### 反汇编/源码工具

| 工具               | 说明         |
| ------------------ | ------------ |
| `disassemble`    | 反汇编代码   |
| `list_source`    | 显示源代码   |
| `info_registers` | 显示寄存器值 |
| `info_types`     | 显示类型信息 |

### 高级工具

| 工具              | 说明                         |
| ----------------- | ---------------------------- |
| `run_command`   | 执行任意 GDB CLI 命令        |
| `define_hook`   | 定义 GDB 钩子命令            |
| `flash_and_run` | 烧录固件并运行（嵌入式专用） |

### 工作区与构建工具

| 工具                                                       | 说明                                     |
| ---------------------------------------------------------- | ---------------------------------------- |
| `fs_workspace_roots`                                     | 查看允许访问的工作区根目录               |
| `fs_list` / `fs_find` / `fs_stat`                    | 列目录、查找文件、查看文件元数据         |
| `fs_read_text` / `fs_write_text` / `fs_replace_text` | 读取、写入、替换工作区文本文件           |
| `cmake_configure`                                        | 执行 `cmake --preset <preset>`         |
| `cmake_build`                                            | 执行 `cmake --build --preset <preset>` |
| `build_check_elf_stale`                                  | 检查 ELF/AXF 是否比源码旧                |
| `cmake_build_if_stale`                                   | ELF/AXF 过期时自动构建                   |

这些工具受 `workspace_roots` 限制，不会访问配置根目录之外的路径。

### Probe / OpenOCD / Serial 工具

| 工具                                                                                            | 说明                                   |
| ----------------------------------------------------------------------------------------------- | -------------------------------------- |
| `probe_check_ports`                                                                           | 检查 3333/50000/8765 等调试端口占用    |
| `pyocd_list` / `pyocd_targets`                                                              | 检测 CMSIS-DAP/DAPLink 与 pyOCD target |
| `openocd_version` / `openocd_probe_scan`                                                    | 检查 OpenOCD 与短流程扫描              |
| `gdb_server_read_output` / `probe_tail_log`                                                 | 读取后端输出或日志尾部                 |
| `serial_list_ports` / `serial_open` / `serial_read` / `serial_write` / `serial_close` | 串口日志与命令交互                     |

### SVD / 外设寄存器工具

| 工具                                              | 说明                               |
| ------------------------------------------------- | ---------------------------------- |
| `svd_load` / `svd_status`                     | 加载并查看 CMSIS-SVD 状态          |
| `svd_list_peripherals` / `svd_list_registers` | 列出外设和寄存器定义               |
| `svd_decode_register_value`                     | 解码一个原始寄存器值               |
| `svd_read_register` / `svd_read_peripheral`   | 通过 GDB 内存读并按 SVD 解码寄存器 |

### VS Code Bridge 工具

| 工具                                                                                       | 说明                               |
| ------------------------------------------------------------------------------------------ | ---------------------------------- |
| `vscode_set_source_breakpoint` / `vscode_remove_source_breakpoint`                     | 请求 VS Code 设置/删除源码断点红点 |
| `vscode_set_watch` / `vscode_remove_watch`                                             | 请求 VS Code 原生 Watch 面板更新   |
| `vscode_open_run_and_debug` / `vscode_reveal_location`                                 | 打开调试视图、跳转源代码位置       |
| `vscode_sync_debug_state`                                                                | 请求插件同步 GDB MCP 状态          |
| `vscode_bridge_list_commands` / `vscode_bridge_drain_commands` / `vscode_bridge_ack` | 扩展侧消费桥接命令队列             |

VS Code Bridge 只是 UI 命令队列。真正影响 GDB 执行的仍是 GDB 工具；
AI Watch 的状态源是 `watch_*` 工具，而不是 `vscode_set_watch`。

### Git / Docs 工具

| 工具                                                                     | 说明                          |
| ------------------------------------------------------------------------ | ----------------------------- |
| `git_status` / `git_diff` / `git_recent_commits`                   | 查看仓库状态、差异和近期提交  |
| `git_commit_paths`                                                     | 只提交显式指定路径            |
| `git_restore_paths`                                                    | 带确认 token 丢弃指定路径改动 |
| `git_debug_report`                                                     | 生成调试相关 Git 报告         |
| `docs_reference` / `docs_search_workspace` / `docs_read_workspace` | 查官方参考入口和本地文档      |

## MCP 资源列表

| 资源 URI                          | 说明                     |
| --------------------------------- | ------------------------ |
| `gdb://status`                  | 当前调试器完整状态       |
| `gdb://registers`               | 当前寄存器值             |
| `gdb://backtrace`               | 当前调用栈               |
| `gdb://breakpoints`             | 当前断点列表             |
| `gdb://threads`                 | 线程信息                 |
| `gdb://memory/{address}/{size}` | 读取指定地址和大小的内存 |
| `gdb://locals`                  | 当前栈帧的局部变量       |
| `gdb://args`                    | 当前栈帧的函数参数       |
| `gdb://frame`                   | 当前栈帧详细信息         |
| `gdb://sections`                | 可执行文件的段信息       |
| `gdb://guide/overview`          | MCP GDB Server 总览      |
| `gdb://guide/debug-flow`        | 推荐调试流程             |
| `gdb://guide/tools`             | 工具分类说明             |
| `gdb://guide/tool-reference`    | 单个工具用途参考         |
| `gdb://guide/embedded-tasks`    | 嵌入式常见任务流程       |

## 典型调试流程

### MCP 客户端调用顺序

```
1. start_gdb_server()        → 启动 GDB Server（或已通过 CLI 自动启动）
2. start_gdb()               → 启动 GDB 进程
3. load_file("/path/firmware.elf")  → 加载 ELF 文件
4. connect_target("localhost:50000") → 连接到远程目标
5. break_insert("main")      → 在 main 设置断点
6. watch_add("variable")     → 可选：加入 AI Watch 长期观察
7. continue_execution()      → 继续执行
8. watch_refresh()           → 停止后刷新 Watch 值
9. print("other")            → 一次性查看其他表达式
10. backtrace()              → 查看调用栈
11. step() / next()          → 单步调试
```

### 嵌入式 ST-LINK 调试示例

```bash
# 1. 启动 MCP 服务器（ST-LINK 模式）
mcp-gdbserver \
  --gdb-path arm-none-eabi-gdb \
  --target localhost:50000 \
  -g "/opt/STMicroelectronics/ST-LINK_gdbserver -p 50000 -cp /opt/STM32Cube/STM32CubeProgrammer/bin --swd"

# 2. MCP 客户端中调用工具：
#    start_gdb_server()                    # 启动 ST-LINK GDB Server
#    start_gdb()                           # 启动 arm-none-eabi-gdb
#    load_file("/project/build/firmware.elf")
#    connect_target("localhost:50000")     # 连接到 ST-LINK
#    flash_and_run()                       # 烧录并运行
#    break_insert("main")
#    continue_execution()
```

## 项目结构

```
src/mcp_gdbserver/
├── __init__.py          # 包初始化
├── __main__.py          # python -m 入口
├── main.py              # CLI 主入口
├── config.py            # 配置管理（CLI/文件/环境变量）
├── mi_parser.py         # GDB MI 输出解析器
├── gdb_server_mgr.py    # GDB Server 进程管理器
├── session.py           # GDB 会话管理器（PTY + MI3）
├── tools.py             # 核心 GDB 调试工具
├── watch_tools.py       # AI Watch 表达式列表与刷新工具
├── filesystem_tools.py  # 工作区文件读写工具
├── build_tools.py       # CMake configure/build 与 ELF 过期检查
├── probe_tools.py       # pyOCD/OpenOCD/端口/后端日志诊断
├── serial_tools.py      # 串口日志与命令交互
├── svd.py               # CMSIS-SVD 解析
├── svd_tools.py         # 外设寄存器读取与 bitfield 解码
├── vscode_bridge.py     # VS Code 扩展 UI 命令队列
├── git_tools.py         # Git 状态/diff/提交/报告工具
├── docs_tools.py        # 文档参考与本地文档搜索工具
├── workspace.py         # workspace_roots 安全边界与命令执行辅助
├── resources.py         # MCP 资源与工具指南
└── server.py            # FastMCP 服务器配置与启动
```

## 配置文件示例

参见：

- [`config.example.json`](config.example.json) — 标准 gdbserver 模式
- [`config.example.stlink.json`](config.example.stlink.json) — ST-LINK 自定义模式

## 许可证

MIT
