import os
from functools import lru_cache
from pathlib import Path
from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field


class Settings(BaseModel):
    #llm模型名
    model_name: str
    #baseurl
    llm_base_url: str
    #llm_api
    llm_api_key: str
    #goole_search_api
    search_api_key: str | None = None
    #agent最大可迭代次数，没传默认为10
    max_agent_iterations: int = Field(default=10, ge=1)
    #agent运行允许的最大运行时间
    agent_timeout_seconds: float = Field(default=120, gt=0)
    #tools调用允许的最大运行时间
    tool_timeout_seconds: float = Field(default=15, gt=0)
    #多余字段不报错
    model_config = ConfigDict(extra="ignore")

    @classmethod
    def from_env(cls, env_file: str | Path = ".env") -> "Settings":
        file_values = dotenv_values(env_file)

        def value(*names: str, default=None):
            for name in names:
                #优先在环境变量中查找对应配置
                if name in os.environ:
                    return os.environ[name]
                #环境变量中没有，则在env_file中查询
                if file_values.get(name) is not None:
                    return file_values[name]
            return default

        return cls(
            model_name=value("MODEL_NAME", "model_name"),
            llm_base_url=value("LLM_BASE_URL", "base_url"),
            llm_api_key=value("LLM_API_KEY", "api"),
            search_api_key=value("SEARCH_API_KEY", "search_api"),
            max_agent_iterations=value("MAX_AGENT_ITERATIONS", default=10),
            agent_timeout_seconds=value("AGENT_TIMEOUT_SECONDS", default=120),
            tool_timeout_seconds=value("TOOL_TIMEOUT_SECONDS", default=15),
        )


@lru_cache
#利用缓存读取数据
def get_settings() -> Settings:
    return Settings.from_env()
