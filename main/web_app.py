import logging
import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from Agent import Agent
from ErrorClass import AppError
from models import StopReason
from observability import bind_context, configure_logging, reset_context
from path_manager import PathManager
from main.task_registry import TaskRegistry

logger = logging.getLogger(__name__)
path_man = PathManager()


class ChatRequest(BaseModel):
    session_id: UUID
    message: str = Field(min_length=1, max_length=10_000)


class ChatResponse(BaseModel):
    success: bool
    answer: str
    stop_reason: StopReason
    request_id: UUID
    session_id: UUID
    duration_ms: float


class ErrorResponse(BaseModel):
    success: bool = False
    error_code: str
    message: str
    request_id: UUID


STATUS_BY_STOP_REASON = {
    StopReason.COMPLETED: 200,
    StopReason.MAX_ITERATIONS: 409,
    StopReason.REPEATED_TOOL_CALL: 409,
    StopReason.TIMEOUT: 504,
    StopReason.TOOL_ERROR: 502,
    StopReason.MODEL_ERROR: 502,
}


def create_app(agent_instance: Any | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        if application.state.agent is None:
            application.state.agent = Agent()
        configure_logging(
            getattr(getattr(application.state.agent, "settings", None), "log_level", "INFO")
        )
        manager = getattr(application.state.agent, "mcpmanager", None)
        if manager is not None and hasattr(manager, "start"):
            await manager.start()
        try:
            yield
        finally:
            await application.state.tasks.close()
            if manager is not None and hasattr(manager, "stop"):
                await manager.stop()

    application = FastAPI(title="Chat", lifespan=lifespan)
    application.state.agent = agent_instance
    application.state.tasks = TaskRegistry()
    static_path = str(path_man.abs_path / "main" / "static")
    application.mount("/static", StaticFiles(directory=static_path), name="static")

    @application.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = uuid4()
        tokens = bind_context(str(request.state.request_id))
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = str(request.state.request_id)
            return response
        finally:
            reset_context(tokens)

    @application.exception_handler(AppError)
    async def handle_app_error(request: Request, error: AppError):
        payload = ErrorResponse(
            error_code=error.error_code,
            message=error.public_message,
            request_id=request.state.request_id,
        )
        return JSONResponse(status_code=error.status_code, content=payload.model_dump(mode="json"))

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, _error: RequestValidationError):
        payload = ErrorResponse(
            error_code="INVALID_ARGUMENT",
            message="请求参数不正确",
            request_id=request.state.request_id,
        )
        return JSONResponse(status_code=422, content=payload.model_dump(mode="json"))

    @application.exception_handler(Exception)
    async def handle_unknown_error(request: Request, error: Exception):
        logger.exception("未处理异常 request_id=%s", request.state.request_id, exc_info=error)
        payload = ErrorResponse(
            error_code="INTERNAL_ERROR",
            message="服务内部错误",
            request_id=request.state.request_id,
        )
        return JSONResponse(status_code=500, content=payload.model_dump(mode="json"))

    @application.get("/")
    async def index():
        return FileResponse(str(path_man.abs_path / "main" / "static" / "index.html"))

    @application.post("/chat", response_model=ChatResponse)
    async def chat(request: Request, payload: ChatRequest):
        tokens = bind_context(str(request.state.request_id), str(payload.session_id))
        try:
            result = await request.app.state.agent.run(
                payload.message, session_id=str(payload.session_id)
            )
        finally:
            reset_context(tokens)
        succeeded = result.stop_reason == StopReason.COMPLETED
        response = ChatResponse(
            success=succeeded,
            answer=result.answer or "任务未能生成有效回复，请稍后重试。",
            stop_reason=result.stop_reason,
            request_id=request.state.request_id,
            session_id=payload.session_id,
            duration_ms=result.duration_ms,
        )
        return JSONResponse(
            status_code=STATUS_BY_STOP_REASON[result.stop_reason],
            content=response.model_dump(mode="json"),
        )

    @application.delete("/sessions/{session_id}")
    async def clear_session(request: Request, session_id: UUID):
        cleared = await request.app.state.agent.conversation_store.clear(str(session_id))
        return {
            "success": True,
            "session_id": str(session_id),
            "cleared": cleared,
            "request_id": str(request.state.request_id),
        }

    @application.post("/tasks", status_code=202)
    async def create_task(request: Request, payload: ChatRequest):
        task_id, record = await request.app.state.tasks.create(
            payload.session_id, request.state.request_id
        )

        async def publish(event: dict[str, Any]) -> None:
            await record.queue.put(event)

        async def runner() -> None:
            tokens = bind_context(str(record.request_id), str(record.session_id))
            try:
                await request.app.state.agent.run(
                    payload.message,
                    session_id=str(payload.session_id),
                    event_callback=publish,
                )
            except asyncio.CancelledError:
                await publish({"type": "cancelled", "status": "cancelled"})
                raise
            finally:
                record.finished = True
                reset_context(tokens)

        record.task = asyncio.create_task(runner(), name=f"agent-{task_id}")
        return {
            "task_id": str(task_id),
            "request_id": str(record.request_id),
            "session_id": str(record.session_id),
        }

    @application.get("/tasks/{task_id}/events")
    async def task_events(request: Request, task_id: UUID):
        record = await request.app.state.tasks.get(task_id)
        if record is None:
            return JSONResponse(status_code=404, content={
                "success": False, "error_code": "NOT_FOUND",
                "message": "任务不存在", "request_id": str(request.state.request_id),
            })

        async def stream():
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(record.queue.get(), timeout=15)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    if event.get("type") in {"result", "cancelled"}:
                        break
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    if record.finished and record.queue.empty():
                        break

        return StreamingResponse(stream(), media_type="text/event-stream")

    @application.delete("/tasks/{task_id}")
    async def cancel_task(request: Request, task_id: UUID):
        cancelled = await request.app.state.tasks.cancel(task_id)
        if not cancelled:
            return JSONResponse(status_code=404, content={
                "success": False, "error_code": "NOT_FOUND",
                "message": "任务不存在或已结束", "request_id": str(request.state.request_id),
            })
        return {"success": True, "task_id": str(task_id), "status": "cancelling"}

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main.web_app:app", host="127.0.0.1", port=8000, reload=True)
