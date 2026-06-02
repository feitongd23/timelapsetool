# AE 去闪 + 增稳 (Deflicker + Warp Stabilizer) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 扩展 AE 阶段：在「导入序列 → 渲染」之间加入 AE 原生 Deflicker（第二遍去闪）和变形稳定器（增稳），两者参数都在表单可调。PR 阶段不再增稳。

**Architecture:** `PipelineConfig` 用结构化 `deflicker` / `stabilize` dict 替换旧的 `stabilize: bool`。`ae.build_ae_script` 根据这两个配置，在建合成后、入渲染队列前，条件式地往图层加 Deflicker 与变形稳定器效果并设参数。配置/校验/UI/jsx 拼装可单测；AE 两个效果的确切 matchName 与属性名先由一次**实机内省**确定，再填入 `ae.py` 常量。

**Tech Stack:** Python 3.9 + FastAPI（后端），Electron 原生 JS + Jest（前端），After Effects 2026 ExtendScript。

---

## 配置数据结构

```
deflicker = { "enabled": true,  "strength": 50, "time_radius": 2 }
stabilize = { "enabled": true,  "result": "smooth", "smoothness": 50, "method": "subspace" }
```

- deflicker.strength：0–100；time_radius：1–10
- stabilize.result：`smooth`（平滑运动）/ `none`（无运动）
- stabilize.smoothness：0–100（仅 result=smooth 有效）
- stabilize.method：`position` / `pos_scale_rot` / `perspective` / `subspace`

两者 `enabled=false` 时其余字段不校验、jsx 不加对应效果。

---

## File Structure

```
timelapse-tool/python/
├── pipeline/
│   ├── effects.py        # 新增：deflicker/stabilize 校验 + AE 效果常量映射
│   ├── models.py         # 修改：stabilize:bool → deflicker:dict + stabilize:dict
│   ├── ae.py             # 修改：build_ae_script 注入效果；render_sequence 透传参数
│   └── stages.py         # 修改：AEStage 传 deflicker/stabilize
├── server.py             # 修改：StartBody 字段
└── tests/                # 对应新增/修改测试
electron/renderer/
├── index.html            # 修改：PR 增稳开关 → AE 去闪 + AE 增稳 两个区
└── pipeline.js           # 修改：buildStartPayload 带 deflicker/stabilize
docs/superpowers/
└── ae-introspect.jsx     # 新增：实机内省脚本（Task 3 用）
```

测试约定：后端 `cd timelapse-tool/python && .venv/bin/python -m pytest`；前端 `cd timelapse-tool && export PATH="$HOME/.local/node/bin:$PATH" && npx jest --testEnvironment=jsdom`。

---

## Task 1: 去闪/增稳 配置与校验

**Files:**
- Create: `timelapse-tool/python/pipeline/effects.py`
- Test: `timelapse-tool/python/tests/test_effects.py`

- [ ] **Step 1: 写失败的测试**

创建 `timelapse-tool/python/tests/test_effects.py`：

```python
import pytest

from pipeline.effects import validate_deflicker, validate_stabilize, STABILIZE_METHODS


def test_deflicker_disabled_skips_param_checks():
    validate_deflicker({"enabled": False})  # 不抛


def test_deflicker_valid():
    validate_deflicker({"enabled": True, "strength": 50, "time_radius": 2})


def test_deflicker_bad_strength():
    with pytest.raises(ValueError, match="去闪强度"):
        validate_deflicker({"enabled": True, "strength": 200, "time_radius": 2})


def test_deflicker_bad_time_radius():
    with pytest.raises(ValueError, match="时间半径"):
        validate_deflicker({"enabled": True, "strength": 50, "time_radius": 0})


def test_stabilize_disabled_skips():
    validate_stabilize({"enabled": False})


def test_stabilize_valid():
    validate_stabilize({"enabled": True, "result": "smooth", "smoothness": 50, "method": "subspace"})


def test_stabilize_bad_result():
    with pytest.raises(ValueError, match="结果"):
        validate_stabilize({"enabled": True, "result": "x", "smoothness": 50, "method": "subspace"})


def test_stabilize_bad_method():
    with pytest.raises(ValueError, match="方法"):
        validate_stabilize({"enabled": True, "result": "smooth", "smoothness": 50, "method": "x"})


def test_stabilize_bad_smoothness():
    with pytest.raises(ValueError, match="平滑度"):
        validate_stabilize({"enabled": True, "result": "smooth", "smoothness": 999, "method": "subspace"})


def test_methods_constant():
    assert STABILIZE_METHODS == ["position", "pos_scale_rot", "perspective", "subspace"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_effects.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'pipeline.effects'`。

