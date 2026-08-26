import json,logging,re
from contextvars import ContextVar, Token
from datetime import datetime, timezone

#使用ContextVar来管理
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
session_id_var: ContextVar[str] = ContextVar("session_id", default="-")

#匹配敏感信息，在输出日志时对敏感信息脱敏
SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|authorization|token|secret|password)([\"']?\s*[:=]\s*[\"']?)([^\s,}\"']+)"
)


def redact(value: object) -> str:
    """
    对敏感信息脱敏
    """
    return SECRET_PATTERN.sub(r"\1\2***", str(value))


class JsonFormatter(logging.Formatter):
    """
    将日志整理成固定的json格式
    """
    def format(self, record: logging.LogRecord) -> str:
        """
        采集python输出的LogRecord类型的日志数据，转换为固定格式
        """
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
            "request_id": request_id_var.get(),
            "session_id": session_id_var.get(),
        }
        for key in ("event", "duration_ms", "tool_name", "stop_reason", "token_total"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """
    初始化程序的日志系统
    """
    #设置日志默认打印到控制台
    handler = logging.StreamHandler()
    #设置日志的Formatter为自定义的Formatter
    handler.setFormatter(JsonFormatter())
    #拿到一个日志根对象
    root = logging.getLogger()
    #清除之前设置的Formatter
    root.handlers.clear()
    #将handler应用于root
    root.addHandler(handler)
    #设置日志等级
    root.setLevel(level.upper())


def bind_context(request_id: str, session_id: str = "-") -> tuple[Token, Token]:
    """
    给当前任务绑定request_id以及session_id
    """
    return request_id_var.set(request_id), session_id_var.set(session_id)


def reset_context(tokens: tuple[Token, Token]) -> None:
    """
    恢复起始的上下文
    """
    request_id_var.reset(tokens[0])
    session_id_var.reset(tokens[1])
