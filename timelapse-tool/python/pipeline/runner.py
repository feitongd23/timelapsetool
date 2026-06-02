from pathlib import Path

from pipeline.models import PipelineState

SEQUENCE_EXTS = {".tif", ".tiff", ".jpg", ".jpeg", ".png"}


class PipelineRunner:
    """按状态机顺序驱动阶段；遇到手动阶段暂停，等 continue_ 恢复。"""

    def __init__(self, stages, emit):
        self._stages = stages
        self._emit = emit
        self._state = PipelineState.IDLE
        self._index = 0
        self._current = None
        self._completed = []
        self._error = None
        self._config = None

    def status(self):
        return {
            "state": self._state,
            "current_stage": self._current,
            "completed": list(self._completed),
            "error": self._error,
        }

    def start(self, config):
        config.validate()
        self._config = config
        self._state = PipelineState.RUNNING
        self._index = 0
        self._current = None
        self._completed = []
        self._error = None
        self._run_until_pause_or_done()

    def continue_(self):
        if self._state != PipelineState.WAITING_FOR_USER:
            raise RuntimeError("当前不处于等待用户状态")
        self._check_sequence_ready()
        self._state = PipelineState.RUNNING
        self._index += 1
        self._run_until_pause_or_done()

    def _check_sequence_ready(self):
        folder = Path(self._config.lrt_export_folder)
        has_image = any(p.suffix.lower() in SEQUENCE_EXTS for p in folder.iterdir())
        if not has_image:
            raise ValueError("LRT 导出文件夹里没有图像序列，请先在 LRTimelapse 中导出")

    def _run_until_pause_or_done(self):
        while self._index < len(self._stages):
            stage = self._stages[self._index]
            self._current = stage.name
            if stage.manual:
                stage.run(self._config, self._emit)
                self._state = PipelineState.WAITING_FOR_USER
                return
            try:
                stage.run(self._config, self._emit)
            except Exception as exc:
                self._state = PipelineState.FAILED
                self._error = str(exc)
                return
            self._completed.append(stage.name)
            self._index += 1
        self._state = PipelineState.DONE
