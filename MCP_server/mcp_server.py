from mcp.server.fastmcp import FastMCP
from datetime import datetime


mcp = FastMCP("Doraemon")

@mcp.tool()
def get_current_time() -> datetime:
    """
    获取当前的时间（例如：2026-08-14 14:49:52.692439）
    return:
        当前的时间
    """
    today_date = datetime.today()
    return today_date

@mcp.tool()
def call_me():
    """
    给我打电话
    """
    print("hahahaha")

if __name__ == "__main__":
    mcp.run()