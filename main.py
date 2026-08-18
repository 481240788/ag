from Agent import Agent

async def main():
    agent = Agent()

    result = await agent.run("成都今天的天气咋样啊，帮我做一个旅游计划放进我的电脑里面，存放的位置放在当前的目录下。根据今天的日期和天气一下合适的景点啊")

    print(result)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())