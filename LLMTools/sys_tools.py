from datetime import datetime
from pathlib import Path
from path_manager import PathManager
from models import ToolResult
pathmanager = PathManager()

def get_current_time() -> ToolResult:
    """
    获取当前的时间（例如：2026-08-14 14:49:52.692439）
    return:
        当前的时间
    """
    today_date = datetime.today()
    return ToolResult.success({"current_time": str(today_date)})

def read_file_content(file_path:str) -> ToolResult:
    """
    读取对应路径的文件内容
    input:
        file_path:需要读取内容的文件地址
    return:
        文件的内容
    """
    #最大允许文件大小为5MB
    MAX_FILE_SIZE = 5 * 1024 * 1024
    path = Path(file_path)
    
    try:
        if not path.exists():
            return ToolResult.failure("NOT_FOUND", f"文件{file_path}不存在")
        
        if not path.is_file():
            return ToolResult.failure("INVALID_ARGUMENT", f"文件{file_path}不是一个文件")
        
        # 禁止读取 .env 文件
        if path.name == ".env":
            return ToolResult.failure("PERMISSION_DENIED", "禁止读取 .env 文件")
        
        if path.stat().st_size > MAX_FILE_SIZE:
            return ToolResult.failure("FILE_TOO_LARGE", f"文件{file_path}过大，暂不支持读取")
    
        return ToolResult.success({"path": str(path.resolve()), "content": path.read_text(encoding='utf-8')})
    except PermissionError:
        return ToolResult.failure("PERMISSION_DENIED", f"文件{file_path}无权限读取")
    except UnicodeDecodeError:
        return ToolResult.failure("INVALID_ENCODING", f"文件{file_path}不是 UTF-8 编码")
    except OSError as e:
        return ToolResult.failure("INTERNAL_ERROR", f"读取文件失败：{e}")

def list_directory(file_path:str) -> ToolResult:
    """
    列出对应路径下的所有文件
    input:
        file_path:需要查看其中的文件的文件夹路径
    return
        查看路径下的所有文件
    """
    path = Path(file_path)
    try:
        if not path.exists():
            return ToolResult.failure("NOT_FOUND", f"文件夹{file_path}不存在")
        if not path.is_dir():
            return ToolResult.failure("INVALID_ARGUMENT", f"{file_path}不是一个文件夹")
    
        items = []

        for item in path.iterdir():
            if item.is_dir():
                items.append(f"[DIR] {item.name}")
            else:
                items.append(f"[FILE] {item.name}")

        return ToolResult.success({"path": str(path.resolve()), "items": items})
    except PermissionError:
        return ToolResult.failure("PERMISSION_DENIED", f"文件夹{file_path}无权限读取")
    except OSError as e:
        return ToolResult.failure("INTERNAL_ERROR", f"读取文件夹失败：{e}")

def write_new_file(file_parent_path:str,file_name:str,content:str) -> ToolResult:
    """
    向主机中写一个新的文件
    暂时只允许在当前工程项目的根目录中的examples文件夹中进行操作
    input:
        file_parent_path:文件的父文件夹位置
        file_name:文件名(包含后缀)
        content:写入的内容
    return:
        若出错，则返回对应问题。若正常完成，则返回正常完成的语句
    example:
        file_parent_path:   'F:/helloworld'
        file_name:          'helloworld.py'
        content:            ...
    """    
    
    path = Path(file_parent_path).resolve()
    #项目的根目录
    root_path = pathmanager.abs_path.resolve()
    examples_path = (root_path / "examples").resolve()

    #判断操作是否在要求的文件夹中进行
    try:
        path.relative_to(examples_path)
    except ValueError:
        return ToolResult.failure("PERMISSION_DENIED", "只能在当前工程项目的 examples 文件夹中创建文件")
    
    if path.drive.upper() == "C:":
        return ToolResult.failure("PERMISSION_DENIED", "无法向系统盘中写入文件")
    
    try:
        #检查父文件夹是否存在，不存在则创建
        path.mkdir(exist_ok=True,parents=True)
        #组装文件路径
        file_path = path / file_name
    
        with open(file_path,'x',encoding='utf-8') as f:
            f.write(content)
        return ToolResult.success({"path": str(file_path), "message": "文件写入成功"})
    except FileExistsError:
        return ToolResult.failure("ALREADY_EXISTS", f"路径{path / file_name}已存在文件")
    except PermissionError:
        return ToolResult.failure("PERMISSION_DENIED", f"路径{path}无权限写入")
    
def get_current_filepath() -> ToolResult:
    """
    得到当前项目所处的路径(当前项目的根路径)
    """
    return ToolResult.success({"path": str(pathmanager.abs_path)})
