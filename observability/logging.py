import json,logging,re
from contextvars import ContextVar, Token
from datetime import datetime, timezone

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
    def format(self, record: logging.LogRecord) -> str:
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
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())


def bind_context(request_id: str, session_id: str = "-") -> tuple[Token, Token]:
    return request_id_var.set(request_id), session_id_var.set(session_id)


def reset_context(tokens: tuple[Token, Token]) -> None:
    request_id_var.reset(tokens[0])
    session_id_var.reset(tokens[1])
