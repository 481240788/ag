from pathlib import Path


class PathPolicyError(ValueError):
    pass


class PathPolicy:
    #不允许的文件名
    SENSITIVE_NAMES = {
        ".env", ".env.local", ".env.production", "id_rsa", "id_ed25519",
        "credentials.json", "secrets.json",
    }

    def __init__(
        self,
        #允许可读路径
        readable_roots: list[Path],
        #允许可写路径
        writable_roots: list[Path],
        base_path: Path | None = None,
    ) -> None:
        self.base_path = (base_path or Path.cwd()).resolve()
        self.readable_roots = [root.resolve() for root in readable_roots]
        self.writable_roots = [root.resolve() for root in writable_roots]

    def validate_read(self, raw_path: str | Path) -> Path:
        """
        判断raw_path是否可读
        """
        path = self._resolve(raw_path)
        self._validate(path, self.readable_roots)
        return path

    def validate_write(self, raw_path: str | Path) -> Path:
        """
        判断raw_path是否可写
        """
        path = self._resolve(raw_path)
        self._validate(path, self.writable_roots)
        return path

    def _resolve(self, raw_path: str | Path) -> Path:
        """
        将路径转为绝对路径
        """
        path = Path(raw_path)
        if not path.is_absolute():
            #转换为绝对路径
            path = self.base_path / path
        self._reject_symlinks(path.absolute())
        #允许解析不存在的路径(便于写操作)
        return path.resolve(strict=False)

    def _validate(self, path: Path, allowed_roots: list[Path]) -> None:
        """
        三层检查：
            1.检查path是否在允许访问路径中
            2.检查path对应文件是否是配置文件(.env...)
            3.检查path中是否包含符号链接越过红区
        """
        if not any(self._is_within(path, root) for root in allowed_roots):
            raise PathPolicyError("路径不在允许访问的目录中")
        if path.name.lower() in self.SENSITIVE_NAMES or path.name.lower().startswith(".env"):
            raise PathPolicyError("禁止访问敏感文件")
        self._reject_symlinks(path)

    @staticmethod
    def _is_within(path: Path, root: Path) -> bool:
        """
        input:
            path:路径
            root:允许访问的路径
        return:
            True:path在root中
        """
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    @staticmethod
    def _reject_symlinks(path: Path) -> None:
        """
        检查传入路径中是否有符号链接绕过红区
        """
        current = path
        while True:
            
            if current.exists() and current.is_symlink():
                raise PathPolicyError("禁止通过符号链接访问文件")
            if current.parent == current:
                break
            #一层一层向父文件夹中查询
            current = current.parent
