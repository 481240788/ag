import asyncio
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4


@dataclass
class TaskRecord:
    session_id: UUID
    request_id: UUID
    queue: asyncio.Queue[dict[str, Any]] = field(default_factory=asyncio.Queue)
    task: asyncio.Task | None = None
    finished: bool = False


class TaskRegistry:
    def __init__(self) -> None:
        self._records: dict[UUID, TaskRecord] = {}
        self._lock = asyncio.Lock()

    async def create(self, session_id: UUID, request_id: UUID) -> tuple[UUID, TaskRecord]:
        task_id = uuid4()
        record = TaskRecord(session_id=session_id, request_id=request_id)
        async with self._lock:
            self._records[task_id] = record
        return task_id, record

    async def get(self, task_id: UUID) -> TaskRecord | None:
        async with self._lock:
            return self._records.get(task_id)

    async def cancel(self, task_id: UUID) -> bool:
        record = await self.get(task_id)
        if record is None or record.task is None or record.task.done():
            return False
        record.task.cancel()
        return True

    async def close(self) -> None:
        async with self._lock:
            tasks = [record.task for record in self._records.values() if record.task]
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
