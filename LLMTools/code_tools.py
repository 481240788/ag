import subprocess,os,sys,tempfile


def execute_python(code: str, timeout: int = 10) -> str:
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

        return (
            f"return_code: {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    except subprocess.TimeoutExpired:
        return f"执行超时：超过 {timeout} 秒"

    finally:
        os.remove(file_path)