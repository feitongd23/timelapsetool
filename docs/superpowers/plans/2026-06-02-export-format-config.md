# 导出格式配置 (Export Format) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把流水线的导出格式从单一 `codec` 字符串升级为「预设 / 手动」两模式的完整配置：预设一键选成品规格，手动可细调编码+质量。纯逻辑 + UI，不依赖 Adobe，全部可单测。

**Architecture:** 后端新增 `export_formats` 模块，定义预设表、编码→容器映射、ProRes 档位、各编码的质量校验，并把 `PipelineConfig.codec: str` 替换为 `export: dict`（结构化导出规格）。前端导出区域加「预设/手动」切换，纯函数把表单态转成 `export` dict 喂给现有 `buildStartPayload`。后端 PR 桩阶段先不消费该 dict（真实导出在 2e）。

**Tech Stack:** Python 3.9 + FastAPI（后端），Electron 原生 JS + Jest/jsdom（前端）。沿用现有结构。

---

## File Structure

```
timelapse-tool/python/
├── pipeline/
│   ├── export_formats.py     # 新增：预设表 / 校验 / 编码→容器 / ProRes 档位
│   └── models.py             # 修改：codec:str → export:dict，validate 调 export 校验
├── server.py                 # 修改：StartBody.codec → export；新增 GET /export/presets
└── tests/
    ├── test_export_formats.py  # 新增
    ├── test_models.py          # 修改：用 export dict
    └── test_pipeline_api.py    # 修改：start body 用 export；presets 端点

timelapse-tool/electron/renderer/
├── index.html                # 修改：编码下拉 → 导出格式区域（预设/手动切换）
├── pipeline.js               # 修改：buildExportConfig 纯函数；payload 带 export
tests/
└── pipeline.test.js          # 修改：buildExportConfig 测试；payload 断言
```

**职责边界：** `export_formats.py` 是导出规格的唯一事实来源（预设、校验规则都在这），前后端都引用它的定义；`models.py` 只调用它做校验，不重复规则。

测试约定：后端 `cd timelapse-tool/python && .venv/bin/python -m pytest`；前端 `cd timelapse-tool && export PATH="$HOME/.local/node/bin:$PATH" && npx jest --testEnvironment=jsdom`。

---

## 导出规格数据结构（贯穿前后端）

`export` 是一个 dict：

```
ProRes:  { "codec": "ProRes", "container": "MOV", "prores_profile": "422 HQ" }
H.264:   { "codec": "H.264",  "container": "MP4", "bitrate_mbps": 80, "quality": "high" }
H.265:   { "codec": "H.265",  "container": "MP4", "bitrate_mbps": 60, "bit_depth": 10 }
```

- 编码：`ProRes` / `H.264` / `H.265`
- 容器：ProRes→MOV，H.264/H.265→MP4（由编码决定）
- ProRes 档位：`Proxy / LT / 422 / 422 HQ / 4444 / 4444 XQ`
- H.264 质量：`high / medium / low`；码率 1–500 Mbps
- H.265 位深：`8 / 10`；码率 1–500 Mbps

---

## Task 1: 导出格式模块（预设 / 校验）

**Files:**
- Create: `timelapse-tool/python/pipeline/export_formats.py`
- Test: `timelapse-tool/python/tests/test_export_formats.py`

- [ ] **Step 1: 写失败的测试**

创建 `timelapse-tool/python/tests/test_export_formats.py`：

