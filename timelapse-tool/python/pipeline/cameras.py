import json
from pathlib import Path

# 通用标准分辨率（宽降序），用于派生某机型的可选导出分辨率
STANDARD_RESOLUTIONS = [
    ("8K", [7680, 4320]),
    ("4K", [3840, 2160]),
    ("2K", [2048, 1080]),
    ("1080p", [1920, 1080]),
]


class CameraStore:
    """相机配置的读写与分辨率派生。数据持久化在一个 JSON 文件里。"""

    def __init__(self, path):
        self.path = Path(path)
        self._cameras = self._load()

    def _load(self):
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text())
        return data.get("cameras", [])

    def _save(self):
        self.path.write_text(json.dumps({"cameras": self._cameras}, ensure_ascii=False, indent=2))

    def list(self):
        return list(self._cameras)

    def _find(self, name):
        for cam in self._cameras:
            if cam["name"] == name:
                return cam
        raise KeyError(name)

    def resolution_options(self, name):
        cam = self._find(name)
        native_w, native_h = cam["native"]
        options = [{"label": "原分辨率", "size": [native_w, native_h]}]
        for label, size in STANDARD_RESOLUTIONS:
            if size[0] <= native_w:
                options.append({"label": label, "size": size})
        return options

    def add(self, name, native):
        if any(c["name"] == name for c in self._cameras):
            raise ValueError(f"相机已存在: {name}")
        self._cameras.append({"name": name, "native": list(native)})
        self._save()
