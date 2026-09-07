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
        """
        将用户问题，历史聊天记录合并组装为一个规范的messages
        ipnut:
            question: 用户输入的具体问题
            history:  历史的model与用户对话消息
        output:
            标准的messages信息
        """
        #系统提示词组装消息
        messages = [{"role": "system", "content": sys_prompt}]
        #组装历史消息进入messages
        messages.extend(history)
        #用户提示词组装消息
        messages.append({"role": "user", "content": user_prompt.format(question=question)})
        return messages

    @staticmethod
    def _assistant_message(response: Any) -> dict[str, Any]:
        """
        接受llm返回的消息，解析其中的content以及工具调用toolcall
        input:
            response:llm回传的消息，包含：content以及tool_call的内容
        output:
            解析assistant的response后组装标准messages信息
        """
        return {"role": "assistant",
                "content": response.content,
                "tool_calls": [
                    {
                        "id": call.id, 
                        "type": "function", 
                        "function": {
                            "name": call.function.name, 
                            "arguments": call.function.arguments
                            }
                        }
                    for call in response.tool_calls
                ]
        }

    @staticmethod
    def _signature(tool_call: Any) -> str:
        """
        解析工具调用的信息为一个字符串形式，
        以便后续可以检查统计工具调用次数，防止重复调用
        """
        arguments = tool_call.function.arguments
        try:
            arguments = json.dumps(json.loads(arguments), sort_keys=True, ensure_ascii=False)
        except (ValueError, TypeError):
            pass
        return f"{tool_call.function.name}:{arguments}"

    async def run(
        self, question: str, session_id: str, max_runtimes: int | None = None,
        event_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> AgentRunResult:
        #去除session前后空格
        session_id = str(session_id).strip()
        #session_id不存在则抛出异常
        if not session_id:
            raise ValueError("session_id不能为空")
        #为当前的session_id获取一个session锁
        session_lock = await self.conversation_store.get_session_lock(session_id)
        async with session_lock:
            """
            以下代码均在当前session_id对应的session_lock保护下执行。
            如果当前session_id对应的锁已经被其他协程持有，
            那么其他使用相同session_id的协程执行到
            async with session_lock时，会在这里等待。
            直到当前协程执行完async with代码块并释放锁后，
            等待中的协程才能继续获取锁并执行。
            不同session_id对应不同的锁，因此可以并发执行。
            """
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
        #记录此次对话开始的时间
        started = time.perf_counter()
        #最大可循环次数
        max_iterations = max_runtimes or self.settings.max_agent_iterations
        #获取当前session_id的历史对话记录
        history = await self.conversation_store.get_messages(session_id)
        #将user的问题与之前的历史对话记录统计写为标准messages
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
                            #拿到llm的think返回值
                            response = await asyncio.wait_for(
                                self.llm_client.think(messages=messages, tools=tools),
                                timeout=self.settings.llm_timeout_seconds,
                            )
                            model_calls += 1
                            #更新token使用情况
                            token_usage.update(getattr(self.llm_client, "last_usage", {}))
                            #输出正常日志
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
                                                iterations, model_calls, records, dict(token_usage))
                        #如果llm不需要调用工具
                        if not response.tool_calls:
                            #拿到llm返回的文本内容
                            answer = response.content or ""
                            #保存一次对话
                            await self.conversation_store.append_messages(session_id, [
                                {"role": "user", "content": question},
                                {"role": "assistant", "content": answer},
                            ])
                            #此次对话完成，返回结果
                            return self._result(started, answer, StopReason.COMPLETED,
                                                iterations, model_calls, records, dict(token_usage))
                        #这里就是llm在调用tools的循环
                        if iterations >= max_iterations:
                            return self._result(started, "超出最大迭代次数，已终止任务",
                                                StopReason.MAX_ITERATIONS, iterations,
                                                model_calls, records, dict(token_usage))

                        iterations += 1
                        #将llm的返回content以及toolcall信息保存为一次messages
                        messages.append(self._assistant_message(response))
                        for call in response.tool_calls:
                            if len(records) >= self.settings.max_tool_calls:
                                return self._result(
                                    started, "已达到工具调用上限，请缩小查询范围后重试。",
                                    StopReason.TOOL_CALL_LIMIT, iterations, model_calls,
                                    records, dict(token_usage),
                                )
                            #循环调用工具
                            await self._emit(event_callback, {
                                "type": "status", "status": "tool_call",
                                "tool": call.function.name,
                            })
                            #将计数器signatures中对应的工具调用信息的次数+1，防止重复调用工具
                            signatures[self._signature(call)] += 1
                            if signatures[self._signature(call)] >= 3:
                                return self._result(started, "检测到重复工具调用，已终止任务",
                                                    StopReason.REPEATED_TOOL_CALL, iterations,
                                                    model_calls, records, dict(token_usage))
                            #记录工具调用起始时间
                            tool_started = time.perf_counter()
                            #等待mcp_serever调用工具并传回结果
                            result = await asyncio.wait_for(
                                self.mcpmanager.parse_llm_response(session, call),
                                timeout=self.settings.tool_timeout_seconds,
                            )
                            #将工具执行结果规范为ToolResult格式
                            if not isinstance(result, ToolResult):
                                result = ToolResult.model_validate(result)
                            try:
                                #将json字符串转换为python格式dict
                                arguments = json.loads(call.function.arguments)
                            except json.JSONDecodeError:
                                arguments = {}
                            #保存一次工具调用记录
                            records.append(ToolCallRecord(
                                name=call.function.name, arguments=arguments, result=result,
                                duration_ms=(time.perf_counter() - tool_started) * 1000,
                            ))
                            #记录一次工具执行日志
                            logger.info("tool_call_completed", extra={
                                "event": "tool_call_completed",
                                "duration_ms": round(records[-1].duration_ms, 2),
                                "tool_name": call.function.name,
                                "tool_ok": result.ok,
                                "error_code": result.error_code,
                                "retryable": result.retryable,
                            })
                            #将当前tool执行的结果传入messages
                            messages.append({"role": "tool", "tool_call_id": call.id,
                                             "content": result.model_dump_json()})
        except TimeoutError:
            return self._result(started, "任务执行超时", StopReason.TIMEOUT,
                                iterations, model_calls, records, dict(token_usage))
        except Exception:
            logger.exception("工具服务执行失败 session_id=%s", session_id)
            return self._result(started, "工具服务执行失败", StopReason.TOOL_ERROR,
                                iterations, model_calls, records, dict(token_usage))

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
        """
        #如果存在事件回调函数，则将event交给回调函数处理，并等待处理完成
        """
        if callback is not None:
            await callback(event)
