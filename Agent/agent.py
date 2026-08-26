import asyncio,json,logging,time
from collections import Counter
from typing import Any, Optional
from config import Settings, get_settings
from memory import ConversationStore, InMemoryConversationStore
from models import AgentRunResult, StopReason, ToolCallRecord, ToolResult
from Prompt import sys_prompt, user_prompt

logger = logging.getLogger(__name__)


class Agent:
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None, *,
                 settings: Optional[Settings] = None, llm_client: Any = None,
                 mcp_manager: Any = None,
                 conversation_store: ConversationStore | None = None) -> None:
        self.settings = settings or get_settings()
        self.conversation_store = conversation_store or InMemoryConversationStore(
            max_tokens=self.settings.history_max_tokens
        )
        if llm_client is None:
            from LLM import LLM_client
            llm_client = LLM_client(base_url=base_url, api_key=api_key, settings=self.settings)
        if mcp_manager is None:
            from MCP_server import MCPManager
            mcp_manager = MCPManager()
        self.llm_client = llm_client
        self.mcpmanager = mcp_manager

    def build_messages(
        self, question: str, history: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        messages = [{"role": "system", "content": sys_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_prompt.format(question=question)})
        return messages

    @staticmethod
    def _assistant_message(response: Any) -> dict[str, Any]:
        """
        llm回复消息重新组装
        """
        return {"role": "assistant", "content": response.content, "tool_calls": [
            {"id": call.id, "type": "function", "function": {
                "name": call.function.name, "arguments": call.function.arguments}}
            for call in response.tool_calls
        ]}

    @staticmethod
    def _signature(tool_call: Any) -> str:
        """
        组装工具调用相关信息
        """
        return f"{tool_call.function.name}:{tool_call.function.arguments}"

    async def run(
        self, question: str, session_id: str, max_runtimes: int | None = None
    ) -> AgentRunResult:
        session_id = str(session_id).strip()
        if not session_id:
            raise ValueError("session_id 不能为空")
        session_lock = await self.conversation_store.get_session_lock(session_id)
        async with session_lock:
            return await self._run_locked(question, session_id, max_runtimes)

    async def _run_locked(
        self, question: str, session_id: str, max_runtimes: int | None
    ) -> AgentRunResult:
        started = time.perf_counter()
        max_iterations = max_runtimes or self.settings.max_agent_iterations
        history = await self.conversation_store.get_messages(session_id)
        messages = self.build_messages(question, history)
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
                            logger.exception("模型调用失败 session_id=%s", session_id)
                            return self._result(started, "模型调用失败，请检查模型配置或稍后重试。", StopReason.MODEL_ERROR,
                                                iterations, model_calls, records)

                        if not response.tool_calls:
                            answer = response.content or ""
                            #保存对话
                            await self.conversation_store.append_messages(session_id, [
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
                            #保存工具调用记录
                            records.append(ToolCallRecord(
                                name=call.function.name, arguments=arguments, result=result,
                                duration_ms=(time.perf_counter() - tool_started) * 1000,
                            ))
                            #将ToolResult对象结果转换为字符串
                            messages.append({"role": "tool", "tool_call_id": call.id,
                                             "content": result.model_dump_json()})
        except TimeoutError:
            return self._result(started, "任务执行超时", StopReason.TIMEOUT,
                                iterations, model_calls, records)
        except Exception:
            logger.exception("工具服务执行失败 session_id=%s", session_id)
            return self._result(started, "工具服务执行失败", StopReason.TOOL_ERROR,
                                iterations, model_calls, records)

    @staticmethod
    def _result(started: float, answer: str | None, reason: StopReason,
                iterations: int, model_calls: int,
                records: list[ToolCallRecord]) -> AgentRunResult:
        """
        记录Agent执行的结果
        """
        return AgentRunResult(
            answer=answer, stop_reason=reason, iterations=iterations,
            model_calls=model_calls, tool_calls=records,
            duration_ms=(time.perf_counter() - started) * 1000,
        )
