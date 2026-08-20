from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    ok: bool
    data: Any | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False

    @classmethod
    def success(cls, data: Any = None) -> "ToolResult":
        return cls(ok=True, data=data)

    @classmethod
    def failure(
        cls, error_code: str, error_message: str, *, retryable: bool = False
    ) -> "ToolResult":
        return cls(
            ok=False,
            error_code=error_code,
            error_message=error_message,
            retryable=retryable,
        )


class StopReason(str, Enum):
    """
    记录Agent结束原因
    """
    #正常结束
    COMPLETED = "completed"
    #超过最大迭代次数
    MAX_ITERATIONS = "max_iterations"
    #工具重复调用
    REPEATED_TOOL_CALL = "repeated_tool_call"
    #运行超时
    TIMEOUT = "timeout"
    #工具执行错误
    TOOL_ERROR = "tool_error"
    #llm相关错误
    MODEL_ERROR = "model_error"


class ToolCallRecord(BaseModel):
    """
    工具调用情况记录
    """
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: ToolResult
    duration_ms: float


class AgentRunResult(BaseModel):
    """
    Agent执行结果
    """
    answer: str | None = None
    stop_reason: StopReason
    iterations: int = 0
    model_calls: int = 0
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    duration_ms: float = 0