```python
import pytest

from pipeline.export_formats import (
    PRESETS,
    expand_preset,
    validate_export,
    container_for,
)


def test_presets_have_expected_names():
    assert "母版 · ProRes 422 HQ" in PRESETS
    assert "母版 · ProRes 4444" in PRESETS
    assert "交付 · H.265 10bit" in PRESETS
    assert "社媒 · H.264 高质量" in PRESETS
    assert "社媒 · H.264 压缩" in PRESETS


def test_expand_preset_returns_full_export_dict():
    exp = expand_preset("母版 · ProRes 422 HQ")
    assert exp["codec"] == "ProRes"
    assert exp["container"] == "MOV"
    assert exp["prores_profile"] == "422 HQ"


def test_expand_unknown_preset_raises():
    with pytest.raises(KeyError):
        expand_preset("不存在")


def test_container_for_codec():
    assert container_for("ProRes") == "MOV"
    assert container_for("H.264") == "MP4"
    assert container_for("H.265") == "MP4"


def test_validate_prores_ok():
    validate_export({"codec": "ProRes", "container": "MOV", "prores_profile": "4444"})


def test_validate_prores_bad_profile():
    with pytest.raises(ValueError, match="ProRes"):
        validate_export({"codec": "ProRes", "container": "MOV", "prores_profile": "999"})


def test_validate_h264_ok():
    validate_export({"codec": "H.264", "container": "MP4", "bitrate_mbps": 80, "quality": "high"})


def test_validate_h264_bad_bitrate():
    with pytest.raises(ValueError, match="码率"):
        validate_export({"codec": "H.264", "container": "MP4", "bitrate_mbps": 0, "quality": "high"})


def test_validate_h265_bad_bit_depth():
    with pytest.raises(ValueError, match="位深"):
        validate_export({"codec": "H.265", "container": "MP4", "bitrate_mbps": 60, "bit_depth": 12})


def test_validate_unknown_codec():
    with pytest.raises(ValueError, match="编码"):
        validate_export({"codec": "WMV", "container": "MP4"})


def test_validate_wrong_container_for_codec():
    with pytest.raises(ValueError, match="容器"):
        validate_export({"codec": "ProRes", "container": "MP4", "prores_profile": "422"})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_export_formats.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'pipeline.export_formats'`。

- [ ] **Step 3: 写最小实现**

创建 `timelapse-tool/python/pipeline/export_formats.py`：

```python
"""导出格式的唯一事实来源：编码、容器、ProRes 档位、码率范围、预设、校验。"""

CODECS = {"ProRes", "H.264", "H.265"}
PRORES_PROFILES = {"Proxy", "LT", "422", "422 HQ", "4444", "4444 XQ"}
H264_QUALITIES = {"high", "medium", "low"}
H265_BIT_DEPTHS = {8, 10}
MIN_BITRATE, MAX_BITRATE = 1, 500

# 编码 → 容器
_CONTAINER = {"ProRes": "MOV", "H.264": "MP4", "H.265": "MP4"}

# 成品预设：名称 → 完整 export dict
PRESETS = {
    "母版 · ProRes 422 HQ": {"codec": "ProRes", "container": "MOV", "prores_profile": "422 HQ"},
    "母版 · ProRes 4444": {"codec": "ProRes", "container": "MOV", "prores_profile": "4444"},
    "交付 · H.265 10bit": {"codec": "H.265", "container": "MP4", "bitrate_mbps": 60, "bit_depth": 10},
    "社媒 · H.264 高质量": {"codec": "H.264", "container": "MP4", "bitrate_mbps": 80, "quality": "high"},
    "社媒 · H.264 压缩": {"codec": "H.264", "container": "MP4", "bitrate_mbps": 25, "quality": "medium"},
}


def container_for(codec):
    return _CONTAINER[codec]


def expand_preset(name):
    """把预设名展开成完整 export dict（拷贝，避免外部改动污染）。"""
    return dict(PRESETS[name])


def validate_export(export):
    codec = export.get("codec")
    if codec not in CODECS:
        raise ValueError(f"编码不支持: {codec}")
    if export.get("container") != container_for(codec):
        raise ValueError(f"容器与编码不匹配: {codec} 应为 {container_for(codec)}")
    if codec == "ProRes":
        if export.get("prores_profile") not in PRORES_PROFILES:
            raise ValueError(f"ProRes 档位不支持: {export.get('prores_profile')}")
    else:  # H.264 / H.265
        bitrate = export.get("bitrate_mbps")
        if not (isinstance(bitrate, int) and MIN_BITRATE <= bitrate <= MAX_BITRATE):
            raise ValueError(f"码率不支持: {bitrate}（应在 {MIN_BITRATE}-{MAX_BITRATE} Mbps）")
        if codec == "H.264" and export.get("quality") not in H264_QUALITIES:
            raise ValueError(f"H.264 质量档不支持: {export.get('quality')}")
        if codec == "H.265" and export.get("bit_depth") not in H265_BIT_DEPTHS:
            raise ValueError(f"位深不支持: {export.get('bit_depth')}")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_export_formats.py -v`
