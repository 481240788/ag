from abc import ABC, abstractmethod
from asyncio import Lock
from typing import Any


class ConversationStore(ABC):
    """对话历史存储接口"""

    @abstractmethod
    async def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        """
        获取历史信息
        """
        raise NotImplementedError

    @abstractmethod
    async def append_messages(
        self, session_id: str, messages: list[dict[str, Any]]
    ) -> None:
        """
        像历史信息中新增消息
        """
        raise NotImplementedError

    @abstractmethod
    async def clear(self, session_id: str) -> bool:
        """
        清除会话；存在并清除时返回True。
        """
        raise NotImplementedError

    @abstractmethod
    async def get_session_lock(self, session_id: str) -> Lock:
        """
        返回会话级锁，保证同一会话的Agent运行不会交错。
        """
        raise NotImplementedError