- [ ] **Step 3: 写实现**

创建 `timelapse-tool/python/pipeline/effects.py`：

```python
"""去闪/增稳配置校验 + AE 效果映射（matchName 等实机常量集中在此）。"""

STABILIZE_RESULTS = ["smooth", "none"]
STABILIZE_METHODS = ["position", "pos_scale_rot", "perspective", "subspace"]

# AE 效果 matchName —— 实机内省（Task 3）确认后回填
DEFLICKER_MATCHNAME = "ADBE Deflicker"          # 待实机确认
WARP_STABILIZER_MATCHNAME = "ADBE SubspaceStabilizer"


def validate_deflicker(deflicker):
    if not deflicker.get("enabled"):
        return
    strength = deflicker.get("strength")
    if not (isinstance(strength, int) and 0 <= strength <= 100):
        raise ValueError(f"去闪强度应在 0-100: {strength}")
    tr = deflicker.get("time_radius")
    if not (isinstance(tr, int) and 1 <= tr <= 10):
        raise ValueError(f"去闪时间半径应在 1-10: {tr}")


def validate_stabilize(stabilize):
    if not stabilize.get("enabled"):
        return
    if stabilize.get("result") not in STABILIZE_RESULTS:
        raise ValueError(f"增稳结果不支持: {stabilize.get('result')}")
    if stabilize.get("method") not in STABILIZE_METHODS:
        raise ValueError(f"增稳方法不支持: {stabilize.get('method')}")
    sm = stabilize.get("smoothness")
    if not (isinstance(sm, int) and 0 <= sm <= 100):
        raise ValueError(f"增稳平滑度应在 0-100: {sm}")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_effects.py -v`
Expected: 10 个测试全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add timelapse-tool/python/pipeline/effects.py timelapse-tool/python/tests/test_effects.py
git commit -m "feat: 去闪/增稳配置校验与效果常量"
```

---

## Task 2: PipelineConfig 接入 deflicker/stabilize

**Files:**
- Modify: `timelapse-tool/python/pipeline/models.py`
- Modify: `timelapse-tool/python/tests/test_models.py`
- Modify: `timelapse-tool/python/tests/test_runner.py`

- [ ] **Step 1: 改测试**

编辑 `timelapse-tool/python/tests/test_models.py` 的 `_valid_kwargs`：把 `stabilize=True,` 整行替换为：

```python
        deflicker={"enabled": True, "strength": 50, "time_radius": 2},
        stabilize={"enabled": True, "result": "smooth", "smoothness": 50, "method": "subspace"},
```

在文件末尾追加：

```python
def test_bad_stabilize_fails(tmp_path):
    kwargs = _valid_kwargs(tmp_path)
    kwargs["stabilize"] = {"enabled": True, "result": "x", "smoothness": 50, "method": "subspace"}
    with pytest.raises(ValueError, match="结果"):
        PipelineConfig(**kwargs).validate()


def test_bad_deflicker_fails(tmp_path):
    kwargs = _valid_kwargs(tmp_path)
    kwargs["deflicker"] = {"enabled": True, "strength": 999, "time_radius": 2}
    with pytest.raises(ValueError, match="去闪强度"):
        PipelineConfig(**kwargs).validate()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_models.py -v`
Expected: FAIL（`PipelineConfig` 仍是 `stabilize: bool`，缺 `deflicker`）。

- [ ] **Step 3: 改实现**

编辑 `timelapse-tool/python/pipeline/models.py`：
- 顶部 import 区加：`from pipeline.effects import validate_deflicker, validate_stabilize`
- 字段 `stabilize: bool` 替换为两行：

```python
    deflicker: dict
    stabilize: dict
```

- 在 `validate(self)` 末尾追加：

```python
        validate_deflicker(self.deflicker)
        validate_stabilize(self.stabilize)
```

- [ ] **Step 4: 运行 models 测试确认通过**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_models.py -v`
Expected: PASS。

- [ ] **Step 5: 修 runner 测试的 config 构造**

编辑 `timelapse-tool/python/tests/test_runner.py` 的 `_cfg`：把 `stabilize=False,` 替换为：

```python
        deflicker={"enabled": False},
        stabilize={"enabled": False},
```

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_runner.py -v`
Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add timelapse-tool/python/pipeline/models.py timelapse-tool/python/tests/test_models.py timelapse-tool/python/tests/test_runner.py
git commit -m "feat: PipelineConfig 接入结构化 deflicker/stabilize"
```

