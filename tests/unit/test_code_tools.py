import asyncio

from LLMTools.code_tools import execute_local_python_unsafe


def test_execute_python_success():
    result = asyncio.run(execute_local_python_unsafe("print(2 + 3)"))
    assert result.ok
    assert result.data["stdout"].strip() == "5"


def test_execute_python_failure():
    result = asyncio.run(execute_local_python_unsafe("raise RuntimeError('boom')"))
    assert not result.ok
    assert result.error_code == "EXECUTION_FAILED"


def test_execute_python_timeout():
    result = asyncio.run(execute_local_python_unsafe("while True: pass", timeout=1))
    assert not result.ok
    assert result.error_code == "TOOL_TIMEOUT"
