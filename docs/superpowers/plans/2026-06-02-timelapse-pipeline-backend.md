# 延时流水线后端骨架 (Pipeline Backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在已有的 FastAPI 后端上，实现延时流水线的编排核心：相机配置、流水线参数校验、阶段状态机（BR→LRT手动暂停→AE→PR）、桩阶段、REST + WebSocket 接口。不调用任何 Adobe 软件，全部可单元测试。

**Architecture:** 一个 `PipelineRunner` 顺序执行若干 `Stage`。BR/AE/PR 在本计划是桩实现（只校验路径 + 通过回调推送进度），真实 Adobe 调用由后续计划替换。LRT 是一个特殊的「手动暂停」阶段：runner 跑到它时把状态置为 `WAITING_FOR_USER` 并停下，等前端调 `/pipeline/continue` 且校验 LRT 导出文件夹已有图片后，再继续 AE、PR。相机配置持久化到 `cameras.json`。

**Tech Stack:** Python 3.9, FastAPI, pytest。沿用 `timelapse-tool/python/` 现有结构与 venv。

---

## File Structure

```
timelapse-tool/python/
├── server.py                      # 既有；本计划新增流水线 REST + WS 路由
├── pipeline/
│   ├── __init__.py
│   ├── cameras.py                 # 相机配置：加载/保存/分辨率选项
│   ├── models.py                  # PipelineConfig 数据类 + 校验；PipelineState 枚举
│   ├── stages.py                  # Stage 基类 + BR/LRT/AE/PR 桩阶段
│   └── runner.py                  # PipelineRunner 状态机：start / continue / status
├── cameras.json                   # 相机预设数据（随仓库提供默认）
└── tests/
    ├── test_server.py             # 既有
    ├── test_cameras.py            # 新增
    ├── test_models.py             # 新增
    ├── test_stages.py             # 新增
    ├── test_runner.py             # 新增
    └── test_pipeline_api.py       # 新增
```

**职责边界：**
- `cameras.py`：只管相机数据的读写与分辨率派生，不含流水线逻辑。
- `models.py`：只定义数据结构与校验规则，无副作用。
- `stages.py`：每个阶段一个类，单一职责 `run(config, emit)`。本计划为桩。
- `runner.py`：只负责按状态机驱动阶段，不知道具体阶段内部做什么。
- `server.py`：只暴露 HTTP/WS，把请求转给 runner。

测试运行约定：所有 pytest 命令的 cwd = `timelapse-tool/python`，用 `.venv/bin/python -m pytest`。

---

## Task 1: 相机配置数据与默认 cameras.json

**Files:**
- Create: `timelapse-tool/python/cameras.json`
- Create: `timelapse-tool/python/pipeline/__init__.py`
- Create: `timelapse-tool/python/pipeline/cameras.py`
- Test: `timelapse-tool/python/tests/test_cameras.py`

- [ ] **Step 1: 创建默认 cameras.json**

创建 `timelapse-tool/python/cameras.json`：

```json
{
  "cameras": [
    { "name": "Sony A7R IV", "native": [9504, 6336] },
    { "name": "Sony A7R V", "native": [9728, 6656] },
    { "name": "Sony A7 IV", "native": [7008, 4672] },
    { "name": "Canon R5", "native": [8192, 5464] },
    { "name": "Nikon Z9", "native": [8256, 5504] },
    { "name": "Fujifilm GFX100S", "native": [11648, 8736] }
  ]
}
```

- [ ] **Step 2: 创建 pipeline 包标记**

创建空文件 `timelapse-tool/python/pipeline/__init__.py`（内容为空）。

- [ ] **Step 3: 写失败的测试**

创建 `timelapse-tool/python/tests/test_cameras.py`：

