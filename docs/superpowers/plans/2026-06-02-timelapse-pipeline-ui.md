# 延时流水线 UI 面板 (Pipeline UI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把延时流水线后端接口接到前端「延时流水线」Tab，做出极简·液态玻璃·扁平化风格的完整面板：参数表单（机型→分辨率联动）、开始/继续按钮、阶段进度看板。

**Architecture:** 复用骨架已有的 Electron 渲染进程。新增一套液态玻璃风格的全局 CSS 变量与组件类。「延时流水线」面板里渲染一个表单（从 `/cameras` 拉机型、选机型后调 `/cameras/{name}/resolutions` 填充分辨率），点「开始处理」POST `/pipeline/start`，进入等待态后显示「我已在 LRT 完成，继续」按钮 POST `/pipeline/continue`，全程轮询 `/pipeline/status` 更新四阶段进度看板。纯函数（构建表单数据、映射状态到看板）抽出来单测，DOM/网络部分在浏览器实际运行。

**Tech Stack:** Electron 渲染进程（原生 JS + HTML + CSS），Jest + jsdom 测试，后端为 2a 已实现的 FastAPI。

---

## File Structure

```
timelapse-tool/electron/renderer/
├── index.html          # 修改：延时流水线面板填入真实表单 + 进度看板结构
├── style.css           # 修改：新增液态玻璃设计系统（变量+组件类）
├── app.js              # 既有：保留 switchTab/statusLabel/pollHealth + WS
└── pipeline.js         # 新增：流水线面板逻辑（纯函数 + DOM 绑定）
tests/
└── pipeline.test.js    # 新增：纯函数单测
```

**职责边界：**
- `pipeline.js`：流水线面板的全部逻辑。纯函数（`buildStartPayload`、`stageBoardModel`、`canContinue`）可单测；DOM 初始化函数 `initPipeline()` 在浏览器环境调用。
- `style.css`：新增液态玻璃设计 token 与组件类，不破坏骨架已有的 `.tabs/.tab/.panel/.status`。
- `app.js`：仅在浏览器环境多调一次 `initPipeline()`。

约定：Jest 命令 `cd timelapse-tool && export PATH="$HOME/.local/node/bin:$PATH" && npx jest --testEnvironment=jsdom <file>`。

---

## Task 1: 液态玻璃设计系统（CSS）

**Files:**
- Modify: `timelapse-tool/electron/renderer/style.css`

无独立单测（纯样式），通过 Task 5 的实机验证确认观感。

- [ ] **Step 1: 在 style.css 顶部加入设计 token 与玻璃组件类**

在 `timelapse-tool/electron/renderer/style.css` 文件**开头**插入（保留文件原有规则在其后）：

```css
:root {
  --bg-grad-1: #e8eef7;
  --bg-grad-2: #f3e9f5;
  --glass-bg: rgba(255, 255, 255, 0.45);
  --glass-bg-strong: rgba(255, 255, 255, 0.62);
  --glass-border: rgba(255, 255, 255, 0.6);
  --glass-blur: 20px;
  --accent: #007aff;
  --accent-soft: rgba(0, 122, 255, 0.12);
  --text: #1c1c1e;
  --text-dim: #6b6b70;
  --radius: 16px;
  --radius-sm: 10px;
}

body {
  background: linear-gradient(135deg, var(--bg-grad-1), var(--bg-grad-2));
  background-attachment: fixed;
  color: var(--text);
}

/* 液态玻璃卡片 */
.glass {
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur)) saturate(160%);
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(160%);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius);
}

/* 扁平玻璃输入 */
.field { display: flex; flex-direction: column; gap: 6px; margin-bottom: 16px; }
.field label { font-size: 12px; color: var(--text-dim); letter-spacing: 0.02em; }
.field input, .field select {
  appearance: none;
  background: var(--glass-bg-strong);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
  font-size: 14px;
  color: var(--text);
  outline: none;
  transition: border-color 0.15s, background 0.15s;
}
.field input:focus, .field select:focus { border-color: var(--accent); }

.row { display: flex; gap: 14px; }
.row > .field { flex: 1; }

.switch-field { display: flex; align-items: center; justify-content: space-between; }

/* 扁平玻璃按钮 */
.btn {
  appearance: none;
  border: none;
  border-radius: var(--radius-sm);
  padding: 12px 20px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: transform 0.08s, background 0.15s, opacity 0.15s;
}
.btn:active { transform: scale(0.98); }
.btn-primary { background: var(--accent); color: #fff; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-ghost { background: var(--accent-soft); color: var(--accent); }

/* 阶段进度看板 */
.board { display: flex; gap: 10px; margin-top: 20px; }
.stage {
  flex: 1;
  padding: 14px;
  text-align: center;
  border-radius: var(--radius-sm);
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--glass-border);
  font-size: 13px;
  color: var(--text-dim);
  transition: all 0.2s;
}
.stage .stage-name { font-weight: 600; color: var(--text); font-size: 15px; }
.stage .stage-hint { font-size: 11px; margin-top: 4px; }
.stage.done { background: rgba(52, 199, 89, 0.16); border-color: rgba(52,199,89,0.4); }
.stage.active { background: var(--accent-soft); border-color: var(--accent); }
.stage.failed { background: rgba(255, 59, 48, 0.16); border-color: rgba(255,59,48,0.45); }

.pipeline-form { padding: 22px; max-width: 560px; }
.pipeline-actions { display: flex; gap: 12px; margin-top: 8px; }
.hidden { display: none !important; }
```