---

## Task 3: 实机内省 —— 确认 AE 效果的真实 matchName/属性

**Files:**
- Create: `docs/superpowers/ae-introspect.jsx`

**此任务需在装有 After Effects 2026 的本机执行；自动化代理把它交回人类。**

- [ ] **Step 1: 写内省脚本**

创建 `docs/superpowers/ae-introspect.jsx`：

```javascript
// 在 AE 里新建一个纯色图层，加上 Deflicker 与变形稳定器，
// 把它们的 matchName 与所有属性的 (name, matchName) 写到桌面 ae-introspect.txt
(function () {
    var comp = app.project.activeItem;
    if (!comp || !(comp instanceof CompItem)) {
        comp = app.project.items.addComp("introspect", 1920, 1080, 1, 5, 25);
    }
    var solid = comp.layers.addSolid([1, 1, 1], "probe", comp.width, comp.height, 1);
    var lines = [];
    function dump(effName) {
        try {
            var fx = solid.property("ADBE Effect Parade").addProperty(effName);
            lines.push("=== " + effName + " => " + fx.name + " (matchName " + fx.matchName + ") ===");
            for (var i = 1; i <= fx.numProperties; i++) {
                var p = fx.property(i);
                lines.push("  [" + i + "] name=" + p.name + " | matchName=" + p.matchName);
            }
        } catch (e) {
            lines.push("!! 无法添加 " + effName + ": " + e.toString());
        }
    }
    // 用显示名尝试；若失败，AE 里手动加效果后看 matchName
    dump("Deflicker");
    dump("ADBE SubspaceStabilizer");
    var f = new File("~/Desktop/ae-introspect.txt");
    f.open("w"); f.write(lines.join("\n")); f.close();
    alert("已写出 ~/Desktop/ae-introspect.txt");
})();
```

- [ ] **Step 2: 在 AE 里运行并回收结果**

打开 After Effects 2026 → 文件 > 脚本 > 运行脚本文件… → 选 `docs/superpowers/ae-introspect.jsx`。
打开桌面生成的 `ae-introspect.txt`，把内容贴给负责实现的人/写进本任务记录。
**产出**：Deflicker 的真实 matchName + 强度/时间半径对应的属性 matchName；变形稳定器里「结果 / 平滑度 / 方法」三个属性的 matchName 与取值映射。

- [ ] **Step 3: 回填常量**

用内省结果修正 `pipeline/effects.py` 里的 `DEFLICKER_MATCHNAME`、`WARP_STABILIZER_MATCHNAME`，并新增属性 matchName 常量（供 Task 4 的 jsx 用），例如：

```python
# 形如（占位，按内省结果替换）：
DEFLICKER_PROP_STRENGTH = "..."     # 强度属性 matchName
DEFLICKER_PROP_TIME_RADIUS = "..."
WS_PROP_RESULT = "..."              # 结果
WS_PROP_SMOOTHNESS = "..."          # 平滑度
WS_PROP_METHOD = "..."              # 方法
# 结果/方法的 AE 枚举取值映射：
WS_RESULT_VALUE = {"smooth": 1, "none": 2}      # 按实机确认
WS_METHOD_VALUE = {"position": 1, "pos_scale_rot": 2, "perspective": 3, "subspace": 4}
```

- [ ] **Step 4: 提交内省脚本与回填的常量**

```bash
git add docs/superpowers/ae-introspect.jsx timelapse-tool/python/pipeline/effects.py
git commit -m "chore: AE 效果内省脚本与真实 matchName 常量"
```

---

## Task 4: jsx 注入 Deflicker + 变形稳定器

**Files:**
- Modify: `timelapse-tool/python/pipeline/ae.py`
- Modify: `timelapse-tool/python/pipeline/stages.py`
- Test: `timelapse-tool/python/tests/test_ae.py`、`timelapse-tool/python/tests/test_stages.py`

> 依赖 Task 3 回填的常量。下面用 `effects` 模块里的常量名引用，实现时以实际回填值为准。

- [ ] **Step 1: 写失败的测试**

在 `timelapse-tool/python/tests/test_ae.py` 末尾追加：

