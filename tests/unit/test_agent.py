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

    def think(self, **_):
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


def make_agent(responses):
    settings = Settings(model_name="test", llm_base_url="https://example.invalid", llm_api_key="key")
    return Agent(settings=settings, llm_client=FakeLLM(responses), mcp_manager=FakeMCP())


def test_agent_direct_answer_and_memory():
    agent = make_agent([response("完成")])
    result = asyncio.run(agent.run("问题"))
    assert result.stop_reason == StopReason.COMPLETED
    assert result.answer == "完成"
    assert len(agent.temp_memory) == 2


def test_agent_calls_tool_then_answers():
    agent = make_agent([response(calls=[tool_call()]), response("现在")])
    result = asyncio.run(agent.run("几点"))
    assert result.stop_reason == StopReason.COMPLETED
    assert result.iterations == 1
    assert result.tool_calls[0].name == "get_current_time"


def test_agent_stops_repeated_tool_call():
    call = tool_call()
    agent = make_agent([response(calls=[call]), response(calls=[call]), response(calls=[call])])
    result = asyncio.run(agent.run("循环"))
    assert result.stop_reason == StopReason.REPEATED_TOOL_CALL