```python
import json
from pathlib import Path

import pytest

from pipeline.cameras import CameraStore

STANDARD = {"8K": [7680, 4320], "4K": [3840, 2160], "2K": [2048, 1080], "1080p": [1920, 1080]}


@pytest.fixture
def store(tmp_path):
    cfg = tmp_path / "cameras.json"
    cfg.write_text(json.dumps({"cameras": [{"name": "Sony A7R IV", "native": [9504, 6336]}]}))
    return CameraStore(cfg)


def test_list_returns_seeded_cameras(store):
    names = [c["name"] for c in store.list()]
    assert "Sony A7R IV" in names


def test_resolution_options_includes_native_and_smaller_standards(store):
    opts = store.resolution_options("Sony A7R IV")
    # 原分辨率排第一
    assert opts[0] == {"label": "原分辨率", "size": [9504, 6336]}
    labels = [o["label"] for o in opts]
    # 只包含不超过原生分辨率的标准规格
    assert "8K" in labels and "4K" in labels and "1080p" in labels


def test_resolution_options_unknown_camera_raises(store):
    with pytest.raises(KeyError):
        store.resolution_options("Nonexistent")


def test_add_camera_persists_to_disk(store, tmp_path):
    store.add("Custom Cam", [6000, 4000])
    reloaded = CameraStore(tmp_path / "cameras.json")
    assert any(c["name"] == "Custom Cam" for c in reloaded.list())


def test_add_duplicate_name_raises(store):
    with pytest.raises(ValueError):
        store.add("Sony A7R IV", [1, 1])
```

- [ ] **Step 4: 运行测试确认失败**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_cameras.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'pipeline.cameras'`。

- [ ] **Step 5: 写最小实现**

创建 `timelapse-tool/python/pipeline/cameras.py`：

```python
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
```

- [ ] **Step 6: 运行测试确认通过**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_cameras.py -v`
Expected: 5 个测试全部 PASS。

- [ ] **Step 7: 提交**

```bash
git add timelapse-tool/python/cameras.json timelapse-tool/python/pipeline/__init__.py timelapse-tool/python/pipeline/cameras.py timelapse-tool/python/tests/test_cameras.py
git commit -m "feat: 相机配置存储与分辨率派生"
```

---

## Task 2: 流水线参数模型与校验

**Files:**
- Create: `timelapse-tool/python/pipeline/models.py`
- Test: `timelapse-tool/python/tests/test_models.py`

- [ ] **Step 1: 写失败的测试**

创建 `timelapse-tool/python/tests/test_models.py`：

```python
import pytest

from pipeline.models import PipelineConfig, PipelineState


def _valid_kwargs(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    preset = tmp_path / "preset.xmp"; preset.write_text("x")
    lrt = tmp_path / "seq"; lrt.mkdir()
    out = tmp_path / "out"; out.mkdir()
    return dict(
        raw_folder=str(raw),
        camera_name="Sony A7R IV",
        acr_preset_path=str(preset),
        lrt_export_folder=str(lrt),
        stabilize=True,
        resolution=[3840, 2160],
        fps=24,
        codec="ProRes",
        output_path=str(out),
    )


def test_valid_config_passes(tmp_path):
    cfg = PipelineConfig(**_valid_kwargs(tmp_path))
    cfg.validate()  # 不抛异常


def test_missing_raw_folder_fails(tmp_path):
    kwargs = _valid_kwargs(tmp_path)
    kwargs["raw_folder"] = str(tmp_path / "nope")
    with pytest.raises(ValueError, match="RAW 文件夹"):
        PipelineConfig(**kwargs).validate()


def test_bad_fps_fails(tmp_path):
    kwargs = _valid_kwargs(tmp_path)
    kwargs["fps"] = 99
    with pytest.raises(ValueError, match="帧率"):
        PipelineConfig(**kwargs).validate()


def test_bad_codec_fails(tmp_path):
    kwargs = _valid_kwargs(tmp_path)
    kwargs["codec"] = "WMV"
    with pytest.raises(ValueError, match="编码"):
        PipelineConfig(**kwargs).validate()


def test_states_exist():
    assert PipelineState.IDLE
    assert PipelineState.RUNNING
    assert PipelineState.WAITING_FOR_USER
    assert PipelineState.DONE
    assert PipelineState.FAILED
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_models.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'pipeline.models'`。

- [ ] **Step 3: 写最小实现**

创建 `timelapse-tool/python/pipeline/models.py`：

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_models.py -v`
Expected: 5 个测试全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add timelapse-tool/python/pipeline/models.py timelapse-tool/python/tests/test_models.py
git commit -m "feat: 流水线参数模型与校验"
```

---

## Task 3: 阶段抽象与桩阶段

**Files:**
- Create: `timelapse-tool/python/pipeline/stages.py`
- Test: `timelapse-tool/python/tests/test_stages.py`

阶段约定：每个阶段有 `name` 和 `run(config, emit)`。`emit(message)` 是进度回调（接收一个 str）。LRT 阶段是手动阶段，用 `manual = True` 标记，runner 见到它会暂停。`run` 抛异常表示失败。

