from uuid import uuid4

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from main.web_app import create_app
from models import AgentRunResult, StopReason


class FakeStore:
    async def clear(self, _):
        return True


class FakeAgent:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.conversation_store = FakeStore()

    async def run(self, *_args, **_kwargs):
        if self.error:
            raise self.error
        return self.result


def result(reason=StopReason.COMPLETED, answer="完成"):
    return AgentRunResult(answer=answer, stop_reason=reason, duration_ms=12.5)


def test_chat_success_has_request_and_session_ids():
    session_id = uuid4()
    with TestClient(create_app(FakeAgent(result()))) as client:
        response = client.post("/chat", json={"session_id": str(session_id), "message": "你好"})
    assert response.status_code == 200
    assert response.json()["session_id"] == str(session_id)
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_chat_timeout_uses_504():
    with TestClient(create_app(FakeAgent(result(StopReason.TIMEOUT, "超时")))) as client:
        response = client.post("/chat", json={"session_id": str(uuid4()), "message": "慢任务"})
    assert response.status_code == 504
    assert response.json()["success"] is False


def test_chat_validation_rejects_empty_message():
    with TestClient(create_app(FakeAgent(result()))) as client:
        response = client.post("/chat", json={"session_id": str(uuid4()), "message": ""})
    assert response.status_code == 422
    assert "X-Request-ID" in response.headers
    assert response.json()["error_code"] == "INVALID_ARGUMENT"


def test_unknown_error_is_sanitized():
    app = create_app(FakeAgent(error=RuntimeError("secret-value")))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/chat", json={"session_id": str(uuid4()), "message": "你好"})
    assert response.status_code == 500
    assert response.json()["message"] == "服务内部错误"
    assert "secret-value" not in response.text