- [ ] **Step 2: 提交**

```bash
git add timelapse-tool/electron/renderer/style.css
git commit -m "feat: 液态玻璃扁平化设计系统"
```

---

## Task 2: 流水线面板 HTML 结构

**Files:**
- Modify: `timelapse-tool/electron/renderer/index.html`

- [ ] **Step 1: 替换延时流水线面板占位内容**

在 `timelapse-tool/electron/renderer/index.html` 中，把：

```html
    <section id="pipeline" class="panel active">
      <h1>延时流水线</h1>
      <p>（占位 — 由后续计划实现）</p>
    </section>
```

整体替换为：

```html
    <section id="pipeline" class="panel active">
      <div class="glass pipeline-form">
        <h1>延时流水线</h1>
        <div class="field">
          <label>RAW 文件夹</label>
          <input id="raw_folder" type="text" placeholder="/path/to/raw" />
        </div>
        <div class="row">
          <div class="field">
            <label>相机机型</label>
            <select id="camera_name"></select>
          </div>
          <div class="field">
            <label>分辨率</label>
            <select id="resolution"></select>
          </div>
        </div>
        <div class="field">
          <label>Camera Raw 预设 (.xmp)</label>
          <input id="acr_preset_path" type="text" placeholder="/path/to/preset.xmp" />
        </div>
        <div class="field">
          <label>LRT 导出序列文件夹</label>
          <input id="lrt_export_folder" type="text" placeholder="LRT 导出图像序列的目标文件夹" />
        </div>
        <div class="row">
          <div class="field">
            <label>帧率</label>
            <select id="fps">
              <option value="24">24</option>
              <option value="25">25</option>
              <option value="30">30</option>
              <option value="60">60</option>
            </select>
          </div>
          <div class="field">
            <label>编码</label>
            <select id="codec">
              <option value="ProRes">ProRes</option>
              <option value="H.264">H.264</option>
              <option value="H.265">H.265</option>
            </select>
          </div>
        </div>
        <div class="field">
          <label>输出路径</label>
          <input id="output_path" type="text" placeholder="/path/to/output" />
        </div>
        <div class="field switch-field">
          <label for="stabilize">PR 增稳 (Warp Stabilizer)</label>
          <input id="stabilize" type="checkbox" />
        </div>
        <div class="pipeline-actions">
          <button id="btn-start" class="btn btn-primary">开始处理</button>
          <button id="btn-continue" class="btn btn-ghost hidden">我已在 LRT 完成，继续</button>
        </div>
        <div id="pipeline-error" class="stage-hint" style="color:#ff3b30;margin-top:10px;"></div>
      </div>

      <div class="board" id="stage-board">
        <div class="stage" data-stage="BR"><div class="stage-name">BR</div><div class="stage-hint">套用预设</div></div>
        <div class="stage" data-stage="LRT"><div class="stage-name">LRT</div><div class="stage-hint">手动操作</div></div>
        <div class="stage" data-stage="AE"><div class="stage-name">AE</div><div class="stage-hint">渲染序列</div></div>
        <div class="stage" data-stage="PR"><div class="stage-name">PR</div><div class="stage-hint">导出成片</div></div>
      </div>
    </section>
```

- [ ] **Step 2: 在 index.html 的 `<script src="app.js"></script>` 之前加载 pipeline.js**

把：

```html
  <script src="app.js"></script>
```

改为：

```html
  <script src="pipeline.js"></script>
  <script src="app.js"></script>
```

