# 工作流模板 (Workflow Templates) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户从内置工作流模板里选一套来跑，也能自建并保存自己的模板（阶段子集）。引擎已支持任意阶段列表，本计划加模板定义/校验/持久化/API/UI。

**Architecture:** 工作流 = `[BR, LRT, AE, PR]` 的有序子集（顺序天然固定，仅含/不含）。`pipeline/workflows.py` 定义内置模板、阶段注册表（名→Stage）、校验（含 PR 必含 AE）、从名字列表构建 Stage 列表。自定义模板持久化到 `workflows.json`。`/pipeline/start` 接收 `workflow`（阶段名列表），据此重建 runner 的阶段。前端加模板下拉 + 自建（勾选阶段+命名保存）。

**Tech Stack:** Python 3.9 + FastAPI，Electron 原生 JS + Jest。

---

## 关键规则

- 合法阶段名：`BR / LRT / AE / PR`，构建时按固定顺序 BR<LRT<AE<PR 排列（输入顺序不影响）。
- **含 PR 必含 AE**（PR 消费 AE 中间视频）。
- 工作流非空。
- 内置模板：
  - `全流程` = [BR, LRT, AE, PR]
  - `跳过BR` = [LRT, AE, PR]
  - `无PR` = [BR, LRT, AE]
  - `极简` = [LRT, AE]

---

## File Structure

```
timelapse-tool/python/
├── pipeline/workflows.py     # 新增：内置模板/注册表/校验/构建/自定义存储
├── workflows.json            # 新增：自定义模板持久化（随仓库给空集）
├── server.py                 # 修改：/workflows 端点；/pipeline/start 接收 workflow
└── tests/test_workflows.py、test_pipeline_api.py（改）
electron/renderer/
├── index.html                # 修改：工作流下拉 + 自建区
└── pipeline.js               # 修改：加载模板、自建保存、start 带 workflow
tests/pipeline.test.js（改）
```

测试约定同前。

---

## Task 1: workflows 模块（内置模板/注册表/校验/构建）

**Files:**
- Create: `timelapse-tool/python/pipeline/workflows.py`
- Test: `timelapse-tool/python/tests/test_workflows.py`

- [ ] **Step 1: 写失败的测试**

创建 `timelapse-tool/python/tests/test_workflows.py`：

```python
import pytest

from pipeline import workflows


def test_builtin_templates_present():
    assert workflows.BUILTIN["全流程"] == ["BR", "LRT", "AE", "PR"]
    assert workflows.BUILTIN["跳过BR"] == ["LRT", "AE", "PR"]
    assert workflows.BUILTIN["无PR"] == ["BR", "LRT", "AE"]
    assert workflows.BUILTIN["极简"] == ["LRT", "AE"]


def test_validate_ok():
    workflows.validate_workflow(["BR", "LRT", "AE", "PR"])
    workflows.validate_workflow(["LRT", "AE"])


def test_validate_empty_fails():
    with pytest.raises(ValueError, match="空"):
        workflows.validate_workflow([])


def test_validate_unknown_stage():
    with pytest.raises(ValueError, match="未知阶段"):
        workflows.validate_workflow(["LRT", "XX"])


def test_validate_pr_requires_ae():
    with pytest.raises(ValueError, match="PR"):
        workflows.validate_workflow(["LRT", "PR"])


def test_normalize_orders_canonically():
    assert workflows.normalize(["PR", "AE", "BR", "LRT"]) == ["BR", "LRT", "AE", "PR"]
    # 去重
    assert workflows.normalize(["AE", "AE", "LRT"]) == ["LRT", "AE"]


def test_build_stages_returns_stage_instances():
    stages = workflows.build_stages(["LRT", "AE"])
    assert [s.name for s in stages] == ["LRT", "AE"]
```

- [ ] **Step 2: 运行确认失败**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_workflows.py -v`
Expected: FAIL（无模块）。

- [ ] **Step 3: 写实现**

创建 `timelapse-tool/python/pipeline/workflows.py`：

```python
from pipeline.stages import BRStage, LRTStage, AEStage, PRStage

# 固定顺序与阶段注册表
CANONICAL_ORDER = ["BR", "LRT", "AE", "PR"]
_REGISTRY = {"BR": BRStage, "LRT": LRTStage, "AE": AEStage, "PR": PRStage}