```python
def test_build_ae_script_adds_deflicker_when_enabled():
    jsx = ae.build_ae_script(
        anchor_file="/seq/0001.jpg", fps=24, project_save_path="/tmp/p.aep",
        deflicker={"enabled": True, "strength": 60, "time_radius": 3},
        stabilize={"enabled": False},
    )
    from pipeline.effects import DEFLICKER_MATCHNAME
    assert DEFLICKER_MATCHNAME in jsx
    assert "60" in jsx  # 强度写入


def test_build_ae_script_adds_stabilizer_when_enabled():
    jsx = ae.build_ae_script(
        anchor_file="/seq/0001.jpg", fps=24, project_save_path="/tmp/p.aep",
        deflicker={"enabled": False},
        stabilize={"enabled": True, "result": "smooth", "smoothness": 70, "method": "subspace"},
    )
    from pipeline.effects import WARP_STABILIZER_MATCHNAME
    assert WARP_STABILIZER_MATCHNAME in jsx
    assert "70" in jsx


def test_build_ae_script_skips_effects_when_disabled():
    jsx = ae.build_ae_script(
        anchor_file="/seq/0001.jpg", fps=24, project_save_path="/tmp/p.aep",
        deflicker={"enabled": False}, stabilize={"enabled": False},
    )
    from pipeline.effects import DEFLICKER_MATCHNAME, WARP_STABILIZER_MATCHNAME
    assert DEFLICKER_MATCHNAME not in jsx
    assert WARP_STABILIZER_MATCHNAME not in jsx
```

并把已有的 `test_build_ae_script_contains_paths_and_fps`、`test_render_sequence_*` 三个测试里对 `build_ae_script(...)` / `render_sequence(...)` 的调用补上 `deflicker={"enabled": False}, stabilize={"enabled": False}` 参数（保持签名一致）。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_ae.py -v`
Expected: FAIL（`build_ae_script` 不接受 deflicker/stabilize 参数）。

- [ ] **Step 3: 改实现**

编辑 `timelapse-tool/python/pipeline/ae.py`：
- 顶部加：`from pipeline import effects`
- 把 `build_ae_script` 签名改为 `build_ae_script(anchor_file, fps, project_save_path, deflicker, stabilize)`，在 `comp.layers.add(footage);` 之后、`app.project.renderQueue.items.add(comp);` 之前，插入按需添加效果的 jsx 片段。形如（属性名用 Task 3 回填的常量，下面是结构示意）：

```python
    layer_fx = []
    if deflicker.get("enabled"):
        layer_fx.append(f'''
var df = layer.property("ADBE Effect Parade").addProperty("{effects.DEFLICKER_MATCHNAME}");
df.property("{effects.DEFLICKER_PROP_STRENGTH}").setValue({deflicker["strength"]});
df.property("{effects.DEFLICKER_PROP_TIME_RADIUS}").setValue({deflicker["time_radius"]});
''')
    if stabilize.get("enabled"):
        layer_fx.append(f'''
var ws = layer.property("ADBE Effect Parade").addProperty("{effects.WARP_STABILIZER_MATCHNAME}");
ws.property("{effects.WS_PROP_RESULT}").setValue({{"smooth":1,"none":2}}["{stabilize["result"]}"]);
ws.property("{effects.WS_PROP_SMOOTHNESS}").setValue({stabilize["smoothness"]});
ws.property("{effects.WS_PROP_METHOD}").setValue({effects.WS_METHOD_VALUE!r}["{stabilize["method"]}"]);
''')
    effects_jsx = "var layer = comp.layer(1);\n" + "\n".join(layer_fx) if layer_fx else ""
```

把这段 `effects_jsx` 拼进 f-string 模板的对应位置（`comp.layers.add(footage);` 之后）。
> 注意：变形稳定器需触发分析（`app.executeCommand` 或属性方法），是 Task 5 实机重点；本步先把效果与参数加上。

- 把 `render_sequence` 签名加上 `deflicker, stabilize` 两参，并透传给 `build_ae_script`。

- [ ] **Step 4: 改 stages.py 透传**

编辑 `timelapse-tool/python/pipeline/stages.py` 的 `AEStage.run`：

```python
    def run(self, config, emit):
        from pipeline import ae
        ae.render_sequence(
            seq_folder=config.lrt_export_folder,
            output_dir=config.output_path,
            fps=config.fps,
            deflicker=config.deflicker,
            stabilize=config.stabilize,
            emit=emit,
        )
