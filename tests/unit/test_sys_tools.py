from LLMTools import sys_tools
from models import ToolResult
from security import PathPolicy


def allow_tmp(monkeypatch, tmp_path):
    monkeypatch.setattr(
        sys_tools, "path_policy", PathPolicy([tmp_path], [tmp_path], base_path=tmp_path)
    )


def test_read_file_success_and_missing(tmp_path, monkeypatch):
    allow_tmp(monkeypatch, tmp_path)
    target = tmp_path / "hello.txt"
    target.write_text("你好", encoding="utf-8")
    result = sys_tools.read_file_content(str(target))
    assert isinstance(result, ToolResult)
    assert result.ok and result.data["content"] == "你好"
    assert sys_tools.read_file_content("missing.txt").error_code == "NOT_FOUND"


def test_list_directory(tmp_path, monkeypatch):
    allow_tmp(monkeypatch, tmp_path)
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    result = sys_tools.list_directory(str(tmp_path))
    assert result.ok
    assert "[FILE] a.txt" in result.data["items"]


def test_rejects_path_traversal_and_sensitive_files(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    allow_tmp(monkeypatch, allowed)
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    assert sys_tools.read_file_content("../secret.txt").error_code == "PERMISSION_DENIED"
    assert sys_tools.read_file_content(str(allowed / ".env.production")).error_code == "PERMISSION_DENIED"


def test_write_validates_combined_target(tmp_path, monkeypatch):
    allow_tmp(monkeypatch, tmp_path)
    assert sys_tools.write_new_file(str(tmp_path), "../x.txt", "x").error_code == "INVALID_ARGUMENT"
    result = sys_tools.write_new_file(str(tmp_path), "ok.txt", "ok")
    assert result.ok
    assert (tmp_path / "ok.txt").read_text(encoding="utf-8") == "ok"
    assert sys_tools.write_new_file(str(tmp_path), "ok.txt", "again").error_code == "ALREADY_EXISTS"


def test_default_policy_rejects_outside_examples(tmp_path):
    assert sys_tools.write_new_file(str(tmp_path), "x.txt", "x").error_code == "PERMISSION_DENIED"
