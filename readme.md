# Doraemon Agent

一个基于 MCP（Model Context Protocol）和 OpenAI 兼容模型接口构建的异步工具调用 Agent。

项目实现了完整的模型工具调用循环、多会话隔离、MCP 常驻连接、结构化运行结果、安全文件工具、SSE 状态推送、任务取消和简洁的 Web 对话界面。

## 功能特性

- OpenAI 兼容的异步 LLM 客户端，可配置模型名称和服务地址。
- 基于 MCP stdio 的统一工具注册与调用。
- MCP 服务随 Web 应用启动和关闭，工具列表自动缓存。
- MCP 调用异常时自动重建连接并重试一次。
- 使用 `session_id` 隔离不同用户的对话历史。
- 按上下文 token 预算裁剪历史消息。
- 模型调用、工具调用和整个 Agent 任务均有超时限制。
- 检测重复工具调用和最大迭代次数，避免无限循环。
- 工具和 Agent 均返回结构化结果。
- 文件操作限制在 `examples` 工作目录内。
- 拒绝路径穿越、敏感文件、符号链接绕过和覆盖写入。
- 本机 Python 执行工具默认关闭，生产环境强制禁用。
- Web 支持 SSE 状态推送和任务取消。
- JSON 结构化日志自动关联请求与会话，并对常见密钥字段脱敏。

## 系统架构

```text
┌───────────────┐
│    Web UI     │
│ HTML/CSS/JS   │
└───────┬───────┘
        │ HTTP / SSE
┌───────▼───────┐
│    FastAPI    │
│ Session/Task  │
└───────┬───────┘
        │
┌───────▼───────┐      ┌──────────────────┐
│ Agent Runtime │─────▶│ Async LLM Client │
│ ReAct Loop    │      │ OpenAI Compatible│
└───────┬───────┘      └──────────────────┘
        │
┌───────▼───────┐      ┌──────────────────┐
│  MCP Manager  │─────▶│ MCP Tool Server  │
│ Persistent    │stdio │ Restricted Tools │
└───────────────┘      └──────────────────┘
```

执行流程：

```text
用户问题
  → 加载当前 session 历史
  → 调用 LLM
  → LLM 判断是否需要工具
  → MCP 执行工具
  → 工具结果反馈给 LLM
  → 继续迭代或返回最终答案
  → 保存成功对话历史
```

## 项目结构

```text
all_agent/
├── Agent/                  # Agent 执行循环
├── LLM/                    # 异步 LLM 客户端
├── LLMTools/               # 外部、文件和代码工具
├── MCP_server/             # MCP Server 与生命周期管理
├── Prompt/                 # 系统提示词和用户模板
├── ErrorClass/             # 应用异常类型
├── config/                 # 集中配置模型
├── memory/                 # 会话存储抽象及内存实现
├── models/                 # AgentResult、ToolResult 等数据模型
├── observability/          # JSON 日志、上下文与脱敏
├── security/               # 文件路径安全策略
├── main/
│   ├── main.py             # 命令行示例入口
│   ├── web_app.py          # FastAPI 应用
│   ├── task_registry.py    # 异步任务注册与取消
│   └── static/
│       ├── index.html
│       ├── style.css
│       └── app.js
├── examples/               # 文件工具唯一默认工作目录
├── evals/                  # 基础评测用例定义
├── tests/                  # 单元测试和 MCP 集成测试
├── .env.example
└── requirements.txt
```

## 内置工具

### 外部工具

| 工具 | 说明 | 依赖 |
|---|---|---|
| `search_information` | 使用 Google 搜索获取在线信息 | SerpApi Key |
| `weather_query` | 查询指定城市的实时天气 | `wttr.in` |

### 文件和系统工具

| 工具 | 说明 |
|---|---|
| `get_current_time` | 获取服务器当前时间 |
| `read_file_content` | 读取 `examples` 内 UTF-8 文件，最大 5MB |
| `list_directory` | 查看 `examples` 内的目录内容 |
| `write_new_file` | 在 `examples` 内创建文件，不允许覆盖 |