Expected: 11 个测试全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add timelapse-tool/python/pipeline/export_formats.py timelapse-tool/python/tests/test_export_formats.py
git commit -m "feat: 导出格式模块（预设/校验/编码-容器映射）"
```

---

## Task 2: PipelineConfig 用 export dict 替换 codec

**Files:**
- Modify: `timelapse-tool/python/pipeline/models.py`
- Modify: `timelapse-tool/python/tests/test_models.py`

- [ ] **Step 1: 改测试（先让它反映新结构）**

编辑 `timelapse-tool/python/tests/test_models.py`：把 `_valid_kwargs` 里的 `codec="ProRes",` 整行替换为：

```python
        export={"codec": "ProRes", "container": "MOV", "prores_profile": "422 HQ"},
```

并把现有的 `test_bad_codec_fails` 整个函数替换为：

```python
def test_bad_export_fails(tmp_path):
    kwargs = _valid_kwargs(tmp_path)
    kwargs["export"] = {"codec": "WMV", "container": "MP4"}
    with pytest.raises(ValueError, match="编码"):
        PipelineConfig(**kwargs).validate()


def test_valid_h265_export_passes(tmp_path):
    kwargs = _valid_kwargs(tmp_path)
    kwargs["export"] = {"codec": "H.265", "container": "MP4", "bitrate_mbps": 60, "bit_depth": 10}
    PipelineConfig(**kwargs).validate()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_models.py -v`
Expected: FAIL（`PipelineConfig` 仍有 `codec` 字段，缺 `export`，构造报错 `unexpected keyword argument 'export'` 或缺 `codec`）。

- [ ] **Step 3: 改实现**

编辑 `timelapse-tool/python/pipeline/models.py`：

把字段定义里的：

```python
    codec: str
```

替换为：

```python
    export: dict
```

把顶部 import 区（`from typing import List` 行附近）加入：

```python
from pipeline.export_formats import validate_export
```

删除 `ALLOWED_CODECS = {...}` 那一行（已移到 export_formats）。

把 `validate` 里的：

```python
        if self.codec not in ALLOWED_CODECS:
            raise ValueError(f"编码不支持: {self.codec}")
```

替换为：

```python
        validate_export(self.export)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_models.py -v`
Expected: 全部 PASS。

- [ ] **Step 5: 修 runner 测试里的 config 构造**

`tests/test_runner.py` 的 `_cfg` 里也有 `codec="ProRes",`。把该行替换为：

```python
        export={"codec": "ProRes", "container": "MOV", "prores_profile": "422 HQ"},
```

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_runner.py -v`
Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add timelapse-tool/python/pipeline/models.py timelapse-tool/python/tests/test_models.py timelapse-tool/python/tests/test_runner.py
git commit -m "feat: PipelineConfig 用结构化 export 替换 codec 字段"
```

---

## Task 3: API —— start 用 export，新增预设端点

**Files:**
- Modify: `timelapse-tool/python/server.py`
- Modify: `timelapse-tool/python/tests/test_pipeline_api.py`

- [ ] **Step 1: 改测试**

编辑 `timelapse-tool/python/tests/test_pipeline_api.py`：

两处 `body = dict(...)` 里的 `fps=24, codec="ProRes", output_path=str(out),` 与 `fps=0, codec="ProRes", output_path=str(out),`，把 `codec="ProRes"` 改为：

```python
        export={"codec": "ProRes", "container": "MOV", "prores_profile": "422 HQ"},
