from openai import OpenAI
from openai.types.chat import ChatCompletionMessage
from typing import Optional,Any
from config import Settings, get_settings
from ErrorClass import LLMConfigMiss

class LLM_client:
    def __init__(
            self,
            base_url:Optional[str]=None,
            api_key:Optional[str]=None,
            settings:Optional[Settings]=None,
    ) -> None:
        try:
            self.settings = settings or get_settings()
        except Exception as e:
            raise LLMConfigMiss(f"[LLM] 配置校验失败: {e}") from e
        llm_base_url = base_url or self.settings.llm_base_url
        llm_api_key = api_key or self.settings.llm_api_key
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
        llm_model_name = model_name or self.settings.model_name
        if not llm_model_name:
            raise LLMConfigMiss("[LLM] llm配置缺失,请确保相关信息配置完整")

        #拿到llm返回结果
        llm_response = self.llm_client.chat.completions.create(
            model=llm_model_name,
            messages=messages,
            tools=tools
        )
        return llm_response.choices[0].message
        
