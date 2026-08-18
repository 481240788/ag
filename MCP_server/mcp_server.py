from mcp.server.fastmcp import FastMCP
from LLMTools import search_information,weather_query,get_current_time,read_file_content,list_directory,write_new_file

mcp = FastMCP("Doraemon")

mcp.tool()(search_information)
mcp.tool()(weather_query)
mcp.tool()(get_current_time)
mcp.tool()(read_file_content)
mcp.tool()(list_directory)
mcp.tool()(write_new_file)



if __name__ == "__main__":
    mcp.run()