```

（即两个 body 都用 export dict 代替 codec 字段。）

在文件末尾追加预设端点测试：

```python
def test_get_export_presets():
    r = client.get("/export/presets")
    assert r.status_code == 200
    names = r.json()["presets"]
    assert "母版 · ProRes 422 HQ" in names
    assert "社媒 · H.264 高质量" in names
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_pipeline_api.py -v`
Expected: FAIL（StartBody 仍是 codec；`/export/presets` 404）。

- [ ] **Step 3: 改实现**

编辑 `timelapse-tool/python/server.py`：

`StartBody` 里把：

```python
    codec: str
```

替换为：

```python
    export: dict
```

在 `from pipeline.stages import default_stages` 之后加入：

```python
from pipeline.export_formats import PRESETS
```

在 `/cameras` 相关路由附近（任意位置，`if __name__` 之前）加入预设端点：

```python
@app.get("/export/presets")
def get_export_presets():
    return {"presets": list(PRESETS.keys())}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/ -v`
Expected: 全部 PASS。如 `test_add_camera_then_listed` 改动了真实 cameras.json，运行后执行 `cd /Users/feitong/photo-app && git checkout timelapse-tool/python/cameras.json`（该测试已用临时文件隔离，正常不会改；保险起见检查 `git status`）。

- [ ] **Step 5: 提交**

```bash
git add timelapse-tool/python/server.py timelapse-tool/python/tests/test_pipeline_api.py
git commit -m "feat: pipeline/start 接收结构化 export，新增 /export/presets"
```

---

## Task 4: 前端导出格式纯函数（TDD）

**Files:**
- Modify: `timelapse-tool/electron/renderer/pipeline.js`
- Modify: `timelapse-tool/tests/pipeline.test.js`

新增纯函数 `buildExportConfig(state)`：根据模式产出 export dict。
- `state.mode === "preset"`：用 `state.preset`（预设名）+ 注入的 `presetTable`（名→dict）展开。
- `state.mode === "manual"`：按 `state.codec` 组装；ProRes 用 `prores_profile`；H.264 用 `bitrate_mbps`+`quality`；H.265 用 `bitrate_mbps`+`bit_depth`。容器由编码决定。

- [ ] **Step 1: 写失败的测试**

在 `timelapse-tool/tests/pipeline.test.js` 顶部 require 行追加 `buildExportConfig`，并把 require 改为：

```javascript
const { buildStartPayload, stageBoardModel, canContinue, continueLabel, buildExportConfig } = require("../electron/renderer/pipeline.js");
```

在文件末尾追加：

```javascript
const PRESET_TABLE = {
  "母版 · ProRes 422 HQ": { codec: "ProRes", container: "MOV", prores_profile: "422 HQ" },
};

test("buildExportConfig 预设模式展开预设", () => {
  const exp = buildExportConfig({ mode: "preset", preset: "母版 · ProRes 422 HQ" }, PRESET_TABLE);
  expect(exp).toEqual({ codec: "ProRes", container: "MOV", prores_profile: "422 HQ" });
});

test("buildExportConfig 手动 ProRes", () => {
  const exp = buildExportConfig({ mode: "manual", codec: "ProRes", prores_profile: "4444" }, PRESET_TABLE);
  expect(exp).toEqual({ codec: "ProRes", container: "MOV", prores_profile: "4444" });
});

test("buildExportConfig 手动 H.264 转换码率为整数", () => {
  const exp = buildExportConfig({ mode: "manual", codec: "H.264", bitrate_mbps: "80", quality: "high" }, PRESET_TABLE);
  expect(exp).toEqual({ codec: "H.264", container: "MP4", bitrate_mbps: 80, quality: "high" });
});

