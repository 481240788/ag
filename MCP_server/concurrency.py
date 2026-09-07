"""Per-tool execution limits within one MCP server process."""

import asyncio
import inspect
from functools import wraps


class ToolConcurrencyLimiter:
    def __init__(self, limits: dict[str, int]):
        self.limits = dict(limits)
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        if any(type(limit) is not int or limit < 1 for limit in limits.values()):
            raise ValueError("工具并发上限必须为正整数")

    def wrap(self, function):
        name = function.__name__
        limit = self.limits.get(name, 1)

        @wraps(function)
        async def limited(*args, **kwargs):
            semaphore = self._semaphores.setdefault(name, asyncio.Semaphore(limit))
            async with semaphore:
                if inspect.iscoroutinefunction(function):
                    return await function(*args, **kwargs)
                # Retain the slot until synchronous work actually finishes, even on cancellation.
                task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
                try:
                    return await asyncio.shield(task)
                except asyncio.CancelledError:
                    await task
                    raise

        return limited
