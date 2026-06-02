from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List

ALLOWED_FPS = {24, 25, 30, 60}
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
    acr_preset_path: str
    lrt_export_folder: str
    stabilize: bool
    resolution: List[int]
    fps: int
    codec: str
    output_path: str

    def validate(self):
        if not Path(self.raw_folder).is_dir():
            raise ValueError(f"RAW 文件夹不存在: {self.raw_folder}")
        if not Path(self.acr_preset_path).is_file():
            raise ValueError(f"Camera Raw 预设文件不存在: {self.acr_preset_path}")
        if not Path(self.lrt_export_folder).is_dir():
            raise ValueError(f"LRT 导出序列文件夹不存在: {self.lrt_export_folder}")
        if not Path(self.output_path).is_dir():
            raise ValueError(f"输出路径不存在: {self.output_path}")
        if self.fps not in ALLOWED_FPS:
            raise ValueError(f"帧率不支持: {self.fps}")
        if self.codec not in ALLOWED_CODECS:
            raise ValueError(f"编码不支持: {self.codec}")
        if not (isinstance(self.resolution, list) and len(self.resolution) == 2):
            raise ValueError("分辨率必须是 [宽, 高]")