test("buildExportConfig 手动 H.265 带位深", () => {
  const exp = buildExportConfig({ mode: "manual", codec: "H.265", bitrate_mbps: "60", bit_depth: "10" }, PRESET_TABLE);
  expect(exp).toEqual({ codec: "H.265", container: "MP4", bitrate_mbps: 60, bit_depth: 10 });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd timelapse-tool && export PATH="$HOME/.local/node/bin:$PATH" && npx jest --testEnvironment=jsdom tests/pipeline.test.js`
Expected: FAIL（`buildExportConfig is not a function`）。

- [ ] **Step 3: 写实现**

在 `timelapse-tool/electron/renderer/pipeline.js` 中，`canContinue` 函数之后加入：

```javascript
const CONTAINER = { ProRes: "MOV", "H.264": "MP4", "H.265": "MP4" };

// 把导出区域的表单态转成后端要的 export dict
function buildExportConfig(state, presetTable) {
  if (state.mode === "preset") {
    return Object.assign({}, presetTable[state.preset]);
  }
  const codec = state.codec;
  const exp = { codec: codec, container: CONTAINER[codec] };
  if (codec === "ProRes") {
    exp.prores_profile = state.prores_profile;
  } else if (codec === "H.264") {
    exp.bitrate_mbps = parseInt(state.bitrate_mbps, 10);
    exp.quality = state.quality;
  } else if (codec === "H.265") {
    exp.bitrate_mbps = parseInt(state.bitrate_mbps, 10);
    exp.bit_depth = parseInt(state.bit_depth, 10);
  }
  return exp;
}
```

并把 `module.exports` 那行加上 `buildExportConfig`：

```javascript
  module.exports = { buildStartPayload, stageBoardModel, canContinue, continueLabel, buildExportConfig, STAGES };
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd timelapse-tool && export PATH="$HOME/.local/node/bin:$PATH" && npx jest --testEnvironment=jsdom tests/pipeline.test.js`
Expected: 全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add timelapse-tool/electron/renderer/pipeline.js timelapse-tool/tests/pipeline.test.js
git commit -m "feat: 前端 buildExportConfig 纯函数（预设/手动 → export dict）"
```

---

## Task 5: 前端导出格式 UI（HTML + 绑定）

**Files:**
- Modify: `timelapse-tool/electron/renderer/index.html`
- Modify: `timelapse-tool/electron/renderer/pipeline.js`

DOM 部分靠 Task 6 实机验证。

- [ ] **Step 1: 替换 HTML 里的编码字段为导出格式区域**

在 `timelapse-tool/electron/renderer/index.html` 中，把现有的编码 field：

```html
          <div class="field">
            <label>编码</label>
            <select id="codec">
              <option value="ProRes">ProRes</option>
              <option value="H.264">H.264</option>
              <option value="H.265">H.265</option>
            </select>
          </div>
```

替换为（注意它原本和「帧率」在同一个 `.row` 里，替换后帧率单独占一行也可接受）：

```html
          <div class="field">
            <label>导出模式</label>
            <select id="export_mode">
              <option value="preset">预设</option>
              <option value="manual">手动</option>
            </select>
          </div>
```

在该 `.row` 结束 `</div>` 之后、`输出路径` field 之前，插入导出格式详情区：

```html
        <div class="field" id="preset-field">
          <label>导出预设</label>
          <select id="export_preset"></select>
        </div>

        <div id="manual-fields" class="hidden">
          <div class="field">
            <label>编码</label>
            <select id="manual_codec">
              <option value="ProRes">ProRes (MOV)</option>
              <option value="H.264">H.264 (MP4)</option>
              <option value="H.265">H.265 (MP4)</option>
            </select>
          </div>
          <div class="field" id="prores-field">
            <label>ProRes 档位</label>
            <select id="prores_profile">
              <option>Proxy</option><option>LT</option><option>422</option>
              <option selected>422 HQ</option><option>4444</option><option>4444 XQ</option>
            </select>
          </div>
          <div class="row" id="bitrate-row">
            <div class="field">
              <label>目标码率 (Mbps)</label>
              <input id="bitrate_mbps" type="number" min="1" max="500" value="80" />
            </div>
            <div class="field" id="h264-quality-field">
              <label>质量档</label>
              <select id="h264_quality">
                <option value="high">高</option>
                <option value="medium">中</option>
                <option value="low">低</option>
              </select>
            </div>
            <div class="field hidden" id="h265-depth-field">
              <label>位深</label>
              <select id="h265_bit_depth">
                <option value="8">8bit</option>
                <option value="10" selected>10bit</option>
              </select>
            </div>
          </div>
        </div>
```

- [ ] **Step 2: 在 pipeline.js 的 initPipeline 里加载预设并绑定模式切换**

在 `timelapse-tool/electron/renderer/pipeline.js` 的 `initPipeline` 函数体内，`await loadResolutions();` 之后插入：

```javascript
  // 加载导出预设
  let presetTable = {};
  try {
    const data = await fetch(httpBase + "/export/presets").then((r) => r.json());
    const presetSel = id("export_preset");
    presetSel.innerHTML = "";
    for (const name of data.presets) {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      presetSel.appendChild(opt);
      // 预设名→dict 由后端校验，前端展开只需名字；保留占位以便 buildExportConfig
      presetTable[name] = null;
    }
  } catch (_) {
    errEl.textContent = "无法加载导出预设";
    return;
  }

  // 导出模式切换：预设 / 手动
  function syncExportMode() {
    const manual = id("export_mode").value === "manual";
    id("preset-field").classList.toggle("hidden", manual);
    id("manual-fields").classList.toggle("hidden", !manual);
  }
  id("export_mode").addEventListener("change", syncExportMode);
  syncExportMode();

  // 手动编码切换：显示对应的质量控件
  function syncManualCodec() {
    const codec = id("manual_codec").value;
    id("prores-field").classList.toggle("hidden", codec !== "ProRes");
    id("bitrate-row").classList.toggle("hidden", codec === "ProRes");
    id("h264-quality-field").classList.toggle("hidden", codec !== "H.264");
    id("h265-depth-field").classList.toggle("hidden", codec !== "H.265");
  }
  id("manual_codec").addEventListener("change", syncManualCodec);
  syncManualCodec();
```

注意：预设展开放在后端更可靠——前端 `presetTable[name] = null` 仅占位。为让预设模式也能在前端构造 payload，改为**预设模式下 payload 只带预设名**，由后端展开。见下一步。

- [ ] **Step 3: 改 readForm / start 提交逻辑，使用 export**

在 `pipeline.js` 中：

把 `readForm()` 里的 `codec: id("codec").value,` 那一行**删除**（编码不再是顶层字段）。

把「开始处理」按钮的点击处理内构造 body 的逻辑改为：根据导出模式构造 export。找到：

```javascript
      body: JSON.stringify(buildStartPayload(readForm())),
```

替换为：

```javascript
      body: JSON.stringify(buildStartBody()),
```

并在 `initPipeline` 内（`id("btn-start")...` 之前）新增一个闭包函数：

```javascript
  function buildStartBody() {
    const payload = buildStartPayload(readForm());
    const mode = id("export_mode").value;
    if (mode === "preset") {
      // 预设模式：只传预设名，后端展开
      payload.export = null;
      payload.preset = id("export_preset").value;
    } else {
      payload.export = buildExportConfig({
        mode: "manual",
        codec: id("manual_codec").value,
        prores_profile: id("prores_profile").value,
        bitrate_mbps: id("bitrate_mbps").value,
        quality: id("h264_quality").value,
        bit_depth: id("h265_bit_depth").value,
      });
    }
    return payload;
  }
```

> `buildStartPayload` 仍负责 raw_folder/camera_name/lrt_export_folder/stabilize/resolution/fps/output_path；不再产出 codec。需把 `buildStartPayload` 中残留的任何 codec 字段删除（若有）。

- [ ] **Step 4: 后端支持「预设名展开」**

编辑 `timelapse-tool/python/server.py` 的 `StartBody`：把 `export: dict` 改为允许二选一：

```python
    export: dict | None = None
    preset: str | None = None
```

> Python 3.9 不支持 `dict | None` 语法，改用 `from typing import Optional` 并写 `Optional[dict]` / `Optional[str]`。

在 `pipeline_start` 里，构造 `PipelineConfig` 之前，把 preset 展开为 export：

```python
@app.post("/pipeline/start")
def pipeline_start(body: StartBody):
    data = body.dict()
    preset = data.pop("preset", None)
    if data.get("export") is None and preset:
        from pipeline.export_formats import expand_preset
        try:
            data["export"] = expand_preset(preset)
        except KeyError:
            raise HTTPException(status_code=400, detail=f"未知导出预设: {preset}")
    config = PipelineConfig(**data)
    try:
        _runner.start(config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _runner.status()
```

补一个后端测试（`tests/test_pipeline_api.py` 末尾）：

```python
def test_pipeline_start_with_preset(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    lrt = tmp_path / "seq"; lrt.mkdir(); (lrt / "0001.tif").write_text("i")
    out = tmp_path / "out"; out.mkdir()
    body = dict(
        raw_folder=str(raw), camera_name="Sony A7R IV",
        lrt_export_folder=str(lrt), stabilize=False, resolution=[3840, 2160],
        fps=24, output_path=str(out), preset="母版 · ProRes 422 HQ",
    )
    r = client.post("/pipeline/start", json=body)
    assert r.status_code == 200
    assert r.json()["state"] == "waiting_for_user"
```

- [ ] **Step 5: 跑后端 + 前端全量测试**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/ -v`
Run: `cd timelapse-tool && export PATH="$HOME/.local/node/bin:$PATH" && npx jest --testEnvironment=jsdom`
Expected: 后端全 PASS、前端全 PASS。

- [ ] **Step 6: 提交**

```bash
git add timelapse-tool/electron/renderer/index.html timelapse-tool/electron/renderer/pipeline.js timelapse-tool/python/server.py timelapse-tool/python/tests/test_pipeline_api.py
git commit -m "feat: 导出格式 UI（预设/手动切换）与后端预设展开"
```

---

## Task 6: 实机端到端验证

**Files:** 无（验证任务）

- [ ] **Step 1: 准备测试素材**

```bash
mkdir -p /tmp/tl_demo/raw /tmp/tl_demo/seq /tmp/tl_demo/out && touch /tmp/tl_demo/seq/0001.tif
```

- [ ] **Step 2: 启动应用**

Run: `cd timelapse-tool && export PATH="$HOME/.local/node/bin:$PATH" && npm start`
Expected: 「导出模式」下拉默认「预设」，下面是「导出预设」下拉（5 个预设）；切到「手动」后出现编码下拉，选 ProRes 显示档位、选 H.264 显示码率+质量档、选 H.265 显示码率+位深。

- [ ] **Step 3: 预设模式跑一遍**

填 `/tmp/tl_demo/raw`、`/tmp/tl_demo/seq`、`/tmp/tl_demo/out`，导出模式「预设」选「母版 · ProRes 422 HQ」，点开始 → 继续(BR) → 继续(LRT) → 四阶段全绿。

- [ ] **Step 4: 手动模式跑一遍**

导出模式切「手动」，编码选 H.265，码率 60、位深 10bit，重复开始→继续→继续，四阶段全绿。
（验证完清理 `rm -rf /tmp/tl_demo`。）

---

## Self-Review Notes

- **Spec 覆盖**：实现导出格式「预设为主 + 手动」需求；编码限定 H.264/H.265/ProRes（无 DNxHR）；ProRes 档位、H.264 质量、H.265 位深、码率范围齐全；AE 中间渲染固定 ProRes 4444 属于 2d，不在本计划。
- **类型一致性**：`export` dict 的键（codec/container/prores_profile/bitrate_mbps/quality/bit_depth）在 export_formats.py、models.py、server.py、前端 buildExportConfig 中一致；预设名在后端 PRESETS、`/export/presets`、前端下拉一致。
- **单一事实来源**：所有导出规则集中在 `export_formats.py`，models 仅调用 `validate_export`，不重复。
- **预设展开放后端**：前端预设模式只传 `preset` 名，避免前端硬编码预设内容与后端不一致。
- **占位符扫描**：无 TODO；桩阶段不消费 export（真实导出在 2e）是有意为之，已注明。
- **Python 3.9 注意**：用 `Optional[...]` 而非 `X | None`。
- **测试隔离**：沿用 tmp_path；添加相机测试已隔离，注意 start 测试用模块级 _runner（顺序无副作用，因每次 start 重置状态）。
