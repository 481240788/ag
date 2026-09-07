import asyncio
import inspect

import pytest
from pydantic import ValidationError

from config import Settings
from MCP_server.concurrency import ToolConcurrencyLimiter


def test_limit_and_independent_tools():
    async def scenario():
        active = peak = 0
        entered = asyncio.Event()
        release = asyncio.Event()

        async def slow(value: int):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            if active == 2:
                entered.set()
            try:
                await release.wait()
                return value
            finally:
                active -= 1

        async def other():
            return "independent"

        limiter = ToolConcurrencyLimiter({"slow": 2, "other": 1})
        wrapped = limiter.wrap(slow)
        assert inspect.signature(wrapped) == inspect.signature(slow)
        tasks = [asyncio.create_task(wrapped(i)) for i in range(6)]
        await asyncio.wait_for(entered.wait(), 1)
        assert await limiter.wrap(other)() == "independent"
        release.set()
        assert await asyncio.gather(*tasks) == list(range(6))
        assert peak == 2

    asyncio.run(scenario())


def test_cancellation_and_exception_release_slots():
    async def scenario():
        entered = asyncio.Event()

        async def work(mode):
            if mode == "wait":
                entered.set()
                await asyncio.Event().wait()
            if mode == "error":
                raise ValueError("expected")
            return "ok"

        wrapped = ToolConcurrencyLimiter({"work": 1}).wrap(work)
        running = asyncio.create_task(wrapped("wait"))
        await entered.wait()
        queued = asyncio.create_task(wrapped("ok"))
        await asyncio.sleep(0)
        queued.cancel()
        with pytest.raises(asyncio.CancelledError):
            await queued
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
        with pytest.raises(ValueError):
            await wrapped("error")
        assert await asyncio.wait_for(wrapped("ok"), 1) == "ok"

    asyncio.run(scenario())


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_invalid_limits(limit):
    with pytest.raises(ValidationError):
        Settings(model_name="test", llm_base_url="test", llm_api_key="test",
                 tool_concurrency_limits={"tool": limit})


def test_env_overrides_merge_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_NAME", "test")
    monkeypatch.setenv("LLM_BASE_URL", "test")
    monkeypatch.setenv("LLM_API_KEY", "test")
    monkeypatch.setenv("TOOL_CONCURRENCY_LIMITS", '{"route_planning":4}')
    settings = Settings.from_env(tmp_path / "missing.env")
    assert settings.tool_concurrency_limits["route_planning"] == 4
    assert settings.tool_concurrency_limits["query_train_tickets"] == 1