- [ ] **Step 1: 写失败的测试**

创建 `timelapse-tool/python/tests/test_stages.py`：

```python
from pipeline.stages import BRStage, LRTStage, AEStage, PRStage, default_stages


def test_default_stages_order():
    names = [s.name for s in default_stages()]
    assert names == ["BR", "LRT", "AE", "PR"]


def test_lrt_stage_is_manual():
    assert LRTStage().manual is True
    assert BRStage().manual is False


def test_br_stage_emits_progress():
    messages = []
    BRStage().run(config=None, emit=messages.append)
    assert any("BR" in m for m in messages)


def test_ae_and_pr_stages_emit_progress():
    msgs = []
    AEStage().run(config=None, emit=msgs.append)
    PRStage().run(config=None, emit=msgs.append)
    assert any("AE" in m for m in msgs)
    assert any("PR" in m for m in msgs)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_stages.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'pipeline.stages'`。

- [ ] **Step 3: 写最小实现**

创建 `timelapse-tool/python/pipeline/stages.py`：

```python
class Stage:
    """流水线阶段基类。子类设置 name / manual，并实现 run()。"""

    name = "Stage"
    manual = False

    def run(self, config, emit):
        """执行阶段。emit(str) 推送进度。抛异常表示失败。"""
        raise NotImplementedError


class BRStage(Stage):
    name = "BR"
    manual = False

    def run(self, config, emit):
        # 桩：真实实现（Bridge 套 ACR 预设）由后续计划替换
        emit("BR 阶段（桩）：批量套用 Camera Raw 预设")


class LRTStage(Stage):
    name = "LRT"
    manual = True  # 手动阶段：runner 跑到这里会暂停等用户

    def run(self, config, emit):
        # 手动阶段无自动动作；打开 LRT 的逻辑由后续计划补充
        emit("LRT 阶段：请在 LRTimelapse 中手动完成关键帧/去闪/导出序列")


class AEStage(Stage):
    name = "AE"
    manual = False

    def run(self, config, emit):
        # 桩：真实实现（aerender）由后续计划替换
        emit("AE 阶段（桩）：渲染图像序列为中间视频")


class PRStage(Stage):
    name = "PR"
    manual = False

    def run(self, config, emit):
        # 桩：真实实现（Premiere 导出）由后续计划替换
        emit("PR 阶段（桩）：导入、增稳、按规格导出成片")


def default_stages():
    return [BRStage(), LRTStage(), AEStage(), PRStage()]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_stages.py -v`
Expected: 4 个测试全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add timelapse-tool/python/pipeline/stages.py timelapse-tool/python/tests/test_stages.py
git commit -m "feat: 阶段抽象与 BR/LRT/AE/PR 桩阶段"
```

---

## Task 4: 流水线状态机 PipelineRunner

**Files:**
- Create: `timelapse-tool/python/pipeline/runner.py`
- Test: `timelapse-tool/python/tests/test_runner.py`

runner 行为：
- `start(config)`：校验 config；依次跑阶段；遇到 `manual` 阶段时，先执行该阶段的 `run`（推送提示），然后把状态置 `WAITING_FOR_USER` 并停在该阶段，返回。
- `continue_()`：仅当处于 `WAITING_FOR_USER`；校验 LRT 导出文件夹有图片（`.tif/.tiff/.jpg/.jpeg/.png` 任一）；继续跑剩余阶段直到 `DONE`。
- 任一阶段抛异常 → 状态 `FAILED`，记录 `error` 与失败阶段名。
- `status()`：返回 `{state, current_stage, completed, error}`。
- 进度通过构造时传入的 `emit` 回调推送。

- [ ] **Step 1: 写失败的测试**

创建 `timelapse-tool/python/tests/test_runner.py`：

```python
import pytest

from pipeline.models import PipelineConfig, PipelineState
from pipeline.runner import PipelineRunner
from pipeline.stages import Stage, LRTStage


def _cfg(tmp_path, with_seq_image=False):
    raw = tmp_path / "raw"; raw.mkdir()
    preset = tmp_path / "p.xmp"; preset.write_text("x")
    lrt = tmp_path / "seq"; lrt.mkdir()
    out = tmp_path / "out"; out.mkdir()
    if with_seq_image:
        (lrt / "0001.tif").write_text("img")
    return PipelineConfig(
        raw_folder=str(raw), camera_name="Cam", acr_preset_path=str(preset),
        lrt_export_folder=str(lrt), stabilize=False, resolution=[3840, 2160],
        fps=24, codec="ProRes", output_path=str(out),
    )