- [ ] **Step 3: 提交**

```bash
git add timelapse-tool/electron/renderer/index.html
git commit -m "feat: 流水线面板 HTML 表单与进度看板结构"
```

---

## Task 3: 流水线纯函数逻辑（TDD）

**Files:**
- Create: `timelapse-tool/electron/renderer/pipeline.js`
- Test: `timelapse-tool/tests/pipeline.test.js`

先实现可单测的纯函数：
- `buildStartPayload(values)`：把表单原始值（字符串）转成后端要的 payload（`fps` 转 int，`resolution` 从 "宽x高" 字符串转 `[w,h]`，`stabilize` 转 bool）。
- `stageBoardModel(status)`：把 `/pipeline/status` 返回映射成四阶段的 class（done/active/failed/空）。
- `canContinue(status)`：状态是否为 `waiting_for_user`。

- [ ] **Step 1: 写失败的测试**

创建 `timelapse-tool/tests/pipeline.test.js`：

```javascript
const { buildStartPayload, stageBoardModel, canContinue } = require("../electron/renderer/pipeline.js");

test("buildStartPayload 转换类型", () => {
  const payload = buildStartPayload({
    raw_folder: "/raw",
    camera_name: "Sony A7R IV",
    acr_preset_path: "/p.xmp",
    lrt_export_folder: "/seq",
    stabilize: true,
    resolution: "3840x2160",
    fps: "24",
    codec: "ProRes",
    output_path: "/out",
  });
  expect(payload.fps).toBe(24);
  expect(payload.resolution).toEqual([3840, 2160]);
  expect(payload.stabilize).toBe(true);
  expect(payload.raw_folder).toBe("/raw");
});

test("stageBoardModel 标记已完成/进行中阶段", () => {
  const model = stageBoardModel({
    state: "waiting_for_user",
    current_stage: "LRT",
    completed: ["BR"],
    error: null,
  });
  expect(model.BR).toBe("done");
  expect(model.LRT).toBe("active");
  expect(model.AE).toBe("");
});

test("stageBoardModel 失败态标记失败阶段", () => {
  const model = stageBoardModel({
    state: "failed",
    current_stage: "AE",
    completed: ["BR"],
    error: "炸了",
  });
  expect(model.BR).toBe("done");
  expect(model.AE).toBe("failed");
});

test("stageBoardModel 完成态全部 done", () => {
  const model = stageBoardModel({
    state: "done",
    current_stage: "PR",
    completed: ["BR", "AE", "PR"],
    error: null,
  });
  expect(model.BR).toBe("done");
  expect(model.PR).toBe("done");
});

test("canContinue 仅在等待态为真", () => {
  expect(canContinue({ state: "waiting_for_user" })).toBe(true);
  expect(canContinue({ state: "running" })).toBe(false);
  expect(canContinue({ state: "done" })).toBe(false);
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd timelapse-tool && export PATH="$HOME/.local/node/bin:$PATH" && npx jest --testEnvironment=jsdom tests/pipeline.test.js`
Expected: FAIL，`Cannot find module '../electron/renderer/pipeline.js'`。

- [ ] **Step 3: 写最小实现**

创建 `timelapse-tool/electron/renderer/pipeline.js`：

