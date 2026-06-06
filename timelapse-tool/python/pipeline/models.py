from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List

from pipeline.export_formats import validate_social
from pipeline.effects import validate_stabilize

# 帧率允许自由输入，只校验合理范围（含常用 12/15/24/25/30/48/50/60/90/120）
MIN_FPS, MAX_FPS = 1, 120


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
    stabilize: dict
    resolution: List[int]
    fps: int
    social: dict
    output_path: str

    def validate(self):
        if not Path(self.raw_folder).is_dir():
            raise ValueError(f"RAW 文件夹不存在: {self.raw_folder}")
        if not Path(self.output_path).is_dir():
            raise ValueError(f"输出路径不存在: {self.output_path}")
        if not (MIN_FPS <= self.fps <= MAX_FPS):
            raise ValueError(f"帧率不支持: {self.fps}（应在 {MIN_FPS}-{MAX_FPS}）")
        validate_social(self.social)
        validate_stabilize(self.stabilize)
        if not (isinstance(self.resolution, list) and len(self.resolution) == 2):
            raise ValueError("分辨率必须是 [宽, 高]")
