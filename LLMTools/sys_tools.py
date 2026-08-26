from datetime import datetime
from pathlib import Path

from models import ToolResult
from path_manager import PathManager
from security import PathPolicy, PathPolicyError

pathmanager = PathManager()
examples_path = (pathmanager.abs_path / "examples").resolve()
path_policy = PathPolicy(
    readable_roots=[examples_path],
    writable_roots=[examples_path],
    base_path=pathmanager.abs_path,
)
MAX_FILE_SIZE = 5 * 1024 * 1024


def get_current_time() -> ToolResult:
    return ToolResult.success({"current_time": str(datetime.today())})


def read_file_content(file_path: str) -> ToolResult:
    try:
        path = path_policy.validate_read(file_path)
        if not path.exists():
            return ToolResult.failure("NOT_FOUND", f"文件 {file_path} 不存在")
        if not path.is_file():
            return ToolResult.failure("INVALID_ARGUMENT", f"{file_path} 不是文件")
        if path.stat().st_size > MAX_FILE_SIZE:
            return ToolResult.failure("FILE_TOO_LARGE", "文件超过 5MB 读取限制")
        return ToolResult.success({
            "path": str(path),
            "content": path.read_text(encoding="utf-8"),
        })
    except PathPolicyError as error:
        return ToolResult.failure("PERMISSION_DENIED", str(error))
    except PermissionError:
        return ToolResult.failure("PERMISSION_DENIED", f"文件 {file_path} 无权限读取")
    except UnicodeDecodeError:
        return ToolResult.failure("INVALID_ENCODING", "文件不是 UTF-8 编码")
    except OSError as error:
        return ToolResult.failure("INTERNAL_ERROR", f"读取文件失败：{error}")


def list_directory(file_path: str) -> ToolResult:
    try:
        path = path_policy.validate_read(file_path)
        if not path.exists():
            return ToolResult.failure("NOT_FOUND", f"文件夹 {file_path} 不存在")
        if not path.is_dir():
            return ToolResult.failure("INVALID_ARGUMENT", f"{file_path} 不是文件夹")
        items = [
            f"[DIR] {item.name}" if item.is_dir() else f"[FILE] {item.name}"
            for item in path.iterdir()
        ]
        return ToolResult.success({"path": str(path), "items": sorted(items)})
    except PathPolicyError as error:
        return ToolResult.failure("PERMISSION_DENIED", str(error))
    except PermissionError:
        return ToolResult.failure("PERMISSION_DENIED", f"文件夹 {file_path} 无权限读取")
    except OSError as error:
        return ToolResult.failure("INTERNAL_ERROR", f"读取文件夹失败：{error}")


def write_new_file(file_parent_path: str, file_name: str, content: str) -> ToolResult:
    if not file_name or Path(file_name).name != file_name:
        return ToolResult.failure("INVALID_ARGUMENT", "文件名不得包含路径")
    try:
        parent = path_policy.validate_write(file_parent_path)
        target = path_policy.validate_write(parent / file_name)
        parent.mkdir(exist_ok=True, parents=True)
        with target.open("x", encoding="utf-8") as file:
            file.write(content)
        return ToolResult.success({"path": str(target), "message": "文件写入成功"})
    except PathPolicyError as error:
        return ToolResult.failure("PERMISSION_DENIED", str(error))
    except FileExistsError:
        return ToolResult.failure("ALREADY_EXISTS", "目标文件已存在，禁止覆盖")
    except PermissionError:
        return ToolResult.failure("PERMISSION_DENIED", "目标目录无写入权限")
    except OSError as error:
        return ToolResult.failure("INTERNAL_ERROR", f"写入文件失败：{error}")


def get_current_filepath() -> ToolResult:
    return ToolResult.success({"path": str(pathmanager.abs_path)})
