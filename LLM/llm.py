from openai import OpenAI
from openai.types.chat import ChatCompletionMessage
from typing import Optional,Any
from dotenv import load_dotenv
from ErrorClass import LLMConfigMiss
import os
load_dotenv()

class LLM_client:
    def __init__(
            self,
            base_url:Optional[str]=None,
            api_key:Optional[str]=None
    ) -> None:
        #获取llm的相关配置
        llm_base_url = base_url or os.getenv("base_url",None)
        llm_api_key = api_key or os.getenv("api",None)
        #如果llm配置缺失
        if not all([llm_base_url,llm_api_key]):
            raise LLMConfigMiss("[LLM] llm配置缺失,请确保相关信息配置完整")
        
        self.llm_client = OpenAI(
            base_url=llm_base_url,
            api_key=llm_api_key
        )

    def think(
        self,
        messages:list[dict[str,Any]],
        tools:Optional[list[dict[str,Any]]]=None,
        model_name:Optional[str]=None
    ) -> ChatCompletionMessage:
        """
        llm接收messages,输出回复
        """
        #选择使用的model名
        llm_model_name = model_name or os.getenv("model_name",None)
        if not llm_model_name:
            raise LLMConfigMiss("[LLM] llm配置缺失,请确保相关信息配置完整")

        #拿到llm返回结果
        llm_response = self.llm_client.chat.completions.create(
            model=llm_model_name,
            messages=messages,
            tools=tools
        )
        return llm_response.choices[0].message
        