BUILTIN = {
    "全流程": ["BR", "LRT", "AE", "PR"],
    "跳过BR": ["LRT", "AE", "PR"],
    "无PR": ["BR", "LRT", "AE"],
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
    if "PR" in chosen and "AE" not in chosen:
        raise ValueError("含 PR 的工作流必须包含 AE（PR 需要 AE 的中间视频）")


def build_stages(names):
    validate_workflow(names)
    return [_REGISTRY[n]() for n in normalize(names)]
```

- [ ] **Step 4: 运行确认通过**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_workflows.py -v`
Expected: 7 个 PASS。

- [ ] **Step 5: 提交**

```bash
git add timelapse-tool/python/pipeline/workflows.py timelapse-tool/python/tests/test_workflows.py
git commit -m "feat: 工作流模板（内置/校验/构建阶段）"
```

---

## Task 2: 自定义模板持久化（WorkflowStore）

**Files:**
- Create: `timelapse-tool/python/workflows.json`
- Modify: `timelapse-tool/python/pipeline/workflows.py`
- Test: `timelapse-tool/python/tests/test_workflows.py`

- [ ] **Step 1: 建空的 workflows.json**

创建 `timelapse-tool/python/workflows.json`：

```json
{ "workflows": {} }
```

- [ ] **Step 2: 写失败的测试**

在 `tests/test_workflows.py` 末尾追加：

```python
def test_store_save_and_list(tmp_path):
    p = tmp_path / "workflows.json"
    p.write_text('{"workflows": {}}')
    store = workflows.WorkflowStore(p)
    store.save("我的", ["LRT", "AE", "PR"])
    reloaded = workflows.WorkflowStore(p)
    assert reloaded.custom()["我的"] == ["LRT", "AE", "PR"]


def test_store_save_validates(tmp_path):
    p = tmp_path / "workflows.json"
    p.write_text('{"workflows": {}}')
    store = workflows.WorkflowStore(p)
    with pytest.raises(ValueError, match="PR"):
        store.save("坏的", ["LRT", "PR"])


def test_store_all_merges_builtin_and_custom(tmp_path):
    p = tmp_path / "workflows.json"
    p.write_text('{"workflows": {"我的": ["LRT", "AE"]}}')
    store = workflows.WorkflowStore(p)
    allw = store.all()
    assert "全流程" in allw and "我的" in allw
```

- [ ] **Step 3: 写实现**

在 `pipeline/workflows.py` 末尾追加：

```python
import json
from pathlib import Path


class WorkflowStore:
    """自定义工作流的读写；all() 合并内置 + 自定义（自定义会覆盖同名内置）。"""

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
```

- [ ] **Step 4: 运行确认通过**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_workflows.py -v`
Expected: 全部 PASS（10 个）。

- [ ] **Step 5: 提交**

```bash
git add timelapse-tool/python/workflows.json timelapse-tool/python/pipeline/workflows.py timelapse-tool/python/tests/test_workflows.py
git commit -m "feat: 自定义工作流持久化 WorkflowStore"
```

---

## Task 3: API —— /workflows 与 start 接收 workflow

**Files:**
- Modify: `timelapse-tool/python/server.py`
- Modify: `timelapse-tool/python/tests/test_pipeline_api.py`

- [ ] **Step 1: 写失败的测试**

在 `tests/test_pipeline_api.py` 末尾追加：

```python
def test_get_workflows_lists_builtin():
    r = client.get("/workflows")
    assert r.status_code == 200
    wf = r.json()["workflows"]
    assert wf["全流程"] == ["BR", "LRT", "AE", "PR"]
    assert "极简" in wf


def test_start_with_custom_workflow_runs_only_those_stages(tmp_path, monkeypatch):
    from pipeline import ae, pr
    monkeypatch.setattr(ae, "render_sequence",
                        lambda seq_folder, output_dir, fps, emit, **kw: emit("AE"))
    monkeypatch.setattr(pr, "render_final",
                        lambda intermediate_video, output_dir, export, emit, **kw: emit("PR"))
    raw = tmp_path / "raw"; raw.mkdir()
    lrt = tmp_path / "seq"; lrt.mkdir(); (lrt / "0001.tif").write_text("i")
    out = tmp_path / "out"; out.mkdir()
    body = dict(
        raw_folder=str(raw), camera_name="Sony A7R IV",
        lrt_export_folder=str(lrt), stabilize={"enabled": False}, resolution=[3840, 2160],
        fps=24, export={"codec": "ProRes", "container": "MOV", "prores_profile": "422 HQ"},
        output_path=str(out), workflow=["LRT", "AE"],
    )
    r = client.post("/pipeline/start", json=body)
    assert r.status_code == 200
    # 极简工作流第一个阶段是 LRT（手动），停在 LRT
    assert r.json()["current_stage"] == "LRT"
    r2 = client.post("/pipeline/continue")
    assert r2.json()["state"] == "done"  # 只剩 AE，跑完即完成


def test_save_custom_workflow():
    r = client.post("/workflows", json={"name": "测试流", "stages": ["LRT", "AE", "PR"]})
    assert r.status_code == 201
    assert "测试流" in client.get("/workflows").json()["workflows"]
```

- [ ] **Step 2: 运行确认失败**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_pipeline_api.py -v`
Expected: FAIL（无 /workflows；StartBody 无 workflow）。

- [ ] **Step 3: 写实现**

编辑 `timelapse-tool/python/server.py`：

顶部 import 区加：

```python
from pipeline import workflows
```

在 `_runner` 定义附近加 workflow 存储：

```python
_WORKFLOWS_PATH = Path(__file__).parent / "workflows.json"
_workflow_store = workflows.WorkflowStore(_WORKFLOWS_PATH)
```

`StartBody` 加字段：

```python
    workflow: Optional[list] = None
```

`pipeline_start` 里，构造 `PipelineConfig` 之后、`_runner.start` 之前，按 workflow 重建 runner 阶段：

```python
@app.post("/pipeline/start")
def pipeline_start(body: StartBody):
    global _runner
    data = body.dict()
    workflow_names = data.pop("workflow", None)
    preset = data.pop("preset", None)
    if data.get("export") is None and preset:
        from pipeline.export_formats import expand_preset
        try:
            data["export"] = expand_preset(preset)
        except KeyError:
            raise HTTPException(status_code=400, detail=f"未知导出预设: {preset}")
    config = PipelineConfig(**data)
    try:
        if workflow_names:
            stages = workflows.build_stages(workflow_names)
        else:
            stages = default_stages()
        _runner = PipelineRunner(stages=stages, emit=_progress_log.append)
        _runner.start(config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _runner.status()
```

> 注意：`pipeline_continue` / `pipeline_status` 仍引用模块级 `_runner`，因此 start 里用 `global _runner` 重新赋值后它们用的是同一个新 runner。

新增端点（`if __name__` 之前）：

```python
@app.get("/workflows")
def get_workflows():
    return {"workflows": _workflow_store.all()}


class SaveWorkflowBody(BaseModel):
    name: str
    stages: list


@app.post("/workflows", status_code=201)
def save_workflow(body: SaveWorkflowBody):
    try:
        _workflow_store.save(body.name, body.stages)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/ -v`
Expected: 全部 PASS。
> `test_save_custom_workflow` 会写真实 `workflows.json`。提交前 `cd /Users/feitong/photo-app && git checkout timelapse-tool/python/workflows.json` 还原（或像相机测试那样用临时文件隔离——优先隔离：在测试里 monkeypatch `server._workflow_store` 为临时 WorkflowStore）。**实现时优先用 monkeypatch 隔离**，避免污染。

- [ ] **Step 5: 提交**

```bash
git add timelapse-tool/python/server.py timelapse-tool/python/tests/test_pipeline_api.py
git commit -m "feat: /workflows 端点与 start 按工作流重建阶段"
```

---

## Task 4: 前端 —— 工作流下拉 + 自建保存

**Files:**
- Modify: `timelapse-tool/electron/renderer/index.html`
- Modify: `timelapse-tool/electron/renderer/pipeline.js`
- Modify: `timelapse-tool/tests/pipeline.test.js`

- [ ] **Step 1: 纯函数测试**

在 `timelapse-tool/tests/pipeline.test.js` 末尾追加（并把顶部 require 加上 `collectWorkflowStages`）：

```javascript
test("collectWorkflowStages 按勾选返回固定顺序子集", () => {
  const checked = { BR: false, LRT: true, AE: true, PR: true };
  expect(collectWorkflowStages(checked)).toEqual(["LRT", "AE", "PR"]);
});

test("collectWorkflowStages 全不选返回空", () => {
  expect(collectWorkflowStages({ BR: false, LRT: false, AE: false, PR: false })).toEqual([]);
});
```

require 行改为：

```javascript
const { buildStartPayload, stageBoardModel, canContinue, continueLabel, buildExportConfig, collectWorkflowStages } = require("../electron/renderer/pipeline.js");
```

- [ ] **Step 2: 运行确认失败**

Run: `cd timelapse-tool && export PATH="$HOME/.local/node/bin:$PATH" && npx jest --testEnvironment=jsdom tests/pipeline.test.js`
Expected: FAIL（collectWorkflowStages 未定义）。

- [ ] **Step 3: pipeline.js 加纯函数 + 导出**

在 `pipeline.js` 的 `canContinue` 之后加：

```javascript
const WORKFLOW_ORDER = ["BR", "LRT", "AE", "PR"];

// 把阶段勾选状态转成固定顺序的阶段名数组
function collectWorkflowStages(checked) {
  return WORKFLOW_ORDER.filter((name) => checked[name]);
}
```

`module.exports` 加上 `collectWorkflowStages`。

- [ ] **Step 4: 运行确认通过**

Run: `cd timelapse-tool && export PATH="$HOME/.local/node/bin:$PATH" && npx jest --testEnvironment=jsdom tests/pipeline.test.js`
Expected: PASS。

- [ ] **Step 5: HTML 加工作流区**

在 `index.html` 的 `<h1>延时流水线</h1>` 之后、第一个字段之前插入：

```html
        <div class="field">
          <label>工作流模板</label>
          <select id="workflow_select"></select>
        </div>
        <details class="workflow-builder">
          <summary>自建工作流</summary>
          <div class="wf-checks">
            <label><input type="checkbox" class="wf-stage" value="BR" checked /> BR</label>
            <label><input type="checkbox" class="wf-stage" value="LRT" checked /> LRT</label>
            <label><input type="checkbox" class="wf-stage" value="AE" checked /> AE</label>
            <label><input type="checkbox" class="wf-stage" value="PR" checked /> PR</label>
          </div>
          <div class="path-input">
            <input id="wf_name" type="text" placeholder="模板名" />
            <button type="button" id="wf_save" class="btn-browse">保存模板</button>
          </div>
          <div id="wf-error" class="error-text"></div>
        </details>
```

- [ ] **Step 6: pipeline.js 接线**

在 `initPipeline` 内（加载导出预设之后）加入：加载工作流到下拉、保存自建、把所选工作流写进 start body。

```javascript
  // 加载工作流模板
  let workflowMap = {};
  async function loadWorkflows(selectName) {
    const data = await fetch(httpBase + "/workflows").then((r) => r.json());
    workflowMap = data.workflows;
    const sel = id("workflow_select");
    sel.innerHTML = "";
    for (const name of Object.keys(workflowMap)) {
      const opt = document.createElement("option");
      opt.value = name; opt.textContent = name + "（" + workflowMap[name].join("-") + "）";
      sel.appendChild(opt);
    }
    if (selectName) sel.value = selectName;
  }
  await loadWorkflows("全流程");

  id("wf_save").addEventListener("click", async () => {
    const checked = {};
    document.querySelectorAll(".wf-stage").forEach((c) => { checked[c.value] = c.checked; });
    const stages = collectWorkflowStages(checked);
    const name = id("wf_name").value.trim();
    const errEl2 = id("wf-error");
    errEl2.textContent = "";
    if (!name) { errEl2.textContent = "请填模板名"; return; }
    const res = await fetch(httpBase + "/workflows", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name, stages: stages }),
    });
    if (!res.ok) {
      const e = await res.json().catch(() => ({}));
      errEl2.textContent = "保存失败：" + (e.detail || res.status);
      return;
    }
    await loadWorkflows(name);
  });
```

在 `buildStartBody()` 里，给 payload 加所选工作流：

```javascript
    payload.workflow = workflowMap[id("workflow_select").value] || null;
```

- [ ] **Step 7: 前后端全量测试**

Run 后端 `tests/ -q`、前端 `npx jest --testEnvironment=jsdom`，均 PASS。

- [ ] **Step 8: 提交**

```bash
git add timelapse-tool/electron/renderer/index.html timelapse-tool/electron/renderer/pipeline.js timelapse-tool/tests/pipeline.test.js
git commit -m "feat: 前端工作流模板下拉与自建保存"
```

---

## Task 5: 实机验证

- [ ] 重启 app：顶部出现「工作流模板」下拉（全流程/跳过BR/无PR/极简）；「自建工作流」可勾选阶段+命名保存，保存后出现在下拉里。
- [ ] 选「极简 LRT-AE」跑：只经过 LRT（手动）→ AE，看板只点亮 LRT/AE，跑到 done。
- [ ] 选「无PR BR-LRT-AE」跑：BR→LRT→AE，无 PR。

---

## Self-Review Notes

- **Spec 覆盖**：实现「工作流模板（B）」——内置 4 套 + 自建保存；含 PR 必含 AE 校验；阶段固定顺序子集。
- **类型一致性**：阶段名 BR/LRT/AE/PR 在 workflows 注册表、stages、前端 WORKFLOW_ORDER 一致；`workflow` 字段在 StartBody、build_stages、前端 buildStartBody 一致。
- **引擎复用**：PipelineRunner 已支持任意 stages 列表；start 时按 workflow 重建 runner（global 赋值，continue/status 仍指向同一个）。
- **隔离**：自定义模板测试用 monkeypatch 临时 WorkflowStore，避免污染仓库 workflows.json（与相机测试同策略）。
- **YAGNI**：工作流只做"子集（固定顺序）"，不做任意乱序/任意自定义步骤（那是 C，未选）。
