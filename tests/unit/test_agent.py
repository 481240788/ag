import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from Agent import Agent
from config import Settings
from models import StopReason, ToolResult


def response(content=None, calls=None):
    return SimpleNamespace(content=content, tool_calls=calls or [])


def tool_call(call_id="1", name="get_current_time", arguments="{}"):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


class FakeLLM:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.received_messages = []

    async def think(self, messages, **_):
        self.received_messages.append(messages)
        return next(self.responses)


class FakeMCP:
    @asynccontextmanager
    async def connect_to_mcp(self):
        yield object()

    async def get_mcp_tools(self, _):
        return []

    def mcp_to_llm(self, _):
        return []

    async def parse_llm_response(self, _, __):
        return ToolResult.success({"current_time": "now"})


def make_agent(responses, conversation_store=None):
    settings = Settings(model_name="test", llm_base_url="https://example.invalid", llm_api_key="key")
    llm = FakeLLM(responses)
    return Agent(
        settings=settings, llm_client=llm, mcp_manager=FakeMCP(),
        conversation_store=conversation_store,
    )


def test_agent_direct_answer_and_memory():
    agent = make_agent([response("完成")])
    result = asyncio.run(agent.run("问题", session_id="session-a"))
    assert result.stop_reason == StopReason.COMPLETED
    assert result.answer == "完成"
    history = asyncio.run(agent.conversation_store.get_messages("session-a"))
    assert len(history) == 2


def test_signature_normalizes_json():
    assert Agent._signature(tool_call(arguments='{"a":1,"b":2}')) == Agent._signature(
        tool_call(arguments='{"b": 2, "a": 1}'))


def test_tool_budget_limits_large_batch():
    agent = make_agent([response(calls=[tool_call(str(i), arguments='{"n":%d}' % i) for i in range(5)])])
    agent.settings.max_tool_calls = 2
    agent.llm_client.last_usage = {"total_tokens": 23}
    result = asyncio.run(agent.run("批量查询", session_id="budget"))
    assert result.stop_reason == StopReason.TOOL_CALL_LIMIT
    assert len(result.tool_calls) == 2
    assert result.token_usage["total_tokens"] == 23


def test_timeout_retains_completed_usage():
    class LaterTimeout(FakeLLM):
        last_usage = {"total_tokens": 42}

        async def think(self, messages, **kwargs):
            if self.received_messages:
                raise TimeoutError()
            return await super().think(messages, **kwargs)

    agent = make_agent([])
    agent.llm_client = LaterTimeout([response(calls=[tool_call()])])
    result = asyncio.run(agent.run("超时", session_id="usage"))
    assert result.stop_reason == StopReason.TIMEOUT
    assert result.token_usage["total_tokens"] == 42
    assert len(result.tool_calls) == 1


def test_agent_calls_tool_then_answers():
    agent = make_agent([response(calls=[tool_call()]), response("现在")])
    result = asyncio.run(agent.run("几点", session_id="session-a"))
    assert result.stop_reason == StopReason.COMPLETED
    assert result.iterations == 1
    assert result.tool_calls[0].name == "get_current_time"


def test_agent_stops_repeated_tool_call():
    call = tool_call()
    agent = make_agent([response(calls=[call]), response(calls=[call]), response(calls=[call])])
    result = asyncio.run(agent.run("循环", session_id="session-a"))
    assert result.stop_reason == StopReason.REPEATED_TOOL_CALL


def test_agent_isolates_session_history():
    agent = make_agent([response("A1"), response("B1"), response("A2")])

    async def scenario():
        await agent.run("A 的秘密", session_id="a")
        await agent.run("B 的问题", session_id="b")
        await agent.run("A 的追问", session_id="a")

    asyncio.run(scenario())
    third_messages = agent.llm_client.received_messages[2]
    contents = [message.get("content") for message in third_messages]
    assert "A 的秘密" in contents
    assert "A1" in contents
    assert "B 的问题" not in contents
    assert "B1" not in contents


def test_agent_failure_does_not_save_history():
    class BrokenLLM:
        async def think(self, **_):
            raise RuntimeError("model unavailable")

    agent = make_agent([])
    agent.llm_client = BrokenLLM()
    result = asyncio.run(agent.run("不会保存", session_id="failed"))
    history = asyncio.run(agent.conversation_store.get_messages("failed"))
    assert result.stop_reason == StopReason.MODEL_ERROR
    assert result.answer
    assert history == []


def test_agent_model_timeout_has_explicit_stop_reason():
    class SlowLLM:
        async def think(self, **_):
            await asyncio.sleep(0.05)

    settings = Settings(
        model_name="test", llm_base_url="https://example.invalid", llm_api_key="key",
        llm_timeout_seconds=0.01, agent_timeout_seconds=1,
    )
    agent = Agent(settings=settings, llm_client=SlowLLM(), mcp_manager=FakeMCP())
    result = asyncio.run(agent.run("慢请求", session_id="timeout"))
    assert result.stop_reason == StopReason.TIMEOUT


def test_agent_tool_timeout_has_explicit_stop_reason():
    class SlowMCP(FakeMCP):
        async def parse_llm_response(self, _, __):
            await asyncio.sleep(0.05)
            return ToolResult.success()

    settings = Settings(
        model_name="test", llm_base_url="https://example.invalid", llm_api_key="key",
        tool_timeout_seconds=0.01, agent_timeout_seconds=1,
    )
    agent = Agent(
        settings=settings,
        llm_client=FakeLLM([response(calls=[tool_call()])]),
        mcp_manager=SlowMCP(),
    )
    result = asyncio.run(agent.run("慢工具", session_id="timeout"))
    assert result.stop_reason == StopReason.TIMEOUT