```

并更新 `tests/test_stages.py` 的 `test_ae_stage_delegates_to_render`：`Cfg` 加 `deflicker = {"enabled": False}` 与 `stabilize = {"enabled": False}`，`fake_render` 签名加 `deflicker, stabilize`，断言它们被传入。

- [ ] **Step 5: 运行全量后端测试确认通过**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/ -v`
Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add timelapse-tool/python/pipeline/ae.py timelapse-tool/python/pipeline/stages.py timelapse-tool/python/tests/test_ae.py timelapse-tool/python/tests/test_stages.py
git commit -m "feat: AE jsx 注入 Deflicker 去闪与变形稳定器增稳"
```

---

## Task 5: API + 前端配置流转

**Files:**
- Modify: `timelapse-tool/python/server.py`、`timelapse-tool/python/tests/test_pipeline_api.py`
- Modify: `timelapse-tool/electron/renderer/pipeline.js`、`timelapse-tool/tests/pipeline.test.js`

- [ ] **Step 1: 后端 StartBody**

编辑 `timelapse-tool/python/server.py` 的 `StartBody`：把 `stabilize: bool` 替换为：

```python
    deflicker: dict
    stabilize: dict
```

更新 `tests/test_pipeline_api.py` 所有 body：把 `stabilize=False,` 替换为：

```python
        deflicker={"enabled": False}, stabilize={"enabled": False},
```

并 mock 掉 AE（已有的两次暂停测试已 monkeypatch `ae.render_sequence`，确认仍然如此）。
Run 后端测试确认 PASS。

- [ ] **Step 2: 前端纯函数测试**

编辑 `timelapse-tool/tests/pipeline.test.js` 的 `buildStartPayload 转换类型` 用例：输入对象去掉 `stabilize: true`，改为提供 `deflicker`/`stabilize` 源字段（见实现），并断言 `payload.deflicker.enabled` / `payload.stabilize.method` 正确。具体断言：

```javascript
test("buildStartPayload 带 deflicker/stabilize", () => {
  const payload = buildStartPayload({
    raw_folder: "/raw", camera_name: "Cam", lrt_export_folder: "/seq",
    resolution: "3840x2160", fps: "24", output_path: "/out",
    deflicker_enabled: true, deflicker_strength: "60", deflicker_time_radius: "3",
    stabilize_enabled: true, stabilize_result: "smooth",
    stabilize_smoothness: "70", stabilize_method: "subspace",
  });
  expect(payload.deflicker).toEqual({ enabled: true, strength: 60, time_radius: 3 });
  expect(payload.stabilize).toEqual({ enabled: true, result: "smooth", smoothness: 70, method: "subspace" });
});
```

Run → 失败。

- [ ] **Step 3: 前端 buildStartPayload 实现**

编辑 `timelapse-tool/electron/renderer/pipeline.js` 的 `buildStartPayload`：在返回对象里加：

```javascript
    deflicker: {
      enabled: Boolean(values.deflicker_enabled),
      strength: parseInt(values.deflicker_strength, 10),
      time_radius: parseInt(values.deflicker_time_radius, 10),
    },
    stabilize: {
      enabled: Boolean(values.stabilize_enabled),
      result: values.stabilize_result,
      smoothness: parseInt(values.stabilize_smoothness, 10),
      method: values.stabilize_method,
    },
```

Run 前端测试确认 PASS。

- [ ] **Step 4: HTML UI + readForm**

编辑 `timelapse-tool/electron/renderer/index.html`：把现有的 PR 增稳开关块：

```html
        <div class="field switch-field">
          <label for="stabilize">PR 增稳 (Warp Stabilizer)</label>
          <input id="stabilize" type="checkbox" />
        </div>
```

替换为「AE 去闪」与「AE 增稳」两个区：

```html
        <div class="field switch-field">
          <label for="deflicker_enabled">AE 去闪 (Deflicker)</label>
          <input id="deflicker_enabled" type="checkbox" />
        </div>
        <div id="deflicker-fields" class="hidden">
          <div class="row">
            <div class="field">
              <label>去闪强度 (0–100)</label>
              <input id="deflicker_strength" type="number" min="0" max="100" value="50" />
            </div>
            <div class="field">
              <label>时间半径 (1–10)</label>
              <input id="deflicker_time_radius" type="number" min="1" max="10" value="2" />
            </div>
          </div>
        </div>

        <div class="field switch-field">
          <label for="stabilize_enabled">AE 增稳 (变形稳定器)</label>
          <input id="stabilize_enabled" type="checkbox" />
        </div>
        <div id="stabilize-fields" class="hidden">
          <div class="row">
            <div class="field">
              <label>结果</label>
              <select id="stabilize_result">
                <option value="smooth">平滑运动</option>
                <option value="none">无运动</option>
              </select>
            </div>
            <div class="field">
              <label>平滑度 (0–100)</label>
              <input id="stabilize_smoothness" type="number" min="0" max="100" value="50" />
            </div>
          </div>
          <div class="field">
            <label>方法</label>
            <select id="stabilize_method">
              <option value="subspace">子空间变形</option>
              <option value="perspective">透视</option>
              <option value="pos_scale_rot">位置、缩放、旋转</option>
              <option value="position">位置</option>
            </select>
          </div>
        </div>
