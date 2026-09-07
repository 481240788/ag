from mcp.server.fastmcp import FastMCP
from LLMTools.outside_tools import search_information, weather_query_gaode,route_planning
from LLMTools.sys_tools import get_current_time, read_file_content, list_directory, write_new_file
from LLMTools.code_tools import execute_local_python_unsafe
from config import get_settings
from LLMTools.train_tools import query_train_tickets
from MCP_server.concurrency import ToolConcurrencyLimiter

mcp = FastMCP("Doraemon")
settings = get_settings()
limiter = ToolConcurrencyLimiter(settings.tool_concurrency_limits)


def register_tool(function):
    mcp.tool()(limiter.wrap(function))

#outside_tools
register_tool(search_information)
register_tool(weather_query_gaode)
register_tool(route_planning)
register_tool(query_train_tickets)

#sys_tools
register_tool(get_current_time)
register_tool(read_file_content)
register_tool(list_directory)
register_tool(write_new_file)

# 本机代码执行不是沙盒，仅允许在非生产环境中显式开启。
if settings.enable_local_python_execution and settings.app_environment.lower() != "production":
    register_tool(execute_local_python_unsafe)


if __name__ == "__main__":
    mcp.run()
