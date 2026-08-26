from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from uuid import UUID
from path_manager import PathManager
from Agent import Agent

app = FastAPI(title="MCP Agent Chat")
path_man = PathManager()
# 静态文件
static_path = str(path_man.abs_path / 'main' / 'static')
app.mount("/static", StaticFiles(directory=static_path), name="static")

class ChatRequest(BaseModel):
    session_id: UUID
    message: str = Field(min_length=1, max_length=10_000)


# 创建一个全局 Agent
agent = Agent()


@app.get("/")
async def index():
    index_path = path_man.abs_path / "main" / "static" / "index.html"
    return FileResponse(str(index_path))


@app.post("/chat")
async def chat(request: ChatRequest):
    try:
        result = await agent.run(request.message, session_id=str(request.session_id))

        return {
            "success": True,
            "answer": result.answer,
            "stop_reason": result.stop_reason.value,
            "session_id": str(request.session_id),
        }
    except Exception as e:
        return {
            "success": False,
            "answer": f"执行失败：{str(e)}"
        }


@app.delete("/sessions/{session_id}")
async def clear_session(session_id: UUID):
    cleared = await agent.conversation_store.clear(str(session_id))
    return {
        "success": True,
        "session_id": str(session_id),
        "cleared": cleared,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main.web_app:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )
