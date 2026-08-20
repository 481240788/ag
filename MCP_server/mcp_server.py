from mcp.server.fastmcp import FastMCP
from LLMTools.outside_tools import search_information, weather_query
from LLMTools.sys_tools import get_current_time, read_file_content, list_directory, write_new_file
from LLMTools.code_tools import execute_python

mcp = FastMCP("Doraemon")

#outside_tools
mcp.tool()(search_information)
mcp.tool()(weather_query)

#sys_tools
mcp.tool()(get_current_time)
mcp.tool()(read_file_content)
mcp.tool()(list_directory)
mcp.tool()(write_new_file)

#code_tools
mcp.tool()(execute_python)


if __name__ == "__main__":
    mcp.run()
