import asyncio
import json
import time
from collections import Counter
from typing import Any, Optional

from config import Settings, get_settings
from models import AgentRunResult, StopReason, ToolCallRecord, ToolResult
from Prompt import sys_prompt, user_prompt


class Agent:
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None, *,
                 settings: Optional[Settings] = None, llm_client: Any = None,
                 mcp_manager: Any = None) -> None:
        self.settings = settings or get_settings()
        self.temp_memory: list[dict[str, Any]] = []
        if llm_client is None:
            from LLM import LLM_client
            llm_client = LLM_client(base_url=base_url, api_key=api_key, settings=self.settings)
        if mcp_manager is None:
            from MCP_server import MCPManager
            mcp_manager = MCPManager()
        self.llm_client = llm_client
        self.mcpmanager = mcp_manager

    def build_messages(self, question: str) -> list[dict[str, Any]]:
        messages = [{"role": "system", "content": sys_prompt}]
        messages.extend(self.temp_memory[-16:])
        messages.append({"role": "user", "content": user_prompt.format(question=question)})
        return messages

    @staticmethod
    def _assistant_message(response: Any) -> dict[str, Any]:
        return {"role": "assistant", "content": response.content, "tool_calls": [
            {"id": call.id, "type": "function", "function": {
                "name": call.function.name, "arguments": call.function.arguments}}
            for call in response.tool_calls
        ]}

    @staticmethod
    def _signature(tool_call: Any) -> str:
        return f"{tool_call.function.name}:{tool_call.function.arguments}"

    async def run(self, question: str, max_runtimes: int | None = None) -> AgentRunResult:
        started = time.perf_counter()
        max_iterations = max_runtimes or self.settings.max_agent_iterations
        messages = self.build_messages(question)
        records: list[ToolCallRecord] = []
        signatures: Counter[str] = Counter()
        iterations = model_calls = 0

        try:
            async with asyncio.timeout(self.settings.agent_timeout_seconds):
                async with self.mcpmanager.connect_to_mcp() as session:
                    tools = self.mcpmanager.mcp_to_llm(
                        await self.mcpmanager.get_mcp_tools(session)
                    )
                    while True:
                        try:
                            response = self.llm_client.think(messages=messages, tools=tools)
                            model_calls += 1
                        except Exception:
                            return self._result(started, None, StopReason.MODEL_ERROR,
                                                iterations, model_calls, records)

                        if not response.tool_calls:
                            answer = response.content or ""
                            self.temp_memory.extend([
                                {"role": "user", "content": question},
                                {"role": "assistant", "content": answer},
                            ])
                            return self._result(started, answer, StopReason.COMPLETED,
                                                iterations, model_calls, records)

                        if iterations >= max_iterations:
                            return self._result(started, "超出最大迭代次数，已终止任务",
                                                StopReason.MAX_ITERATIONS, iterations,
                                                model_calls, records)

                        iterations += 1
                        messages.append(self._assistant_message(response))
                        for call in response.tool_calls:
                            signatures[self._signature(call)] += 1
                            if signatures[self._signature(call)] >= 3:
                                return self._result(started, "检测到重复工具调用，已终止任务",
                                                    StopReason.REPEATED_TOOL_CALL, iterations,
                                                    model_calls, records)

                            tool_started = time.perf_counter()
                            result = await self.mcpmanager.parse_llm_response(session, call)
                            if not isinstance(result, ToolResult):
                                result = ToolResult.model_validate(result)
                            try:
                                arguments = json.loads(call.function.arguments)
                            except json.JSONDecodeError:
                                arguments = {}
                            records.append(ToolCallRecord(
                                name=call.function.name, arguments=arguments, result=result,
                                duration_ms=(time.perf_counter() - tool_started) * 1000,
                            ))
                            messages.append({"role": "tool", "tool_call_id": call.id,
                                             "content": result.model_dump_json()})
        except TimeoutError:
            return self._result(started, "任务执行超时", StopReason.TIMEOUT,
                                iterations, model_calls, records)
        except Exception:
            return self._result(started, "工具服务执行失败", StopReason.TOOL_ERROR,
                                iterations, model_calls, records)

    @staticmethod
    def _result(started: float, answer: str | None, reason: StopReason,
                iterations: int, model_calls: int,
                records: list[ToolCallRecord]) -> AgentRunResult:
        return AgentRunResult(
            answer=answer, stop_reason=reason, iterations=iterations,
            model_calls=model_calls, tool_calls=records,
            duration_ms=(time.perf_counter() - started) * 1000,
        )
