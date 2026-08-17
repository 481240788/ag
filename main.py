from typing import Optional
from LLM import LLM_client
from ErrorClass import LLMConfigMiss
from Prompt import sys_prompt
from MCP_server import MCPManager

class Agent:
    def __init__(
            self,
            base_url:Optional[str]=None,
            api_key:Optional[str]=None
    ) -> None:
        
        try:
            self.llm_client = LLM_client(
                base_url=base_url,
                api_key=api_key
            )
        except LLMConfigMiss as e:
            raise e
        
        self.mcpmanager = MCPManager()


    async def run(self,question:str,max_runtimes=3):
        """
        执行(主程序)
        """
        #当前循环次数
        current_run_times = 0
        #组装格式化提示词
        llm_sys_prompt = sys_prompt.format(question=question)
        #组装messages
        messages = [
            {
                "role":"user","content":llm_sys_prompt
            }
        ]

        async with self.mcpmanager.connect_to_mcp() as session:
            #当前可用的工具列表
            canuse_tool_list = await self.mcpmanager.get_mcp_tools(session)

            #格式转换(拿到符合openai格式的llm需要的工具格式)
            llm_tools = self.mcpmanager.mcp_to_llm(canuse_tool_list)

            #调用llm
            response = self.llm_client.think(
                messages=messages,
                tools=llm_tools
            )

            while(response.tool_calls):
                current_run_times += 1

                if current_run_times > max_runtimes:
                    break
                
                #保存每一次的assistant信息
                messages.append(
                    {
                        "role":"assistant",
                        "content":response.content,
                        "tool_calls":[
                            {
                                "id":tool_call.id,
                                "type":"function",
                                "function":{
                                    "name":tool_call.function.name,
                                    "arguments":tool_call.function.arguments
                                }
                            }
                            for tool_call in response.tool_calls
                        ]
                    }
                )

                #根据llm返回结果，调用工具获取结果
                for tool_call in response.tool_calls:
                    result = await self.mcpmanager.parse_llm_response(
                        session,
                        tool_call
                    )

                    #工具结果传入messages
                    messages.append(
                        {
                            "role":"tool",
                            "tool_call_id":tool_call.id,
                            "content":result
                        }
                    )

                response = self.llm_client.think(
                    messages=messages,
                    tools=llm_tools
                )
            
            return response.content

                
    
async def main():
    agent = Agent()

    result = await agent.run("hello，今天是几号？")

    print(result)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())