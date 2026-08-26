# Doraemon Agent

基于 MCP（Model Context Protocol）协议的智能 Agent 项目。通过 MCP 协议统一管理工具调用，结合大语言模型实现自动化的任务分析与执行。

## 项目架构

```
├── Agent/              # Agent 核心模块
│   └── agent.py        # 包装 LLM 为 Agent，实现工具调用循环
├── LLM/                # 大语言模型客户端
│   └── llm.py          # 基于 OpenAI 兼容接口的 LLM 客户端
├── LLMTools/           # 工具集
│   ├── outside_tools.py    # 外部工具（Google 搜索、天气查询）
│   ├── sys_tools.py        # 系统工具（文件读写、目录列表、时间获取、文件创建）
│   └── code_tools.py       # 代码工具（Python 代码执行与调试）
├── MCP_server/         # MCP 服务模块
│   ├── mcp_server.py       # 将工具注册到 MCP 服务端
│   └── mcp_manager.py      # MCP 客户端管理（会话管理、格式转换、工具调用）
├── Prompt/             # 提示词模块
│   └── prompt.py       # 系统提示词与用户提示词模板
├── ErrorClass/         # 自定义异常
│   └── errorclass.py   # LLMConfigMiss、ToolRunError、SearchError、ApiError
├── path_manager/       # 路径管理
│   └── pathmanager.py  # 项目根路径管理工具
├── main/               # 入口模块
│   ├── main.py         # 命令行运行入口
│   ├── web_app.py      # FastAPI Web 应用入口
│   └── static/         # 前端静态文件
├── examples/           # Agent 创建文件的指定工作目录
├── .env                # 环境变量配置
└── .env.example        # 环境变量示例
```

## 各模块说明

### Agent

**agent.py** — Agent 核心类，负责：

- 初始化 LLM 客户端与 MCP 管理器
- 实现 ReAct 循环：调用 LLM → 解析工具调用 → 执行工具 → 将结果反馈给 LLM
- 通过 `session_id` 隔离短期对话记忆，并按上下文 token 预算裁剪
- 支持最大迭代次数限制，防止无限循环

### LLM

**llm.py** — LLM 客户端，基于 OpenAI 兼容接口：

- 支持自定义 `base_url` 和 `api_key`，兼容多种大模型服务
- `think()` 方法：接收 messages 和可选的 tools 列表，返回 LLM 回复

### LLMTools

工具集，分为三类：

- **outside_tools.py** — 外部 API 工具
  - `search_information`：通过 Google 搜索获取在线信息（基于 SerpApi）
  - `weather_query`：查询指定城市的实时天气
- **sys_tools.py** — 系统工具
  - `get_current_time`：获取当前系统时间
  - `read_file_content`：读取 `examples` 工作目录内的文件内容（限制 5MB）
  - `list_directory`：列出 `examples` 工作目录中的文件和子目录
  - `write_new_file`：在 examples 目录中创建新文件（安全限制：不可覆盖、不可写入系统盘）
- **code_tools.py** — 代码工具
  - `execute_local_python_unsafe`：仅供可信本地开发使用的宿主机代码执行工具，默认关闭

### MCP_server

**mcp_server.py** — MCP 服务端，将所有工具注册到 MCP 框架中（项目代号：Doraemon）

**mcp_manager.py** — MCP 管理器，负责：

- 启动 MCP 服务并建立 stdio 通信会话
- 获取 MCP 中的可用工具列表
- 将 MCP 工具格式转换为 OpenAI 兼容的 function calling 格式
- 将 LLM 返回的 tool_call 解析为 MCP 可调用格式，并返回执行结果

### Prompt

**prompt.py** — 提示词定义：

- `sys_prompt`：系统提示词，定义 Agent 的行为准则（工具调用规则、文件安全规则、回答规则等）
- `user_prompt`：用户提示词模板，接收用户问题

### ErrorClass

