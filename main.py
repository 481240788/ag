from Agent import Agent

async def main():
    agent = Agent()

    result = await agent.run("北京今天的天气咋样啊，帮我做一个旅游计划的makedown文档放进我的电脑里面。根据今天的日期和天气找一下合适的景点啊")

    print(result)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())