```javascript
// 四个阶段固定顺序
const STAGES = ["BR", "LRT", "AE", "PR"];

// 把表单原始值转成后端 /pipeline/start 需要的 payload
function buildStartPayload(values) {
  const [w, h] = String(values.resolution).split("x").map((n) => parseInt(n, 10));
  return {
    raw_folder: values.raw_folder,
    camera_name: values.camera_name,
    acr_preset_path: values.acr_preset_path,
    lrt_export_folder: values.lrt_export_folder,
    stabilize: Boolean(values.stabilize),
    resolution: [w, h],
    fps: parseInt(values.fps, 10),
    codec: values.codec,
    output_path: values.output_path,
  };
}

// 把 /pipeline/status 映射成每个阶段的 CSS class
function stageBoardModel(status) {
  const completed = new Set(status.completed || []);
  const model = {};
  for (const name of STAGES) {
    if (status.state === "failed" && status.current_stage === name) {
      model[name] = "failed";
    } else if (status.state === "done") {
      model[name] = "done";
    } else if (completed.has(name)) {
      model[name] = "done";
    } else if (status.current_stage === name && status.state !== "failed") {
      model[name] = "active";
    } else {
      model[name] = "";
    }
  }
  return model;
}

function canContinue(status) {
  return status.state === "waiting_for_user";
}

if (typeof module !== "undefined") {
  module.exports = { buildStartPayload, stageBoardModel, canContinue, STAGES };
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd timelapse-tool && export PATH="$HOME/.local/node/bin:$PATH" && npx jest --testEnvironment=jsdom tests/pipeline.test.js`
Expected: 5 个测试全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add timelapse-tool/electron/renderer/pipeline.js timelapse-tool/tests/pipeline.test.js
git commit -m "feat: 流水线面板纯函数逻辑（payload/看板/继续判定）"
```

---

## Task 4: 流水线面板 DOM 绑定（浏览器逻辑）

**Files:**
- Modify: `timelapse-tool/electron/renderer/pipeline.js`
- Modify: `timelapse-tool/electron/renderer/app.js`

这部分是浏览器副作用逻辑（网络 + DOM），不写单测，靠 Task 5 实机验证。

- [ ] **Step 1: 在 pipeline.js 末尾（module.exports 之前）加入 DOM 初始化**

在 `timelapse-tool/electron/renderer/pipeline.js` 中，把结尾的：

```javascript
if (typeof module !== "undefined") {
  module.exports = { buildStartPayload, stageBoardModel, canContinue, STAGES };
}
```

替换为：

```javascript
// 应用阶段看板模型到 DOM
function renderBoard(status) {
  const model = stageBoardModel(status);
  for (const name of STAGES) {
    const el = document.querySelector(`.stage[data-stage="${name}"]`);
    if (el) el.className = "stage" + (model[name] ? " " + model[name] : "");
  }
}

function readForm() {
  const id = (x) => document.getElementById(x);
  return {
    raw_folder: id("raw_folder").value,
    camera_name: id("camera_name").value,
    acr_preset_path: id("acr_preset_path").value,
    lrt_export_folder: id("lrt_export_folder").value,
    stabilize: id("stabilize").checked,
    resolution: id("resolution").value,
    fps: id("fps").value,
    codec: id("codec").value,
    output_path: id("output_path").value,
  };
}

async function initPipeline(httpBase) {
  const id = (x) => document.getElementById(x);
  const errEl = id("pipeline-error");
  const cameraSel = id("camera_name");
  const resSel = id("resolution");

  // 拉机型
  try {
    const cams = await fetch(httpBase + "/cameras").then((r) => r.json());
    cameraSel.innerHTML = "";
    for (const cam of cams.cameras) {
      const opt = document.createElement("option");
      opt.value = cam.name;
      opt.textContent = cam.name;
      cameraSel.appendChild(opt);
    }
  } catch (_) {
    errEl.textContent = "无法加载相机列表";
    return;
  }

  // 机型→分辨率联动
  async function loadResolutions() {
    const name = cameraSel.value;
    const data = await fetch(httpBase + "/cameras/" + encodeURIComponent(name) + "/resolutions").then((r) => r.json());
    resSel.innerHTML = "";
    for (const o of data.options) {
      const opt = document.createElement("option");
      opt.value = o.size[0] + "x" + o.size[1];
      opt.textContent = o.label + " (" + o.size[0] + "×" + o.size[1] + ")";
      resSel.appendChild(opt);
    }
  }
  cameraSel.addEventListener("change", loadResolutions);
  await loadResolutions();

  async function refreshStatus() {
    const status = await fetch(httpBase + "/pipeline/status").then((r) => r.json());
    renderBoard(status);
    id("btn-continue").classList.toggle("hidden", !canContinue(status));
    if (status.state === "failed") errEl.textContent = "失败：" + (status.error || "");
    return status;
  }

  id("btn-start").addEventListener("click", async () => {
    errEl.textContent = "";
    const res = await fetch(httpBase + "/pipeline/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildStartPayload(readForm())),
    });
    if (!res.ok) {
      const e = await res.json().catch(() => ({}));
      errEl.textContent = "启动失败：" + (e.detail || res.status);
      return;
    }
    await refreshStatus();
  });

  id("btn-continue").addEventListener("click", async () => {
    errEl.textContent = "";
    const res = await fetch(httpBase + "/pipeline/continue", { method: "POST" });
    if (!res.ok) {
      const e = await res.json().catch(() => ({}));
      errEl.textContent = "继续失败：" + (e.detail || res.status);
      return;
    }
    await refreshStatus();
  });

  await refreshStatus();
}

if (typeof window !== "undefined") {
  window.initPipeline = initPipeline;
}

