import json
from pathlib import Path


def load_cases(path: Path | None = None) -> list[dict]:
    """
    加载设置好的测评案例，方便批量调用agent进行测试
    """
    case_path = path or Path(__file__).with_name("cases.json")
    cases = json.loads(case_path.read_text(encoding="utf-8"))
    required = {"id", "question", "expected_tools", "forbidden_tools", "expected_status"}
    for case in cases:
        missing = required - case.keys()
        if missing:
            raise ValueError(f"用例 {case.get('id', '<unknown>')} 缺少字段: {sorted(missing)}")
    return cases


if __name__ == "__main__":
    loaded = load_cases()
    print(f"已加载 {len(loaded)} 个评测用例")
