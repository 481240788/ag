class LLMConfigMiss(Exception):
    """
    llm相关配置缺失
    """
    pass

class ToolRunError(Exception):
    """
    工具执行失败
    """
    pass

class SearchError(Exception):
    """
    查询出错
    """
    pass

class ApiError(Exception):
    """
    Api未填写
    """
    pass