### 本机代码执行

`execute_local_python_unsafe` 会直接在宿主机执行 Python，不是真正的安全沙盒，因此：

- 默认不注册到 MCP。
- 只有显式设置 `ENABLE_LOCAL_PYTHON_EXECUTION=true` 才会启用。
- 当 `APP_ENVIRONMENT=production` 时始终禁用。
- 即使在开发环境启用，也只应执行可信代码。
- 工具有运行超时、输出长度限制和临时文件清理，但这些措施不等同于系统隔离。

## 环境要求

- Python 3.11 或更高版本。
- 一个支持 OpenAI Chat Completions 和 Tool Calling 的模型服务。
- 可选：SerpApi Key，用于在线搜索。

## 安装

```bash
git clone <your-repository-url>
cd all_agent

python -m venv .venv
```

Windows：

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Linux/macOS：

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

## 配置

复制环境变量示例：

```powershell
Copy-Item .env.example .env
```

Linux/macOS：

```bash
cp .env.example .env
```

编辑 `.env`：

```env
# LLM 必填配置
MODEL_NAME="qwen3.7-max"
LLM_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
LLM_API_KEY=your-api-key

# 搜索工具可选配置
SEARCH_API_KEY=your-serpapi-key

# Agent 运行边界
MAX_AGENT_ITERATIONS=10
AGENT_TIMEOUT_SECONDS=120
LLM_TIMEOUT_SECONDS=60
TOOL_TIMEOUT_SECONDS=15
HISTORY_MAX_TOKENS=4000

# 本机代码执行，默认关闭
ENABLE_LOCAL_PYTHON_EXECUTION=false
PYTHON_MAX_OUTPUT_CHARS=20000
APP_ENVIRONMENT=development

# 日志
LOG_LEVEL=INFO
```

项目兼容早期版本的小写配置名称，但推荐统一使用以上大写名称。

## 运行

### Web 模式

```bash
python -m main.web_app
```

浏览器访问：

```text
http://127.0.0.1:8000
```

应用启动时会同时启动 MCP 子进程并缓存工具列表；关闭 Web 服务时会自动释放 MCP 连接。

### 命令行示例

```bash
python -m main.main
```

当前命令行入口是固定问题的演示代码，主要用于快速验证 Agent 工作流程。

## Web API

### 直接等待完整结果

```http
POST /chat
Content-Type: application/json
```

请求：

```json
{
  "session_id": "b592a1dd-47ba-43b8-9660-71ec8c141765",
  "message": "现在几点？"
}
```

响应：

```json
{
  "success": true,
  "answer": "现在是……",
  "stop_reason": "completed",
  "request_id": "8bb6dc7d-b605-4d30-9370-660049031cd0",
  "session_id": "b592a1dd-47ba-43b8-9660-71ec8c141765",
  "duration_ms": 912.4
}
```

### 创建异步任务

```http
POST /tasks
```

请求体与 `/chat` 相同，成功后返回 `202 Accepted`：

```json
{
  "task_id": "f55441e8-f3dd-40ec-bd21-3c91721ef340",
  "request_id": "8bb6dc7d-b605-4d30-9370-660049031cd0",
  "session_id": "b592a1dd-47ba-43b8-9660-71ec8c141765"
}
```

### 接收任务状态

```http
GET /tasks/{task_id}/events
Accept: text/event-stream
```

SSE 只返回安全的运行状态，不暴露模型内部推理：

```text
data: {"type":"status","status":"thinking"}

data: {"type":"status","status":"tool_call","tool":"get_current_time"}

data: {"type":"result","status":"completed","data":{...}}
```

### 取消任务

```http
DELETE /tasks/{task_id}
```

### 清除会话

```http
DELETE /sessions/{session_id}
```

## 运行结果

Agent 返回 `AgentRunResult`：