if (typeof module !== "undefined") {
  module.exports = { buildStartPayload, stageBoardModel, canContinue, STAGES };
}
```

- [ ] **Step 2: 在 app.js 的浏览器分支里调用 initPipeline**

在 `timelapse-tool/electron/renderer/app.js` 中找到浏览器分支（`if (typeof window !== "undefined" && window.backend) {` 块），在该块内 `pollHealth(...)` 调用之后、块结束 `}` 之前，加入：

```javascript
  if (typeof window.initPipeline === "function") {
    window.initPipeline(window.backend.httpBase);
  }
```

- [ ] **Step 3: 回归既有前端单测**

Run: `cd timelapse-tool && export PATH="$HOME/.local/node/bin:$PATH" && npx jest --testEnvironment=jsdom`
Expected: 既有 smoke.test.js（4）+ pipeline.test.js（5）全部 PASS，共 9 个。

- [ ] **Step 4: 提交**

```bash
git add timelapse-tool/electron/renderer/pipeline.js timelapse-tool/electron/renderer/app.js
git commit -m "feat: 流水线面板 DOM 绑定与状态轮询"
```

---

## Task 5: 实机端到端验证

**Files:** 无（验证任务）

- [ ] **Step 1: 启动应用**

Run: `cd timelapse-tool && export PATH="$HOME/.local/node/bin:$PATH" && npm start`
Expected: 窗口打开，「延时流水线」面板显示液态玻璃风格表单；相机下拉已填充（Sony A7R IV 等），选不同机型时分辨率下拉随之变化；底部四阶段看板（BR/LRT/AE/PR）可见。

- [ ] **Step 2: 准备测试素材并跑一遍流水线（用桩阶段）**

在 Finder 或终端建几个临时文件夹用于填表（真实跑桩流水线）：

```bash
mkdir -p /tmp/tl_demo/raw /tmp/tl_demo/seq /tmp/tl_demo/out && touch /tmp/tl_demo/preset.xmp && touch /tmp/tl_demo/seq/0001.tif
```

在表单里填：RAW 文件夹 `/tmp/tl_demo/raw`、ACR 预设 `/tmp/tl_demo/preset.xmp`、LRT 导出文件夹 `/tmp/tl_demo/seq`、输出路径 `/tmp/tl_demo/out`，其余用默认。
点「开始处理」。
Expected: BR 阶段变绿（done），LRT 阶段高亮（active），出现「我已在 LRT 完成，继续」按钮。

- [ ] **Step 3: 点继续完成流水线**

点「我已在 LRT 完成，继续」。
Expected: AE、PR 阶段依次变绿，四个阶段最终全绿（桩流水线完成）。

- [ ] **Step 4: 验证校验失败提示**

把 LRT 文件夹的图片删掉（`rm /tmp/tl_demo/seq/0001.tif`），重启 app 重新走到等待态后点继续。
Expected: 红色错误提示「LRT 导出文件夹里没有图像序列…」。
（验证完清理：`rm -rf /tmp/tl_demo`）

---

## Self-Review Notes

- **Spec 覆盖**：实现 spec 4.1 的前端表单（修订版字段：RAW 文件夹/机型/ACR 预设/LRT 导出文件夹/增稳/分辨率/帧率/编码/输出）、4.2 机型→分辨率联动、第 5 节状态机的前端进度看板。照片筛选 Tab 不在本计划。
- **类型一致性**：`buildStartPayload` 输出字段与 2a 的 `StartBody`/`PipelineConfig` 字段名完全一致（raw_folder/camera_name/acr_preset_path/lrt_export_folder/stabilize/resolution/fps/codec/output_path）。`stageBoardModel` 的阶段名 BR/LRT/AE/PR 与 `default_stages()` 一致。状态字符串 waiting_for_user/done/failed 与 `PipelineState` 一致。
- **占位符扫描**：无 TODO/占位；DOM 绑定是完整实现。
- **设计风格**：遵循用户要求的极简·液态玻璃·扁平化（backdrop-filter 磨砂、柔和圆角、克制留白、扁平无重阴影、单一强调色 #007aff）。
- **测试边界**：纯函数（payload/看板/继续判定）单测覆盖；DOM+网络逻辑靠 Task 5 实机验证（jsdom 下不易测 fetch 链路，YAGNI 不强测）。
- **不破坏既有**：style.css 新增规则不覆盖骨架的 .tabs/.tab/.panel/.status；app.js 仅新增一次 initPipeline 调用。