```

编辑 `pipeline.js` 的 `readForm()`：删除旧的 `stabilize: id("stabilize").checked,`，改为读取上述新控件：

```javascript
    deflicker_enabled: id("deflicker_enabled").checked,
    deflicker_strength: id("deflicker_strength").value,
    deflicker_time_radius: id("deflicker_time_radius").value,
    stabilize_enabled: id("stabilize_enabled").checked,
    stabilize_result: id("stabilize_result").value,
    stabilize_smoothness: id("stabilize_smoothness").value,
    stabilize_method: id("stabilize_method").value,
```

并在 `initPipeline` 内加两个开关的显隐联动（仿照导出模式）：

```javascript
  function syncToggle(cbId, fieldsId) {
    id(fieldsId).classList.toggle("hidden", !id(cbId).checked);
  }
  id("deflicker_enabled").addEventListener("change", () => syncToggle("deflicker_enabled", "deflicker-fields"));
  id("stabilize_enabled").addEventListener("change", () => syncToggle("stabilize_enabled", "stabilize-fields"));
  syncToggle("deflicker_enabled", "deflicker-fields");
  syncToggle("stabilize_enabled", "stabilize-fields");
```

- [ ] **Step 5: 跑前后端全量测试**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/ -q`（全 PASS）
Run: `cd timelapse-tool && export PATH="$HOME/.local/node/bin:$PATH" && npx jest --testEnvironment=jsdom`（全 PASS）

- [ ] **Step 6: 提交**

```bash
git add timelapse-tool/python/server.py timelapse-tool/python/tests/test_pipeline_api.py timelapse-tool/electron/renderer/index.html timelapse-tool/electron/renderer/pipeline.js timelapse-tool/tests/pipeline.test.js
git commit -m "feat: 表单 AE 去闪/增稳控件与配置流转"
```

---

## Task 6: 实机验证（需要真 AE + 真实序列）

**Files:** 无。**需在装有 After Effects 2026 的本机执行。**

- [ ] **Step 1: 用真实序列跑 AE 阶段**

启动 app，填真实 LRT 导出序列文件夹与输出路径，开启 AE 去闪与增稳，跑到 AE 阶段。
Expected: AE 工程里图层带上了 Deflicker 与变形稳定器，参数与表单一致；aerender 渲出 `_ae_intermediate.mov`。

- [ ] **Step 2: 校验效果与稳定器分析**

确认中间视频去闪、增稳生效。
> 重点排查：变形稳定器需要「分析」才生效。若脚本加了效果但没分析，画面不稳——此时需在 jsx 里触发分析（如 `app.executeCommand` 对应「变形稳定器 分析」命令 ID，或属性的分析方法），这是本任务的实机迭代点。记录现象并据此修 `ae.py`。

- [ ] **Step 3: 关闭开关回归**

去闪/增稳都关掉再跑一遍，确认 AE 只渲染不加效果，正常出片。

---

## Self-Review Notes

- **Spec 覆盖**：实现三次修订的「双重去闪（AE 第二遍）+ AE 增稳」；PR 不再增稳（PR 导出在 2e）。
- **类型一致性**：`deflicker`/`stabilize` dict 的键在 effects.py 校验、models、ae.py jsx、server、前端 buildStartPayload、UI 控件 id 之间保持一致（enabled/strength/time_radius；enabled/result/smoothness/method）。
- **实机依赖**：AE 两个效果的确切 matchName/属性名/枚举值，以及变形稳定器的分析触发，集中在 Task 3 内省 + Task 6 验证；effects.py 的常量是单一回填点。
- **可测性**：配置校验、jsx 是否包含 matchName 与参数值、配置流转，全部单测；真实 AE 行为隔离在 Task 3/6。
- **占位符**：Task 4 的属性 matchName 常量是 Task 3 的明确回填项，非遗留占位。
- **YAGNI**：去闪只暴露强度+时间半径，增稳只暴露结果/平滑度/方法（用户要求的可调项），不堆其它高级参数。