| 字段 | 说明 |
|---|---|
| `answer` | 最终回答 |
| `stop_reason` | 终止原因 |
| `iterations` | 工具调用迭代轮数 |
| `model_calls` | 模型调用次数 |
| `tool_calls` | 工具名称、参数、结果和耗时记录 |
| `duration_ms` | 总运行时间 |
| `token_usage` | 模型返回的 token 使用量 |

终止原因包括：

- `completed`
- `max_iterations`
- `repeated_tool_call`
- `timeout`
- `tool_error`
- `model_error`

工具统一返回 `ToolResult`，包含：

- `ok`
- `data`
- `error_code`
- `error_message`
- `retryable`

## 会话与并发

- 每次请求必须携带 UUID 格式的 `session_id`。
- 不同会话拥有独立的历史消息。
- 同一个会话的任务会串行执行，避免上下文交错。
- 不同会话可以并发运行。
- 历史消息存储在进程内，服务重启后会丢失。
- `ConversationStore` 已抽象，可在后续替换为 Redis 或数据库实现。

## MCP 生命周期

- Web 应用启动时建立 MCP stdio 会话。
- 工具列表只在连接建立时获取并缓存。
- Agent 请求复用已有 MCP 会话。
- MCP 调用异常时自动重连并重试一次。
- Web 应用退出时关闭会话和子进程。
- 如果脱离 Web 应用单独使用 Agent，MCP Manager 仍支持临时连接模式。

## 日志与安全

日志为 JSON 格式，主要字段包括：

```json
{
  "timestamp": "2026-08-26T06:07:50.227666+00:00",
  "level": "INFO",
  "logger": "Agent.agent",
  "message": "agent_run_finished",
  "request_id": "...",
  "session_id": "...",
  "event": "agent_run_finished",
  "duration_ms": 912.4,
  "stop_reason": "completed",
  "token_total": 328
}
```

日志不会主动记录完整 Prompt、工具参数或工具结果，并会脱敏常见凭据字段。

文件工具的默认安全边界：

- 只能访问 `examples`。
- 禁止 `../` 路径穿越。
- 禁止读取 `.env*`、SSH Key、credentials 等敏感文件。
- 禁止通过符号链接绕过允许目录。
- 禁止覆盖已有文件。
- 单文件读取上限为 5MB。

## HTTP 状态码

| 状态码 | 场景 |
|---|---|
| `200` | 任务正常完成 |
| `202` | 异步任务创建成功 |
| `409` | 达到迭代上限或检测到重复工具调用 |
| `422` | 请求参数不正确 |
| `502` | 模型或工具服务失败 |
| `504` | Agent 执行超时 |
| `500` | 未处理的服务内部错误 |

所有 HTTP 响应都会携带 `X-Request-ID` 响应头，未知异常不会向客户端返回内部堆栈。

## 测试

运行完整测试：

```bash
python -m pytest -q
```

当前测试覆盖：

- 配置加载与兼容字段。
- Agent 直接回答、工具调用、重复调用和超时。
- 会话隔离、历史裁剪和并发锁。
- 文件权限、路径穿越与安全写入。
- 本机 Python 执行、异常和超时。
- Web 参数校验、错误脱敏和 SSE。
- 结构化日志脱敏。
- MCP 启动、会话复用、工具列表和关闭。

基础评测用例位于 `evals/cases.json`。当前 `evals/evaluator.py` 用于校验用例结构：

```bash
python -m evals.evaluator
```

## 当前限制

- 会话历史和任务状态均保存在进程内，不支持多实例共享。
- SSE 只推送运行阶段和最终结果，不流式输出模型生成的每个 token。
- 尚未实现用户身份认证和请求限流，不应直接暴露到公网。
- SerpApi SDK 是同步接口，目前通过工作线程避免阻塞事件循环。
- 本机 Python 执行工具不是真正的安全沙盒。
- MCP 自动重连是单次恢复策略，不包含复杂熔断和退避机制。

## License

当前仓库尚未提供 License 文件。如计划公开分发，请根据使用目标补充合适的开源许可证。
