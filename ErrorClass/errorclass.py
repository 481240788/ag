class AppError(Exception):
    error_code = "INTERNAL_ERROR"
    status_code = 500
    public_message = "服务内部错误"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.public_message)


class LLMConfigMiss(AppError):
    error_code = "CONFIGURATION_ERROR"
    public_message = "模型服务配置错误"


class ToolRunError(AppError):
    error_code = "TOOL_ERROR"
    status_code = 502
    public_message = "工具服务执行失败"


class SearchError(AppError):
    error_code = "EXTERNAL_SERVICE_ERROR"
    status_code = 502
    public_message = "外部服务暂时不可用"


class ApiError(AppError):
    error_code = "CONFIGURATION_ERROR"
    public_message = "外部服务配置错误"


class PermissionDeniedError(AppError):
    error_code = "PERMISSION_DENIED"
    status_code = 403
    public_message = "没有执行该操作的权限"


class AgentTimeoutError(AppError):
    error_code = "AGENT_TIMEOUT"
    status_code = 504
    public_message = "任务执行超时"
