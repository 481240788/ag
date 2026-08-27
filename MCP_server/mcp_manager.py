import asyncio,json,logging,os,sys,time
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Tool
from openai.types.chat import ChatCompletionMessageToolCall
from models import ToolResult
from path_manager import PathManager

logger = logging.getLogger(__name__)


class MCPManager:
    def __init__(self) -> None:
        abs_path = PathManager().abs_path
        env = os.environ.copy()
        env["PYTHONPATH"] = str(abs_path) + os.pathsep + env.get("PYTHONPATH", "")
        self.mcp_server_params = StdioServerParameters(
            command=sys.executable,
            args=[str(abs_path / "MCP_server" / "mcp_server.py")],
            env=env,
        )
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._tools: list[Tool] | None = None
        self._lifecycle_lock = asyncio.Lock()
        self.startup_duration_ms = 0.0

    async def start(self) -> None:
        async with self._lifecycle_lock:
            if self._session is not None:
                return
            started = time.perf_counter()
            stack = AsyncExitStack()
            try:
                read, write = await stack.enter_async_context(stdio_client(self.mcp_server_params))
                session = await stack.enter_async_context(
                    ClientSession(read_stream=read, write_stream=write)
                )
                await session.initialize()
                tools = (await session.list_tools()).tools
            except Exception:
                await stack.aclose()
                raise
            self._stack = stack
            self._session = session
            self._tools = tools
            self.startup_duration_ms = (time.perf_counter() - started) * 1000
            logger.info("mcp_started", extra={
                "event": "mcp_started", "duration_ms": round(self.startup_duration_ms, 2)
            })

    async def stop(self) -> None:
        async with self._lifecycle_lock:
            stack, self._stack = self._stack, None
            self._session = None
            self._tools = None
            if stack is not None:
                await stack.aclose()
                logger.info("mcp_stopped", extra={"event": "mcp_stopped"})

    async def restart(self) -> None:
        await self.stop()
        await self.start()

    @asynccontextmanager
    async def connect_to_mcp(self):
        if self._session is not None:
            yield self._session
            return
        async with stdio_client(self.mcp_server_params) as (read, write):
            async with ClientSession(read_stream=read, write_stream=write) as session:
                await session.initialize()
                yield session

    def mcp_to_llm(self, tool_list: list[Tool]) -> list[dict[str, Any]]:
        """
        将mcp输出的可用工具list转换为llm传入参数的格式
        """
        return [{
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema,
            },
        } for tool in tool_list]

    async def parse_llm_response(
        self, session: ClientSession, tool_call: ChatCompletionMessageToolCall
    ) -> ToolResult:
        """
        将llm返回的工具调用信息解析后传递给mcp进行工具调用，返回结果
        """
        try:
            arguments = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError as error:
            return ToolResult.failure("INVALID_ARGUMENT", f"工具参数解析失败: {error}")
        try:
            result = await session.call_tool(tool_call.function.name, arguments)
        except Exception as error:
            if session is self._session:
                logger.warning("mcp_reconnecting", extra={"event": "mcp_reconnect"})
                try:
                    await self.restart()
                    result = await self._session.call_tool(tool_call.function.name, arguments)
                except Exception as retry_error:
                    return ToolResult.failure(
                        "TOOL_CALL_FAILED", f"工具调用失败: {retry_error}", retryable=True
                    )
            else:
                return ToolResult.failure(
                    "TOOL_CALL_FAILED", f"工具调用失败: {error}", retryable=True
                )
        if result.isError:
            return ToolResult.failure("EXECUTION_FAILED", self._content_text(result.content))
        text = self._content_text(result.content)
        try:
            return ToolResult.model_validate(json.loads(text))
        except (json.JSONDecodeError, ValueError):
            return ToolResult.success(text)

    @staticmethod
    def _content_text(content: list[Any]) -> str:
        return "\n".join(getattr(item, "text", str(item)) for item in content)

    async def get_mcp_tools(self, session: ClientSession) -> list[Tool]:
        """
        得到可用工具list
        """
        if session is self._session and self._tools is not None:
            return self._tools
        return (await session.list_tools()).tools
