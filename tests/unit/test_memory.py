import asyncio

from memory import InMemoryConversationStore


def test_sessions_are_isolated_and_clear_is_scoped():
    async def scenario():
        store = InMemoryConversationStore()
        await store.append_messages("a", [{"role": "user", "content": "A"}])
        await store.append_messages("b", [{"role": "user", "content": "B"}])
        assert await store.clear("a") is True
        assert await store.get_messages("a") == []
        assert (await store.get_messages("b"))[0]["content"] == "B"
        assert await store.clear("a") is False

    asyncio.run(scenario())


def test_history_is_bounded_and_returned_as_copy():
    async def scenario():
        store = InMemoryConversationStore(max_messages=2)
        await store.append_messages("a", [
            {"role": "user", "content": "1"},
            {"role": "assistant", "content": "2"},
            {"role": "user", "content": "3"},
        ])
        history = await store.get_messages("a")
        assert [item["content"] for item in history] == ["2", "3"]
        history[0]["content"] = "changed"
        assert (await store.get_messages("a"))[0]["content"] == "2"

    asyncio.run(scenario())


def test_same_session_lock_serializes_tasks():
    async def scenario():
        store = InMemoryConversationStore()
        lock = await store.get_session_lock("a")
        entered = []

        async def worker(name):
            async with lock:
                entered.append(f"{name}-start")
                await asyncio.sleep(0)
                entered.append(f"{name}-end")

        await asyncio.gather(worker("one"), worker("two"))
        assert entered in (["one-start", "one-end", "two-start", "two-end"],
                           ["two-start", "two-end", "one-start", "one-end"])

    asyncio.run(scenario())


def test_history_is_trimmed_by_token_budget():
    async def scenario():
        store = InMemoryConversationStore(max_messages=100, max_tokens=20)
        await store.append_messages("a", [
            {"role": "user", "content": "a" * 40},
            {"role": "assistant", "content": "b" * 40},
            {"role": "user", "content": "latest"},
        ])
        history = await store.get_messages("a")
        assert len(history) < 3
        assert history[-1]["content"] == "latest"

    asyncio.run(scenario())
