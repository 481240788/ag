# Doraemon Agent

基于 Python、FastAPI、OpenAI 兼容模型接口和 MCP（Model Context Protocol）的异步工具调用 Agent。项目将模型交互、工具执行、会话记忆和 Web 接入拆分为独立模块，提供可配置的运行预算、结构化结果、任务状态推送及分层测试，适合本地运行、工具集成与 Agent 工程实践。

目前采用单进程内存状态和 MCP stdio 子进程架构。已实现多会话并发和会话内串行执行；身份认证、分布式状态存储及持久化任务调度尚未实现。

## 工程架构

```text
浏览器（HTML / CSS / JavaScript）
  │ HTTP：提交请求、创建任务、取消任务、清除会话
  │ SSE：运行状态与最终结果
  ▼
FastAPI 接入层 ── TaskRegistry（任务句柄、事件队列、取消）
  │ 请求校验、request_id、异常响应、应用生命周期
  ▼
Agent Runtime ── ConversationStore（历史记录、会话锁）
  │ 模型/工具循环、预算控制、调用记录、结果归一化
  ├── LLM Client ── OpenAI 兼容 Chat Completions 服务
  └── MCP Manager ── stdio ── MCP Tool Server
                                │ 工具注册、按工具限并发
                                ├── 搜索 / 高德天气与路线 / 12306
                                └── 文件 / 时间 / 可选本机 Python

横向模块：Settings 配置校验 · Pydantic 数据契约 · JSON 日志 · 文件路径策略
```

### 模块职责

| 模块 | 工程职责 |
| --- | --- |
| `main/web_app.py` | FastAPI 应用工厂、HTTP/SSE 接口、请求上下文、异常处理和启停管理 |
| `main/task_registry.py` | 保存异步任务及事件队列，处理取消和服务关闭时的任务回收 |
| `Agent/agent.py` | 组装消息、执行模型与工具循环、控制预算、保存成功对话 |
| `LLM/llm.py` | 封装异步模型调用，记录模型返回的 token 用量与调用耗时 |
| `MCP_server/mcp_manager.py` | 管理 stdio 会话、缓存工具定义、转换工具协议、异常重连 |
| `MCP_server/mcp_server.py` | 统一注册工具，按配置决定是否启用本机代码执行 |
| `MCP_server/concurrency.py` | 按工具名称使用信号量控制并发，包装同步与异步工具 |
| `LLMTools/` | 工具参数处理、外部服务适配及结构化结果返回 |
| `memory/` | `ConversationStore` 抽象及进程内实现，维护会话锁和历史裁剪 |
| `models/results.py` | `AgentRunResult`、`ToolCallRecord`、`ToolResult` 和终止原因枚举 |
| `config/settings.py` | 环境配置加载、类型校验、默认值与缓存 |
| `observability/` | 请求/会话上下文、JSON 日志和常见凭据字段脱敏 |
| `security/path_policy.py` | 文件工具允许目录、敏感路径与符号链接检查 |
| `Prompt/`、`ErrorClass/`、`path_manager/` | 提示词、应用异常及项目路径定位 |
| `main/static/` | 无独立前端构建步骤的 Web 界面 |
| `tests/unit/`、`tests/integration/` | 单元测试与真实 MCP 子进程集成测试 |
| `evals/` | 评测用例定义与用例结构校验 |
| `examples/` | 文件工具默认工作目录 |

### 一次请求的执行过程

1. Web 层校验 `session_id` 和消息，生成 `request_id`。
2. Agent 获取会话锁，读取历史并组装系统提示词和当前问题。
3. 复用 MCP 会话与工具定义，调用模型。
4. 模型请求工具时，检查迭代次数、工具调用总量和重复调用，再顺序执行工具。
5. 将 `ToolResult` 回填消息，继续模型调用；模型生成最终回答后保存本轮用户消息与回答。
6. 返回 `AgentRunResult`；异步任务通过 SSE 发布运行阶段和最终结果。

工具返回 `ok=false` 时，结果仍会反馈给模型，供其解释失败或调整调用；工具服务异常与预算触发则通过终止原因区分。失败或取消的运行不会按成功对话写入历史。

## 运行控制与并发模型

