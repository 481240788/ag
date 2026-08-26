import asyncio
from uuid import uuid4

from main.task_registry import TaskRegistry


def test_registry_cancels_running_task():
    async def scenario():
        registry = TaskRegistry()
        task_id, record = await registry.create(uuid4(), uuid4())
        record.task = asyncio.create_task(asyncio.sleep(30))
        assert await registry.cancel(task_id)
        await asyncio.gather(record.task, return_exceptions=True)
        assert record.task.cancelled()

    asyncio.run(scenario())