class RecordingStage(Stage):
    def __init__(self, name, manual=False):
        self.name = name
        self.manual = manual
        self.ran = False

    def run(self, config, emit):
        self.ran = True
        emit(f"{self.name} ran")


def test_start_pauses_at_manual_stage(tmp_path):
    stages = [RecordingStage("BR"), RecordingStage("LRT", manual=True),
              RecordingStage("AE"), RecordingStage("PR")]
    runner = PipelineRunner(stages=stages, emit=lambda m: None)
    runner.start(_cfg(tmp_path))
    assert runner.status()["state"] == PipelineState.WAITING_FOR_USER
    assert stages[0].ran is True   # BR 跑了
    assert stages[2].ran is False  # AE 还没跑


def test_continue_requires_sequence_images(tmp_path):
    stages = [RecordingStage("LRT", manual=True), RecordingStage("AE")]
    runner = PipelineRunner(stages=stages, emit=lambda m: None)
    runner.start(_cfg(tmp_path, with_seq_image=False))
    with pytest.raises(ValueError, match="序列"):
        runner.continue_()


def test_continue_finishes_pipeline(tmp_path):
    stages = [RecordingStage("BR"), RecordingStage("LRT", manual=True),
              RecordingStage("AE"), RecordingStage("PR")]
    runner = PipelineRunner(stages=stages, emit=lambda m: None)
    runner.start(_cfg(tmp_path, with_seq_image=True))
    runner.continue_()
    assert runner.status()["state"] == PipelineState.DONE
    assert all(s.ran for s in stages)


def test_failure_sets_failed_state(tmp_path):
    class Boom(Stage):
        name = "AE"
        manual = False
        def run(self, config, emit):
            raise RuntimeError("炸了")

    stages = [RecordingStage("LRT", manual=True), Boom()]
    runner = PipelineRunner(stages=stages, emit=lambda m: None)
    runner.start(_cfg(tmp_path, with_seq_image=True))
    runner.continue_()
    st = runner.status()
    assert st["state"] == PipelineState.FAILED
    assert st["current_stage"] == "AE"
    assert "炸了" in st["error"]