| 控制层 | 当前实现 | 作用范围 |
| --- | --- | --- |
| 会话串行 | 每个 `session_id` 对应一把异步锁 | 同会话请求排队，不同会话可并发 |
| 模型超时 | `LLM_TIMEOUT_SECONDS` | 单次模型调用 |
| 工具超时 | `TOOL_TIMEOUT_SECONDS` | 单次工具调用，包含工具排队时间 |
| Agent 超时 | `AGENT_TIMEOUT_SECONDS` | 获得会话锁并进入执行预算后的运行；不含等待会话锁的时间 |
| 迭代预算 | `MAX_AGENT_ITERATIONS` | 单次运行允许的工具调用轮数 |
| 调用预算 | `MAX_TOOL_CALLS` | 单次运行实际记录的工具调用数量 |
| 重复检测 | 工具名与规范化 JSON 参数签名 | 第三次相同调用在执行前终止 |
| 工具并发 | 每个工具独立信号量 | 单个 MCP 服务进程内共享，不是每秒请求限流 |

单次 Agent 运行中的多个工具按顺序执行。工具并发额度主要约束多个会话同时使用同一工具的场景，各工具之间不共用额度。

默认工具并发上限：

| 工具 | 并发数 |
| --- | --- |
| `search_information` | 2 |
| `weather_query_gaode` | 3 |
| `route_planning` | 2 |
| `query_train_tickets` | 1 |
| `get_current_time` | 8 |
| `read_file_content`、`list_directory` | 各 4 |
| `write_new_file`、`execute_local_python_unsafe` | 各 1 |

`TOOL_CONCURRENCY_LIMITS` 接受 JSON 对象，覆盖指定工具的默认值；值必须为正整数。未配置的新工具默认并发数为 1。同步工具通过工作线程执行，取消后会等待底层线程结束再释放额度，因此超时与取消不保证底层工作立即停止。

历史默认最多保存 100 条消息，并按字符估算 token 后删除较旧消息。`HISTORY_MAX_TOKENS` 是历史裁剪预算，不是整个模型请求的严格 token 上限；系统提示词、当前输入和本轮工具消息还会占用上下文。

## 快速开始

### 环境与安装

需要 Python 3.11+，以及支持 Chat Completions 和 Tool Calling 的模型服务。依赖在 `requirements.txt` 中统一维护，包含运行和测试依赖；部分依赖使用版本范围，当前没有完整依赖锁文件。

在项目根目录执行：

```bash
python -m venv .venv
```

Windows PowerShell：

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Linux/macOS：

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

### 配置

在 `.env` 中填写以下配置，示例中的占位内容需要替换为实际值：

```env
MODEL_NAME=your-tool-calling-model
LLM_BASE_URL=https://your-provider.example/v1
LLM_API_KEY=your-api-key

# 按需配置外部工具
SEARCH_API_KEY=your-serpapi-key
GAODE_MAP_API=your-amap-key

ENABLE_LOCAL_PYTHON_EXECUTION=false
APP_ENVIRONMENT=development
LOG_LEVEL=INFO
```

运行参数的**代码默认值**与仓库 `.env.example` 的**示例覆盖值**不同：

| 配置项 | 代码默认值 | `.env.example` 值 | 说明 |
| --- | --- | --- | --- |
| `MAX_AGENT_ITERATIONS` | 10 | 15 | 工具迭代轮数 |
| `MAX_TOOL_CALLS` | 16 | 30 | 工具调用总量 |
| `AGENT_TIMEOUT_SECONDS` | 120 | 500 | Agent 执行预算，秒 |
| `LLM_TIMEOUT_SECONDS` | 60 | 500 | 单次模型超时，秒 |
| `TOOL_TIMEOUT_SECONDS` | 15 | 30 | 单次工具超时，秒 |
| `HISTORY_MAX_TOKENS` | 4000 | 30000 | 历史消息估算 token 预算 |
| `PYTHON_MAX_OUTPUT_CHARS` | 20000 | 20000 | 本机 Python 输出字符上限 |

例如，单独调整路线工具的并发额度：

```env
TOOL_CONCURRENCY_LIMITS='{"route_planning":4}'
```

