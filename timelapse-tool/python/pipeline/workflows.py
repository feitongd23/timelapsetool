import json
from pathlib import Path

from pipeline.stages import BRStage, LRTStage, AEStage, ExportStage

# 固定顺序与阶段注册表
CANONICAL_ORDER = ["BR", "LRT", "AE", "导出"]
_REGISTRY = {"BR": BRStage, "LRT": LRTStage, "AE": AEStage, "导出": ExportStage}

BUILTIN = {
    "全流程": ["BR", "LRT", "AE", "导出"],
    "跳过BR": ["LRT", "AE", "导出"],
    "无导出": ["BR", "LRT", "AE"],
    "极简": ["LRT", "AE"],
}


def normalize(names):
    """去重并按固定顺序排列。"""
    chosen = set(names)
    return [n for n in CANONICAL_ORDER if n in chosen]


def validate_workflow(names):
    if not names:
        raise ValueError("工作流不能为空")
    for n in names:
        if n not in _REGISTRY:
            raise ValueError(f"未知阶段: {n}")
    chosen = set(names)
    if "导出" in chosen and "AE" not in chosen:
        raise ValueError("含 导出 的工作流必须包含 AE（导出 需要 AE 的中间视频）")


def build_stages(names):
    validate_workflow(names)
    return [_REGISTRY[n]() for n in normalize(names)]


class WorkflowStore:
    """自定义工作流的读写；all() 合并内置 + 自定义（自定义覆盖同名内置）。"""

    def __init__(self, path):
        self.path = Path(path)
        self._custom = self._load()

    def _load(self):
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text()).get("workflows", {})

    def _save_file(self):
        self.path.write_text(
            json.dumps({"workflows": self._custom}, ensure_ascii=False, indent=2)
        )

    def custom(self):
        return dict(self._custom)

    def all(self):
        merged = dict(BUILTIN)
        merged.update(self._custom)
        return merged

    def save(self, name, names):
        validate_workflow(names)
        self._custom[name] = normalize(names)
        self._save_file()
