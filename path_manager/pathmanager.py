from pathlib import Path

class PathManager:
    def __init__(self) -> None:
        #当前项目的根目录的绝对路径
        self.abs_path = Path(__file__).resolve().parents[1]

