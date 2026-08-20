from LLMTools.code_tools import execute_python


def test_execute_python_success():
    result = execute_python("print(2 + 3)")
    assert result.ok
    assert result.data["stdout"].strip() == "5"


def test_execute_python_failure():
    result = execute_python("raise RuntimeError('boom')")
    assert not result.ok
    assert result.error_code == "EXECUTION_FAILED"


def test_execute_python_timeout():
    result = execute_python("while True: pass", timeout=1)
    assert not result.ok
    assert result.error_code == "TOOL_TIMEOUT"
