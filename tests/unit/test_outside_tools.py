import asyncio
from types import SimpleNamespace

import pytest

from LLMTools import outside_tools as tools
from models import ToolResult


def test_geocode_propagates_upstream_failure(monkeypatch):
    async def failed(*args, **kwargs):
        return ToolResult.failure("AMAP_ERROR", "invalid key")
    monkeypatch.setattr(tools, "_request_amap", failed)
    result = asyncio.run(tools.geocode("test", "成都"))
    assert result.error_code == "AMAP_ERROR"


def test_route_handles_failed_geocode(monkeypatch):
    monkeypatch.setattr(tools, "get_settings", lambda: SimpleNamespace(gaode_map_api="test"))
    async def failed(*args, **kwargs):
        return ToolResult.failure("LOCATION_NOT_FOUND", "找不到地点")
    monkeypatch.setattr(tools, "geocode", failed)
    result = asyncio.run(tools.route_planning("起点", "终点"))
    assert result.error_code == "ORIGIN_GEOCODE_ERROR"


@pytest.mark.parametrize("name", ["_driving_route", "_walking_route", "_transit_route"])
def test_route_helpers_propagate_failure(monkeypatch, name):
    async def failed(*args, **kwargs):
        return ToolResult.failure("AMAP_ERROR", "invalid key")
    monkeypatch.setattr(tools, "_request_amap", failed)
    args = ["test", "起点", "终点", "104,30", "105,31"]
    if name == "_transit_route":
        args.extend(["成都", "成都"])
    result = asyncio.run(getattr(tools, name)(*args))
    assert result.error_code == "AMAP_ERROR"
