import asyncio

import pytest

pytest.importorskip("mcp")
from MCP_server import MCPManager


def test_mcp_starts_and_unsafe_python_is_disabled_by_default():
    async def scenario():
        manager = MCPManager()
        await manager.start()
        try:
            async with manager.connect_to_mcp() as first:
                names = [tool.name for tool in await manager.get_mcp_tools(first)]
            async with manager.connect_to_mcp() as second:
                assert first is second
            assert manager.startup_duration_ms > 0
            assert "get_current_time" in names
            assert "query_train_tickets" in names
            assert "read_file_content" in names
            assert "execute_local_python_unsafe" not in names
        finally:
            await manager.stop()

    asyncio.run(scenario())
