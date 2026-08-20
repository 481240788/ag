from typing import Optional
from LLM import LLM_client
from ErrorClass import LLMConfigMiss
from Prompt import user_prompt,sys_prompt
from MCP_server import MCPManager

class Agent:
    def __init__(
            self,
            base_url:Optional[str]=None,
            api_key:Optional[str]=None
    ) -> None:
        
        #定义一个短暂的记忆模块
        self.temp_memory = []

        try:
            self.llm_client = LLM_client(
                base_url=base_url,
                api_key=api_key
            )
        except LLMConfigMiss as e:
            raise e
        
        self.mcpmanager = MCPManager()


    async def run(self,question:str,max_runtimes=10):
        """
        执行(主程序)
        """
        
        #当前循环次数
        current_run_times = 0
        #超出循环次数状态码
        is_error = False
        #组装格式化提示词
        llm_user_prompt = user_prompt.format(question=question)

        #组装messages
        messages = [
            {
                "role":"system","content":sys_prompt
            }]
        
        messages.extend(self.temp_memory[-16:])

        messages.append(
            {
                "role":"user","content":llm_user_prompt
            }
        )

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
            # print(response)
            # print("="*50)
            while(response.tool_calls):
                current_run_times += 1
                print(f"第{current_run_times}次迭代")
                if current_run_times > max_runtimes:
                    is_error = True
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
                    print(
                        f"\n[Tool Call] "
                        f"{tool_call.function.name}"
                    )

                    print(
                        f"[Arguments] "
                        f"{tool_call.function.arguments}"
                    )
                    result = await self.mcpmanager.parse_llm_response(
                        session,
                        tool_call
                    )
                    print(f"[Tool Result] {result}")
                    print("-" * 50)

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

                # print(response)
                # print("="*50)
            if is_error:
                return '超出最大迭代次数，已终止任务'
            
            # #短暂保存历史对话内容
            self.temp_memory.append(
                {
                    "role":"user","content":question
                }
            )
            self.temp_memory.append(
                {
                    "role":"assistant","content":response.content
                }
            )
            return response.content

                
    
