import asyncio,json,logging,time
from collections import Counter
from typing import Any, Awaitable, Callable, Optional
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
        self, question: str, session_id: str, max_runtimes: int | None = None,
        event_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> AgentRunResult:
        session_id = str(session_id).strip()
        if not session_id:
            raise ValueError("session_id 不能为空")
        session_lock = await self.conversation_store.get_session_lock(session_id)
        async with session_lock:
            await self._emit(event_callback, {"type": "status", "status": "thinking"})
            result = await self._run_locked(question, session_id, max_runtimes, event_callback)
            logger.info("agent_run_finished", extra={
                "event": "agent_run_finished",
                "duration_ms": round(result.duration_ms, 2),
                "stop_reason": result.stop_reason.value,
                "token_total": result.token_usage.get("total_tokens", 0),
            })
            await self._emit(event_callback, {
                "type": "result", "status": result.stop_reason.value,
                "data": result.model_dump(mode="json"),
            })
            return result

    async def _run_locked(
        self, question: str, session_id: str, max_runtimes: int | None,
        event_callback: Callable[[dict[str, Any]], Awaitable[None]] | None,
    ) -> AgentRunResult:
        started = time.perf_counter()
        max_iterations = max_runtimes or self.settings.max_agent_iterations
        history = await self.conversation_store.get_messages(session_id)
        messages = self.build_messages(question, history)
        records: list[ToolCallRecord] = []
        signatures: Counter[str] = Counter()
        iterations = model_calls = 0
        token_usage: Counter[str] = Counter()

        try:
            async with asyncio.timeout(self.settings.agent_timeout_seconds):
                async with self.mcpmanager.connect_to_mcp() as session:
                    tools = self.mcpmanager.mcp_to_llm(
                        await self.mcpmanager.get_mcp_tools(session)
                    )
                    while True:
                        try:
                            response = await asyncio.wait_for(
                                self.llm_client.think(messages=messages, tools=tools),
                                timeout=self.settings.llm_timeout_seconds,
                            )
                            model_calls += 1
                            token_usage.update(getattr(self.llm_client, "last_usage", {}))
                            logger.info("model_call_completed", extra={
                                "event": "model_call_completed",
                                "duration_ms": round(getattr(self.llm_client, "last_duration_ms", 0), 2),
                                "token_total": token_usage.get("total_tokens", 0),
                            })
                        except TimeoutError:
                            raise
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
                                                iterations, model_calls, records, dict(token_usage))

                        if iterations >= max_iterations:
                            return self._result(started, "超出最大迭代次数，已终止任务",
                                                StopReason.MAX_ITERATIONS, iterations,
                                                model_calls, records)

                        iterations += 1
                        messages.append(self._assistant_message(response))
                        for call in response.tool_calls:
                            await self._emit(event_callback, {
                                "type": "status", "status": "tool_call",
                                "tool": call.function.name,
                            })
                            signatures[self._signature(call)] += 1
                            if signatures[self._signature(call)] >= 3:
                                return self._result(started, "检测到重复工具调用，已终止任务",
                                                    StopReason.REPEATED_TOOL_CALL, iterations,
                                                    model_calls, records)

                            tool_started = time.perf_counter()
                            result = await asyncio.wait_for(
                                self.mcpmanager.parse_llm_response(session, call),
                                timeout=self.settings.tool_timeout_seconds,
                            )
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
                            logger.info("tool_call_completed", extra={
                                "event": "tool_call_completed",
                                "duration_ms": round(records[-1].duration_ms, 2),
                                "tool_name": call.function.name,
                            })
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
                records: list[ToolCallRecord],
                token_usage: dict[str, int] | None = None) -> AgentRunResult:
        """
        记录Agent执行的结果
        """
        return AgentRunResult(
            answer=answer, stop_reason=reason, iterations=iterations,
            model_calls=model_calls, tool_calls=records,
            duration_ms=(time.perf_counter() - started) * 1000,
            token_usage=token_usage or {},
        )

    @staticmethod
    async def _emit(
        callback: Callable[[dict[str, Any]], Awaitable[None]] | None,
        event: dict[str, Any],
    ) -> None:
        if callback is not None:
            await callback(event)
