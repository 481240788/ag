from path_manager import PathManager
from contextlib import asynccontextmanager
from openai.types.chat import ChatCompletionMessageToolCall
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Tool
from typing import Any
from ErrorClass import ToolRunError
from models import ToolResult
import sys,json,os

class MCPManager:
    def __init__(self) -> None:
        #整个项目根目录的绝对路径
        pathmanager = PathManager()
        abs_path = pathmanager.abs_path

        #继承当前Python进程的环境变量
        env = os.environ.copy()

        #将项目根目录加入PYTHONPATH
        env["PYTHONPATH"] = (
            str(abs_path)
            + os.pathsep
            + env.get("PYTHONPATH", "")
        )
        #mcp服务文件的路径
        mcp_file_path = abs_path / "MCP_server" / "mcp_server.py"
        #mcp服务参数
        self.mcp_server_params = StdioServerParameters(
            command=sys.executable,
            args=[str(mcp_file_path)],
            env=env
        )

    @asynccontextmanager
    async def connect_to_mcp(self):
        async with stdio_client(self.mcp_server_params) as (read,write):
            async with ClientSession(read_stream=read,write_stream=write) as session:
                await session.initialize()
                yield session
    
    def mcp_to_llm(self,tool_list:list[Tool]) -> list[dict[str,Any]]:
        """
        将mcp返回得到的工具转换为llm可读的类型
        """
        llm_tool_list = []
        for tool in tool_list:
            current_tool = {
                "type":"function",
                "function":{
                    "name":tool.name,
                    "description":tool.description or '',
                    "parameters":tool.inputSchema
                }
            }
            llm_tool_list.append(current_tool)
        return llm_tool_list
            

    async def parse_llm_response(
            self,
            session:ClientSession,
            tool_call:ChatCompletionMessageToolCall
    ) -> ToolResult:
        """
        将llm返回的Tool_Callable解析为对应格式,传递给mcp来进行调用,并得到结果
        """
        function_name = tool_call.function.name
        try:
            function_arguments = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError as e:
            return ToolResult.failure("INVALID_ARGUMENT", f"工具参数解析失败: {e}")

        try:
            result = await session.call_tool(function_name, function_arguments)
        except Exception as e:
            return ToolResult.failure("TOOL_CALL_FAILED", f"工具调用失败: {e}", retryable=True)
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
    
    async def get_mcp_tools(self,session:ClientSession):
        """
        拿到mcp中的Toolslist
        """
        result = await session.list_tools()
        canuse_tool_list = result.tools
        return canuse_tool_list
    
