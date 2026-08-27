import asyncio
import json
from copy import deepcopy
from typing import Any
from .base import ConversationStore


class InMemoryConversationStore(ConversationStore):
    """
    对话记忆功能(多用户并行)
    """
    def __init__(self, max_messages: int = 100, max_tokens: int = 4_000) -> None:
        if max_messages < 1:
            raise ValueError("max_messages 必须大于 0")
        if max_tokens < 1:
            raise ValueError("max_tokens 必须大于 0")
        self.max_messages = max_messages
        self.max_tokens = max_tokens
        self._messages: dict[str, list[dict[str, Any]]] = {}
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._state_lock = asyncio.Lock()

    @staticmethod
    def _normalize_session_id(session_id: str) -> str:
        """
        去除session_id前后空格
        """
        normalized = str(session_id).strip()
        if not normalized:
            raise ValueError("session_id 不能为空")
        return normalized

    async def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        """
        获取某一session_id对应的会话记录
        """
        session_id = self._normalize_session_id(session_id)
        async with self._state_lock:
            """
            使用deepcopy复制一份数据，防止修改内部数据
            """
            return deepcopy(self._messages.get(session_id, []))

    async def append_messages(
        self, session_id: str, messages: list[dict[str, Any]]
    ) -> None:
        """
        给某一session追加新消息
        """
        session_id = self._normalize_session_id(session_id)
        async with self._state_lock:
            history = self._messages.setdefault(session_id, [])
            #将messages中的信息加入history
            history.extend(deepcopy(messages))
            history = history[-self.max_messages :]
            while len(history) > 1 and self._estimate_tokens(history) > self.max_tokens:
                #根据token限制删除旧消息
                history.pop(0)
            self._messages[session_id] = history

    @staticmethod
    def _estimate_tokens(messages: list[dict[str, Any]]) -> int:
        """
        粗略估计消息占用多少token
        """
        text = json.dumps(messages, ensure_ascii=False, separators=(",", ":"))
        ascii_count = sum(character.isascii() for character in text)
        non_ascii_count = len(text) - ascii_count
        return non_ascii_count + (ascii_count + 3) // 4

    async def clear(self, session_id: str) -> bool:
        """
        清除某一session的全部历史记录
        """
        session_id = self._normalize_session_id(session_id)
        session_lock = await self.get_session_lock(session_id)
        async with session_lock:
            async with self._state_lock:
                return self._messages.pop(session_id, None) is not None

    async def get_session_lock(self, session_id: str) -> asyncio.Lock:
        """
        获取session_id对应的lock
        """
        session_id = self._normalize_session_id(session_id)
        async with self._state_lock:
            return self._session_locks.setdefault(session_id, asyncio.Lock())
