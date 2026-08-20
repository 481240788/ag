import subprocess,os,sys,tempfile
from models import ToolResult


def execute_python(code: str, timeout: int = 10) -> ToolResult:
    """
    执行 Python 代码并返回执行结果。
    input:
        code: 要执行的 Python 代码
        timeout: 最大执行时间，单位秒
    """

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py",
        delete=False,
        encoding="utf-8"
    ) as f:
        f.write(code)
        file_path = f.name

    try:

        result = subprocess.run(
            [sys.executable, file_path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout
        )

        data = {
            "return_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        if result.returncode == 0:
            return ToolResult.success(data)
        return ToolResult.failure("EXECUTION_FAILED", result.stderr or "Python 执行失败")

    except subprocess.TimeoutExpired:
        return ToolResult.failure("TOOL_TIMEOUT", f"执行超时：超过 {timeout} 秒", retryable=False)

    finally:
        os.remove(file_path)