同名配置优先读取进程环境变量，再读取 `.env`。模型和外部服务配置兼容部分旧的小写名称，建议统一使用大写名称，避免混用。配置由 `get_settings()` 缓存，修改后需重启服务；并发配置不会自动开启本机 Python 工具。

### 启动

```bash
python -m main.web_app
```

访问 `http://127.0.0.1:8000`，交互式接口文档位于 `/docs`。该入口启用了自动重载，适合开发。需要关闭重载时可使用：

```bash
python -m uvicorn main.web_app:app --host 127.0.0.1 --port 8000 --workers 1
```

Web 应用通过 lifespan 启动 MCP 子进程、初始化会话并缓存工具列表；退出时先取消并等待注册任务，再关闭 MCP 连接和子进程。

```bash
python -m main.main
```

命令行入口运行固定问题的演示，用于验证调用链，并非交互式终端客户端。

## Docker 部署

需要 Docker Engine / Docker Desktop（Linux 容器模式）和 Docker Compose v2。在项目根目录执行以下命令。已有 `.env` 时直接复用，不要覆盖；首次配置可复制容器模板：

```powershell
# Windows PowerShell：仅在不存在 .env 时复制
if (!(Test-Path .env)) { Copy-Item docker/.env.docker.example .env }
```

```bash
# Linux/macOS：仅在不存在 .env 时复制
test -f .env || cp docker/.env.docker.example .env
```

填写 `.env` 中的真实模型名称、地址和密钥，再启动：

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose logs -f --tail=100 agent
```

访问 `http://127.0.0.1:8000`。容器内通过 `0.0.0.0:8000` 提供服务，宿主机只绑定回环地址；运行单 worker，不开启自动重载。MCP 由应用在同一容器内启动，无需额外服务或端口。`init: true` 用于子进程回收，应用停止保留 60 秒退出时间。

| 文件 | 职责 |
| --- | --- |
| `docker/Dockerfile` | Python 3.11 slim 镜像、依赖安装、非 root 用户和服务启动命令 |
| `.dockerignore` | 排除密钥配置、Git、缓存、测试及本地示例数据，缩小构建上下文 |
| `compose.yaml` | 环境注入、端口、持久化卷、进程退出、HTTP 检查及日志轮转 |
| `docker/.env.docker.example` | 不含真实密钥的部署配置模板 |

