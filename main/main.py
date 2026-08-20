from Agent import Agent

async def main():
    agent = Agent()

    result = await agent.run("做一个python代码,返回1-100内的所有素数，调试好了写一个py文件出来")

    print(result.answer)
    print(f"终止原因: {result.stop_reason.value}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
