from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List

# 帧率允许自由输入，只校验合理范围（含常用 12/15/24/25/30/48/50/60/90/120）
MIN_FPS, MAX_FPS = 1, 120
ALLOWED_CODECS = {"H.264", "H.265", "ProRes"}


class PipelineState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING_FOR_USER = "waiting_for_user"
    DONE = "done"
    FAILED = "failed"


@dataclass
class PipelineConfig:
    raw_folder: str
    camera_name: str
    lrt_export_folder: str
    stabilize: bool
    resolution: List[int]
    fps: int
    codec: str
    output_path: str

    def validate(self):
        if not Path(self.raw_folder).is_dir():
            raise ValueError(f"RAW 文件夹不存在: {self.raw_folder}")
        if not Path(self.lrt_export_folder).is_dir():
            raise ValueError(f"LRT 导出序列文件夹不存在: {self.lrt_export_folder}")
        if not Path(self.output_path).is_dir():
            raise ValueError(f"输出路径不存在: {self.output_path}")
        if not (MIN_FPS <= self.fps <= MAX_FPS):
            raise ValueError(f"帧率不支持: {self.fps}（应在 {MIN_FPS}-{MAX_FPS}）")
        if self.codec not in ALLOWED_CODECS:
            raise ValueError(f"编码不支持: {self.codec}")
        if not (isinstance(self.resolution, list) and len(self.resolution) == 2):
            raise ValueError("分辨率必须是 [宽, 高]")