**errorclass.py** — 自定义异常类型：

- `LLMConfigMiss`：LLM 配置缺失
- `ToolRunError`：工具执行失败
- `SearchError`：搜索/查询出错
- `ApiError`：API 未配置

### path_manager

**pathmanager.py** — 路径管理工具，提供项目根目录的绝对路径

## 环境配置

在项目根目录创建 `.env` 文件，参考 `.env.example` 填写：

```env
# 模型相关
MODEL_NAME="qwen3.7-max"
LLM_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
LLM_API_KEY=你的API密钥

# 工具相关
# Google 搜索 API（SerpApi）
SEARCH_API_KEY=你的SerpApi密钥

# 运行边界
LLM_TIMEOUT_SECONDS=60
TOOL_TIMEOUT_SECONDS=15
AGENT_TIMEOUT_SECONDS=120
ENABLE_LOCAL_PYTHON_EXECUTION=false
APP_ENVIRONMENT=development
```

**API 获取地址：**

- 通义千问 API：[阿里云百炼平台](https://bailian.console.aliyun.com/)
- Google 搜索 API：[SerpApi](https://serpapi.com/users/sign_in)

## 安装与运行

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 运行测试

核心单元测试不访问真实 LLM、搜索或天气服务：

```bash
python -m pytest -q
```

评测基线位于 `evals/cases.json`，可以先验证用例格式：

```bash
python -m evals.evaluator
```

### 2. 命令行模式运行

```bash
python -m main.main
```

### 3. Web 模式运行

```bash
python -m main.web_app
```

启动后访问 `http://127.0.0.1:8000` 即可使用 Web 聊天界面。

## 目前可实现功能

1. **在线信息搜索** — 通过 Google 搜索获取实时信息
2. **天气查询** — 查询指定城市的当日天气
3. **文件内容读取** — 读取项目 `examples` 目录内的文件内容
4. **目录文件列表** — 查询指定文件夹下的所有文件
5. **获取当前时间** — 获取本机当前时间
6. **创建文件** — 在 examples 目录中创建新文件（有安全限制）
7. **Python 代码执行（默认关闭）** — 仅在非生产环境显式开启后可用，不属于安全沙盒

## 工作流程

```
用户提问 → Agent 组装 Prompt → LLM 分析并决策
                                    ↓
                              需要调用工具？
                              ↓是          ↓否
                    MCP 执行工具       直接回复用户
                         ↓
                  工具结果反馈给 LLM
                         ↓
                  LLM 继续分析（循环）
                         ↓
                   最终回复用户
```

## 运行结果协议

Agent 现在返回结构化的 `AgentRunResult`，其中包含最终回答、终止原因、迭代次数、模型调用次数、工具调用轨迹和运行耗时。工具统一返回 `ToolResult`，以明确区分成功结果、错误码、错误信息和是否可重试。

当前终止原因包括：正常完成、最大迭代次数、重复工具调用、超时、工具错误和模型错误。

## 当前限制

- Web 版本已完成进程内多用户会话隔离；服务重启后历史仍会丢失，生产环境可通过 `ConversationStore` 接入 Redis。
- LLM、天气和工具调用链路均为异步实现；同步 SerpApi SDK 通过工作线程隔离。
- 文件工具默认只允许访问 `examples`，并拒绝路径穿越、敏感文件、符号链接绕过和覆盖写入。
- Python 执行仍然不是安全沙盒，因此默认不注册；即使显式开启，生产环境也会强制禁用。
- Web API 为每个请求生成 `request_id`，并使用 4xx/5xx 状态码区分校验、超时、模型和工具错误。

## Web API

`POST /chat` 请求需要 UUID 格式的 `session_id` 和非空 `message`。响应包含 `request_id`、`session_id`、`stop_reason` 和运行耗时；所有响应还会设置 `X-Request-ID` 响应头。

`DELETE /sessions/{session_id}` 可清除指定会话的进程内历史。
