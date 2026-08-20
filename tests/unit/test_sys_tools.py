from LLMTools.sys_tools import list_directory, read_file_content, write_new_file
from models import ToolResult
from path_manager import PathManager


def test_read_file_success_and_missing(tmp_path):
    target = tmp_path / "hello.txt"
    target.write_text("你好", encoding="utf-8")
    result = read_file_content(str(target))
    assert isinstance(result, ToolResult)
    assert result.ok and result.data["content"] == "你好"
    assert read_file_content(str(tmp_path / "missing.txt")).error_code == "NOT_FOUND"


def test_list_directory(tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    result = list_directory(str(tmp_path))
    assert result.ok
    assert "[FILE] a.txt" in result.data["items"]


def test_write_rejects_outside_examples(tmp_path):
    result = write_new_file(str(tmp_path), "x.txt", "x")
    assert not result.ok
    assert result.error_code == "PERMISSION_DENIED"