Compose 从 `.env` 注入配置，并强制设置生产环境与关闭本机 Python 执行；服务级 `environment` 优先于 `env_file`，参见 [Docker Compose 服务配置](https://docs.docker.com/reference/compose-file/services/)。`.env` 不会复制进镜像。当前依赖安装复用 `requirements.txt`，因此镜像也包含其中的测试依赖。

`/app/examples` 使用命名卷 `agent_examples`，首次启动为空，不会自动导入宿主机 `examples/`。文件工具创建的内容可在重建容器后保留；需要导入现有文件时可执行 `docker compose cp examples/. agent:/app/examples/`，随后确认文件可由容器用户 UID/GID `10001:10001` 访问。会话与任务仍在内存中，不会随该卷持久化。

如需直接使用宿主机目录，可将卷挂载改为 `./examples:/app/examples`；Linux 上需确保该目录允许 UID 10001 写入。命名卷是默认选择，可避免宿主机绑定目录的权限差异。

日常操作：

```bash
# 更新代码或依赖后重建
docker compose up -d --build

# 修改 .env 后重建容器以重新注入配置
docker compose up -d --force-recreate

# 停止并移除容器，保留文件卷
docker compose down
```

不要使用 `docker compose down -v`，除非确实要删除持久化文件。健康检查仅验证首页 HTTP 可响应，不验证模型凭据或外部工具；容器标记 unhealthy 不会单独触发自动重启。若模型服务运行在宿主机，容器内的 `127.0.0.1` 指向容器自身，需要改成容器可达的宿主机地址。

当前工程仍按单实例使用，对外开放前需补齐下文的访问控制。构建需要网络访问镜像仓库和 Python 包源，运行时需要访问配置的模型及工具服务。

## 接口与数据契约

### HTTP / SSE 接口

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/chat` | 等待完整结果 |
| `POST` | `/tasks` | 创建后台任务，返回 `202` 与任务标识 |
| `GET` | `/tasks/{task_id}/events` | SSE 接收状态和最终结果 |
| `DELETE` | `/tasks/{task_id}` | 请求取消任务 |
| `DELETE` | `/sessions/{session_id}` | 清除历史；会等待该会话正在执行的运行结束 |

`/chat` 和 `/tasks` 共用请求格式；`session_id` 必须为 UUID，`message` 长度为 1～10000 字符：

```json
{
  "session_id": "b592a1dd-47ba-43b8-9660-71ec8c141765",
  "message": "现在几点？"
}
```

`/chat` 返回 `success`、`answer`、`stop_reason`、`request_id`、`session_id` 和 `duration_ms`。`/tasks` 返回 `task_id`、`request_id` 和 `session_id`，随后订阅事件：

```text
data: {"type":"status","status":"thinking"}

data: {"type":"status","status":"tool_call","tool":"get_current_time"}

data: {"type":"result","status":"completed","data":{...}}
```

SSE 推送运行阶段和最终结果，不逐 token 输出回答。最终 `data` 是完整 `AgentRunResult`，包含工具参数与结果；事件接口不应被视为已脱敏的公开数据接口。取消通过 `cancelled` 事件表示，不属于 `StopReason` 枚举。

事件队列目前是消费式队列，适合单个订阅者，不支持广播、事件重放或断线续传。断开 SSE 连接不会自动取消后台任务。

### 结构化运行结果

| 模型 | 主要字段 |
| --- | --- |
| `AgentRunResult` | `answer`、`stop_reason`、`iterations`、`model_calls`、`tool_calls`、`duration_ms`、`token_usage` |
| `ToolCallRecord` | `name`、`arguments`、`result`、`duration_ms` |
| `ToolResult` | `ok`、`data`、`error_code`、`error_message`、`retryable` |

`stop_reason` 包括 `completed`、`max_iterations`、`tool_call_limit`、`repeated_tool_call`、`timeout`、`tool_error`、`model_error`。超时或异常结果保留已经完成的模型调用所返回的 token 统计，未返回的用量不计入；这不是供应商账单统计。

当前 HTTP 映射：正常完成 `200`，异步创建 `202`，迭代上限/重复调用 `409`，参数校验失败 `422`，模型/工具服务错误 `502`，执行超时 `504`，未知异常 `500`。任务不存在或已无法取消时返回 `404`。

已知接口缺口：`/chat` 的状态码映射尚未包含 `tool_call_limit`，触发该终止原因时会落入内部异常处理；不能将其描述为已支持的 `409` 响应。异步任务的最终结果直接携带该终止原因。

## 工具集成

| 工具 | 功能 | 外部依赖 |
| --- | --- | --- |
| `search_information` | Google 搜索 | SerpApi，`SEARCH_API_KEY` |
| `weather_query_gaode` | 高德天气查询 | 高德服务，`GAODE_MAP_API` |
| `route_planning` | 驾车、步行、公共交通路线 | 高德服务，`GAODE_MAP_API` |
| `query_train_tickets` | 12306 直达车次、时刻和余票查询 | 12306 网页接口，无额外 API Key |
| `get_current_time` | 当前时间 | 服务器时钟 |
| `read_file_content` | 读取 UTF-8 文件，最大 5MB | 默认限 `examples/` |
| `list_directory` | 列出目录 | 默认限 `examples/` |
| `write_new_file` | 创建文件，不覆盖已有文件 | 默认限 `examples/` |
| `execute_local_python_unsafe` | 本机执行 Python，默认不注册 | 显式启用且非 production 环境 |

12306 工具接受具体车站名或三字母电报码、北京时间日期 `YYYY-MM-DD`，支持出发时间、车次类型、排序和数量过滤；不实现铁路中转、票价、订票或抢票。该工具适配官方网页使用的接口，上游可用性与返回格式可能变化，实时余票以官方页面为准。自动化测试使用模拟 HTTP 响应，不代表真实接口可用性已验证。

### 新增工具

1. 在 `LLMTools/` 中实现带类型注解和清晰参数说明的函数，统一返回 `ToolResult.success(...)` 或 `ToolResult.failure(...)`。
2. 在 `MCP_server/mcp_server.py` 中导入函数并通过 `register_tool` 注册，让工具经过统一并发包装。
3. 需要自定义额度时更新默认配置，或使用 `TOOL_CONCURRENCY_LIMITS` 覆盖。异步工具内部的阻塞调用仍需主动放到工作线程。
4. 为参数校验、成功、外部失败和超时补充单元测试；涉及注册变更时验证 MCP 工具列表。
5. 重启应用，使 MCP 重新加载工具定义并刷新缓存。

`Agent` 支持注入 `settings`、`llm_client`、`mcp_manager` 和 `conversation_store`；`create_app(agent_instance=...)` 支持替换运行时，便于在测试中隔离外部模型和服务。扩展持久化记忆时可实现 `ConversationStore`，多实例部署还需要处理跨进程会话互斥，不能只替换消息存储。

## 可观测性与安全边界

日志采用 JSON 格式，通过 `request_id` 和 `session_id` 关联请求、模型调用与工具执行。主要事件包括 `mcp_started`、`mcp_reconnect`、`model_call_completed`、`tool_call_completed` 和 `agent_run_finished`。

工具完成日志包含 `tool_name`、`duration_ms`、`tool_ok`、`error_code` 和 `retryable`，可区分调用完成与业务成功。Agent 完成日志记录 `stop_reason`、耗时和 token 汇总。常规调用日志不主动记录完整 Prompt、工具参数或结果，并对常见凭据字段脱敏；这不等同于任意业务内容都已脱敏。

文件工具通过路径策略限制访问 `examples/`，拒绝目录穿越、敏感文件及符号链接绕过，并禁止覆盖写入。本机 Python 直接在宿主机执行，仅允许显式设置 `ENABLE_LOCAL_PYTHON_EXECUTION=true` 且 `APP_ENVIRONMENT` 非 `production` 时注册；超时、输出截断和临时文件清理不构成操作系统级沙盒。

MCP 常驻会话在调用异常后重连并重试一次，临时连接模式不执行该恢复流程。重试没有提供业务幂等或恰好一次执行保证，带副作用的新工具需要自行设计重复执行保护。

## 测试与验证

在项目根目录运行：

```bash
python -m pytest -q
```

按层验证：

```bash
python -m pytest tests/unit -q
python -m pytest tests/integration -q
```

| 测试层 | 覆盖重点 | 外部依赖方式 |
| --- | --- | --- |
| 工具与基础模块单元测试 | 配置、文件边界、外部响应解析、并发额度、日志脱敏 | 临时目录、模拟 HTTP 等 |
| Agent 与 Web 单元测试 | 工具循环、预算、超时、会话隔离、任务取消、请求校验、SSE | 注入假的 LLM/MCP 或 Agent |
| MCP 集成测试 | 子进程启动、工具发现、会话复用、响应解析和关闭 | 真实本地 MCP 子进程，不依赖在线模型 |

评测用例位于 `evals/cases.json`：

```bash
python -m evals.evaluator
```

当前 evaluator 只加载并检查必填字段，不运行模型、不评估答案质量，也不生成性能评分。仓库当前未提供 CI 工作流、覆盖率门槛或自动化部署流水线，测试命令需由开发者或外部流水线执行。

## 部署边界与待完善项

- **单进程状态**：历史、会话锁和任务注册表均在进程内，重启后丢失。多个 worker 不共享任务、会话或工具额度，当前应按单 worker 使用。
- **资源回收**：已完成任务记录和会话锁没有 TTL 回收；事件队列也没有容量上限，长期运行需要补充清理和背压。
- **访问控制**：尚无身份认证、会话归属检查和入口请求限流，UUID 只用于标识。对外部署前需要补齐这些能力。
- **可靠性**：尚无持久化任务队列、复杂熔断退避和幂等重试机制，进程退出后不能恢复未完成任务。
- **运维集成**：当前以结构化日志为主，未提供专用健康检查、指标采集和分布式追踪接口。
- **交付保障**：真实模型和外部服务联调、负载容量验证需在目标环境单独执行；模拟测试通过不等于生产可用。
