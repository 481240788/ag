import asyncio
import os
import sys
import tempfile
from pathlib import Path

from config import get_settings
from models import ToolResult


async def execute_local_python_unsafe(code: str, timeout: int = 10) -> ToolResult:
    """在宿主机执行可信 Python 代码；这不是安全沙盒，默认不注册。"""
    settings = get_settings()
    effective_timeout = min(max(timeout, 1), int(settings.tool_timeout_seconds))
    file_path: Path | None = None
    process = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as file:
            file.write(code)
            file_path = Path(file.name)

        process = await asyncio.create_subprocess_exec(
            sys.executable, str(file_path),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=effective_timeout
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            return ToolResult.failure(
                "TOOL_TIMEOUT", f"执行超时：超过 {effective_timeout} 秒"
            )

        max_chars = settings.python_max_output_chars
        stdout = stdout_bytes.decode("utf-8", errors="replace")[:max_chars]
        stderr = stderr_bytes.decode("utf-8", errors="replace")[:max_chars]
        data = {
            "return_code": process.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "output_truncated": (
                len(stdout_bytes) > max_chars or len(stderr_bytes) > max_chars
            ),
        }
        if process.returncode == 0:
            return ToolResult.success(data)
        return ToolResult.failure("EXECUTION_FAILED", stderr or "Python 执行失败")
    except OSError as error:
        return ToolResult.failure("EXECUTION_FAILED", f"无法执行 Python：{error}")
    finally:
        if process is not None and process.returncode is None:
            process.kill()
            await process.wait()
        if file_path is not None:
            try:
                os.remove(file_path)
            except FileNotFoundError:
                pass


execute_python = execute_local_python_unsafe
