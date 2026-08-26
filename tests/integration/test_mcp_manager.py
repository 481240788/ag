import asyncio

import pytest

pytest.importorskip("mcp")
from MCP_server import MCPManager


def test_mcp_starts_and_unsafe_python_is_disabled_by_default():
    async def scenario():
        manager = MCPManager()
        async with manager.connect_to_mcp() as session:
            names = [tool.name for tool in await manager.get_mcp_tools(session)]
            assert "get_current_time" in names
            assert "read_file_content" in names
            assert "execute_local_python_unsafe" not in names

    asyncio.run(scenario())
