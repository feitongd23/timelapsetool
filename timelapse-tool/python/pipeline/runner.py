# Copyright (c) 2026 杜非同. All rights reserved.
# Part of Timelapse Tool — proprietary software.
# Unauthorized copying, modification, or distribution is prohibited.

from pipeline.models import PipelineState


class PipelineRunner:
    """按状态机顺序驱动阶段；遇到手动阶段暂停，等 continue_ 恢复。

    支持多个手动阶段：每遇到一个 manual 阶段就暂停，continue_ 恢复后继续到
    下一个手动阶段或结束。
    """

    def __init__(self, stages, emit):
        self._stages = stages
        self._log = emit  # 原始日志回调（收字符串）
        self._progress = {"stage": None, "message": None, "fraction": None}
        self._state = PipelineState.IDLE
        self._index = 0
        self._current = None
        self._completed = []
        self._error = None
        self._config = None
        self._notice = None  # 流程相关的提示（如序列回绕已整理）

    def _emit(self, message, fraction=None):
        """阶段进度回调：记录最新进度（含可选 0–1 fraction），并写日志。"""
        self._progress = {"stage": self._current, "message": message, "fraction": fraction}
        self._log(message)

    def status(self):
        return {
            "state": self._state,
            "current_stage": self._current,
            "completed": list(self._completed),
            "error": self._error,
            "notice": self._notice,
            "progress": dict(self._progress),
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
        # 校验当前暂停的手动阶段是否满足恢复条件（如 LRT 需已导出序列）
        paused_stage = self._stages[self._index]
        paused_stage.validate_resume(self._config)
        # 手动阶段视为完成，继续后续阶段
        self._completed.append(paused_stage.name)
        self._state = PipelineState.RUNNING
        self._index += 1
        self._run_until_pause_or_done()

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