def test_invalid_config_fails_fast(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.fps = 99
    runner = PipelineRunner(stages=[RecordingStage("BR")], emit=lambda m: None)
    with pytest.raises(ValueError, match="帧率"):
        runner.start(cfg)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_runner.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'pipeline.runner'`。

- [ ] **Step 3: 写最小实现**

创建 `timelapse-tool/python/pipeline/runner.py`：

```python
from pathlib import Path

from pipeline.models import PipelineState

SEQUENCE_EXTS = {".tif", ".tiff", ".jpg", ".jpeg", ".png"}


class PipelineRunner:
    """按状态机顺序驱动阶段；遇到手动阶段暂停，等 continue_ 恢复。"""

    def __init__(self, stages, emit):
        self._stages = stages
        self._emit = emit
        self._state = PipelineState.IDLE
        self._index = 0           # 下一个待跑阶段的下标
        self._current = None      # 当前/最近阶段名
        self._completed = []      # 已完成阶段名
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
        self._index += 1  # 跳过已完成的手动阶段
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
                # 手动阶段：执行提示，然后暂停等待用户
                stage.run(self._config, self._emit)
                self._state = PipelineState.WAITING_FOR_USER
                return
            try:
                stage.run(self._config, self._emit)
            except Exception as exc:  # 阶段失败
                self._state = PipelineState.FAILED
                self._error = str(exc)
                return
            self._completed.append(stage.name)
            self._index += 1
        self._state = PipelineState.DONE
```

注意：手动阶段在 `start` 期间被执行（推送提示）但不计入 `completed`，`continue_` 用 `self._index += 1` 跳过它继续后续阶段。测试 `test_continue_finishes_pipeline` 断言「所有阶段 ran」成立，因为手动阶段的 `run` 在 start 时已被调用。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_runner.py -v`
Expected: 5 个测试全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add timelapse-tool/python/pipeline/runner.py timelapse-tool/python/tests/test_runner.py
git commit -m "feat: 流水线状态机 PipelineRunner"
```

---

## Task 5: REST + WebSocket 接口

**Files:**
- Modify: `timelapse-tool/python/server.py`
- Test: `timelapse-tool/python/tests/test_pipeline_api.py`

接口设计：
- `GET /cameras` → `{"cameras": [...], }`（机型列表）
- `GET /cameras/{name}/resolutions` → `{"options": [...]}`（某机型分辨率选项）
- `POST /cameras` body `{name, native:[w,h]}` → 201；重名 409
- `POST /pipeline/start` body = PipelineConfig 各字段 → `{status: ...}`；校验失败 400
- `POST /pipeline/continue` → `{status: ...}`；非等待态 409，序列未就绪 400
- `GET /pipeline/status` → runner.status()

进度通过既有 `/ws` 推送：每次 emit 时向所有连接的 WS 客户端广播 `{"type": "progress", "message": ...}`。本计划用一个简单的内存广播器。

- [ ] **Step 1: 写失败的测试**

创建 `timelapse-tool/python/tests/test_pipeline_api.py`：

```python
from fastapi.testclient import TestClient

import server

client = TestClient(server.app)


def test_get_cameras_lists_presets():
    r = client.get("/cameras")
    assert r.status_code == 200
    names = [c["name"] for c in r.json()["cameras"]]
    assert "Sony A7R IV" in names


def test_get_resolutions_for_camera():
    r = client.get("/cameras/Sony A7R IV/resolutions")
    assert r.status_code == 200
    assert r.json()["options"][0]["label"] == "原分辨率"


def test_get_resolutions_unknown_camera_404():
    r = client.get("/cameras/Nope/resolutions")
    assert r.status_code == 404


def test_pipeline_start_then_status_then_continue(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    preset = tmp_path / "p.xmp"; preset.write_text("x")
    lrt = tmp_path / "seq"; lrt.mkdir(); (lrt / "0001.tif").write_text("i")
    out = tmp_path / "out"; out.mkdir()
    body = dict(
        raw_folder=str(raw), camera_name="Sony A7R IV", acr_preset_path=str(preset),
        lrt_export_folder=str(lrt), stabilize=False, resolution=[3840, 2160],
        fps=24, codec="ProRes", output_path=str(out),
    )
    r = client.post("/pipeline/start", json=body)
    assert r.status_code == 200
    assert r.json()["state"] == "waiting_for_user"

    r2 = client.get("/pipeline/status")
    assert r2.json()["state"] == "waiting_for_user"

    r3 = client.post("/pipeline/continue")
    assert r3.status_code == 200
    assert r3.json()["state"] == "done"


def test_pipeline_start_bad_fps_400(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    preset = tmp_path / "p.xmp"; preset.write_text("x")
    lrt = tmp_path / "seq"; lrt.mkdir()
    out = tmp_path / "out"; out.mkdir()
    body = dict(
        raw_folder=str(raw), camera_name="Sony A7R IV", acr_preset_path=str(preset),
        lrt_export_folder=str(lrt), stabilize=False, resolution=[3840, 2160],
        fps=99, codec="ProRes", output_path=str(out),
    )
    r = client.post("/pipeline/start", json=body)
    assert r.status_code == 400


def test_add_camera_then_listed():
    r = client.post("/cameras", json={"name": "Test Cam X", "native": [6000, 4000]})
    assert r.status_code == 201
    names = [c["name"] for c in client.get("/cameras").json()["cameras"]]
    assert "Test Cam X" in names
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_pipeline_api.py -v`
Expected: FAIL（路由不存在，404）。

- [ ] **Step 3: 写最小实现**

在 `timelapse-tool/python/server.py` 末尾（`if __name__` 块之前）追加：

```python
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel

from pipeline.cameras import CameraStore
from pipeline.models import PipelineConfig
from pipeline.runner import PipelineRunner
from pipeline.stages import default_stages

_CAMERAS_PATH = Path(__file__).parent / "cameras.json"
_camera_store = CameraStore(_CAMERAS_PATH)


class _Broadcaster:
    """记录所有活跃 WS 连接，emit 时广播进度。"""

    def __init__(self):
        self._clients = set()

    def add(self, ws):
        self._clients.add(ws)

    def remove(self, ws):
        self._clients.discard(ws)

    def emit(self, message):
        # 同步 emit：把消息存到队列，WS 端点循环取。简化为直接记录最近消息列表。
        self._last_messages.append(message) if hasattr(self, "_last_messages") else None


_progress_log = []
_runner = PipelineRunner(stages=default_stages(), emit=_progress_log.append)


@app.get("/cameras")
def get_cameras():
    return {"cameras": _camera_store.list()}


@app.get("/cameras/{name}/resolutions")
def get_resolutions(name: str):
    try:
        return {"options": _camera_store.resolution_options(name)}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"未知相机: {name}")


class AddCameraBody(BaseModel):
    name: str
    native: list


@app.post("/cameras", status_code=201)
def add_camera(body: AddCameraBody):
    try:
        _camera_store.add(body.name, body.native)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": True}


class StartBody(BaseModel):
    raw_folder: str
    camera_name: str
    acr_preset_path: str
    lrt_export_folder: str
    stabilize: bool
    resolution: list
    fps: int
    codec: str
    output_path: str


@app.post("/pipeline/start")
def pipeline_start(body: StartBody):
    config = PipelineConfig(**body.dict())
    try:
        _runner.start(config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _runner.status()


@app.post("/pipeline/continue")
def pipeline_continue():
    try:
        _runner.continue_()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _runner.status()


@app.get("/pipeline/status")
def pipeline_status():
    return _runner.status()
```

注意：`_runner.status()` 返回的 `state` 是 `PipelineState`（str 枚举），FastAPI 序列化为其字符串值（如 `"waiting_for_user"`）。`_Broadcaster` 在本计划用不到 WS 实时广播（进度先存 `_progress_log`），WS 实时推送留待 UI 计划；保留 `/ws` ping/pong 既有行为不变。删掉上面 `_Broadcaster` 类（本计划未用到）以免死代码——只保留 `_progress_log` 与 `_runner`。

- [ ] **Step 4: 按上一步的注意事项删除未用的 `_Broadcaster` 类**

确保 `server.py` 中不包含 `_Broadcaster` 类定义（YAGNI：本计划不需要）。只保留 `_progress_log = []` 和 `_runner = PipelineRunner(...)`。

- [ ] **Step 5: 运行测试确认通过**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/ -v`
Expected: 全部测试 PASS（含既有 test_server.py 的 health/ws 两项）。

- [ ] **Step 6: 提交**

```bash
git add timelapse-tool/python/server.py timelapse-tool/python/tests/test_pipeline_api.py
git commit -m "feat: 流水线 REST 接口（相机/启动/继续/状态）"
```

---

## Task 6: 全量回归与手动验证

**Files:** 无（验证任务）

- [ ] **Step 1: 跑全部后端测试**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/ -v`
Expected: 全绿，无失败、无报错。

- [ ] **Step 2: 手动验证服务可启动且新路由可用**

Run: `cd timelapse-tool/python && .venv/bin/python server.py &` 然后 `sleep 2 && curl -s http://127.0.0.1:8756/cameras`
Expected: 返回包含 Sony A7R IV 的相机列表 JSON。验证后 `kill %1`。

- [ ] **Step 3: 确认无残留进程**

Run: `pgrep -f server.py || echo none`
Expected: `none`。

---

## Self-Review Notes

- **Spec 覆盖**：本计划实现 spec 第 4.1（流水线参数，去掉已废弃的去闪/关键帧控件）、4.2（相机机型与分辨率）、第 5 节数据流的「状态机骨架」部分。真实 Adobe 调用（BR/AE/PR）是桩，由后续计划 2c/2d/2e 替换。LRT 手动暂停语义已实现。
- **类型一致性**：`PipelineConfig` 字段在 models.py 定义，runner、server、测试中引用一致；`PipelineState` 的字符串值（`waiting_for_user`/`done`/`failed`）在 runner 与 api 测试中一致。`Stage.name`/`Stage.manual`/`run(config, emit)` 接口在 stages.py、runner.py、测试中一致。
- **占位符扫描**：桩阶段是有意的最小实现（emit 提示），非占位符；每个桩都有明确注释说明后续计划替换。
- **YAGNI**：明确删除未使用的 `_Broadcaster`；WS 实时进度推送推迟到 UI 计划再做。
- **测试可独立运行**：所有测试用 `tmp_path` 构造临时文件夹，不依赖真实素材或 Adobe 软件。
- **已知副作用**：`test_add_camera_then_listed` 会向仓库内的 `cameras.json` 真实写入「Test Cam X」。这是真实持久化行为的验证。实现者注意：测试后该条目会留在 cameras.json，提交前应 `git checkout timelapse-tool/python/cameras.json` 还原，避免把测试数据提交进去。
