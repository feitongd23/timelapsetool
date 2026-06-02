# 应用骨架 (App Skeleton) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建一个能跑起来的 Electron 双 Tab 桌面应用外壳，与本地 FastAPI Python 后端通过 HTTP + WebSocket 打通通信。

**Architecture:** Electron 主进程启动后自动拉起 Python FastAPI 子进程；渲染进程加载双 Tab UI（延时流水线 / 照片筛选，均为占位）；前端通过 HTTP 调后端 REST、通过 WebSocket 接收后端推送的进度消息。本计划只建外壳和通信骨架，不实现具体业务逻辑。

**Tech Stack:** Electron, Node.js, Python 3.9, FastAPI, uvicorn, websockets, pytest, Jest

---

## File Structure

```
timelapse-tool/
├── package.json              # Electron/Node 依赖与启动脚本
├── electron/
│   ├── main.js               # Electron 主进程：建窗、拉起 Python 后端
│   ├── preload.js            # 安全暴露 IPC/HTTP 配置给渲染进程
│   └── renderer/
│       ├── index.html        # 双 Tab 外壳页面
│       ├── app.js            # Tab 切换 + 后端连通性检查 + WS 连接
│       └── style.css         # 基础样式
├── python/
│   ├── requirements.txt      # Python 依赖
│   ├── server.py             # FastAPI 入口：health + WebSocket 端点
│   └── tests/
│       └── test_server.py    # 后端 API 测试
├── tests/
│   └── smoke.test.js         # 前端冒烟测试（后端连通性逻辑）
└── .gitignore
```

**职责边界：**
- `electron/main.js`：仅负责窗口生命周期和 Python 子进程管理，不含业务逻辑。
- `python/server.py`：仅提供 health 检查和 WebSocket 进度通道骨架，业务路由后续计划再加。
- `electron/renderer/app.js`：仅负责 UI 外壳（Tab 切换）和与后端建立连接，不含业务逻辑。

---

## Task 0: 安装 Node.js 与初始化项目目录

**Files:**
- Create: `timelapse-tool/.gitignore`

- [ ] **Step 1: 检查 Node 是否已安装**

Run: `node -v && npm -v`
如果输出版本号（如 `v20.x.x`），跳到 Step 3。如果报 `command not found`，执行 Step 2。

- [ ] **Step 2: 通过 Homebrew 安装 Node.js**

Run: `brew install node`
Expected: 安装完成后 `node -v` 输出 v18 或更高版本。
（若无 Homebrew：先 `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`）

- [ ] **Step 3: 创建项目目录与 .gitignore**

```bash
mkdir -p timelapse-tool/electron/renderer timelapse-tool/python/tests timelapse-tool/tests
```

创建 `timelapse-tool/.gitignore`：

```gitignore
node_modules/
__pycache__/
*.pyc
.venv/
dist/
build/
.DS_Store
```

- [ ] **Step 4: 提交**

```bash
git add timelapse-tool/.gitignore
git commit -m "chore: 初始化 timelapse-tool 项目目录"
```

---

## Task 1: Python 后端 health 端点

**Files:**
- Create: `timelapse-tool/python/requirements.txt`
- Create: `timelapse-tool/python/server.py`
- Test: `timelapse-tool/python/tests/test_server.py`

- [ ] **Step 1: 创建 requirements.txt**

```
fastapi==0.110.0
uvicorn[standard]==0.29.0
pytest==8.1.1
httpx==0.27.0
```

- [ ] **Step 2: 安装依赖（建虚拟环境）**

```bash
cd timelapse-tool/python && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```
Expected: 安装成功，无报错。

- [ ] **Step 3: 写失败的测试**

创建 `timelapse-tool/python/tests/test_server.py`：

```python
from fastapi.testclient import TestClient
from server import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 4: 运行测试确认失败**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_server.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'server'` 或 `app` 未定义。

- [ ] **Step 5: 写最小实现**

创建 `timelapse-tool/python/server.py`：

```python
from fastapi import FastAPI

app = FastAPI(title="Timelapse Tool Backend")


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 6: 运行测试确认通过**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_server.py -v`
Expected: PASS。

- [ ] **Step 7: 提交**

```bash
git add timelapse-tool/python/requirements.txt timelapse-tool/python/server.py timelapse-tool/python/tests/test_server.py
git commit -m "feat: 后端 health 端点"
```

---

## Task 2: Python 后端 WebSocket 进度通道

**Files:**
- Modify: `timelapse-tool/python/server.py`
- Test: `timelapse-tool/python/tests/test_server.py`

- [ ] **Step 1: 写失败的测试**

在 `timelapse-tool/python/tests/test_server.py` 末尾追加：

```python
def test_websocket_echoes_ping():
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "ping"})
        data = websocket.receive_json()
        assert data == {"type": "pong"}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_server.py::test_websocket_echoes_ping -v`
Expected: FAIL，连接 `/ws` 失败（404/拒绝）。

- [ ] **Step 3: 写最小实现**

在 `timelapse-tool/python/server.py` 末尾追加：

```python
from fastapi import WebSocket


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        message = await websocket.receive_json()
        if message.get("type") == "ping":
            await websocket.send_json({"type": "pong"})
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_server.py -v`
Expected: 两个测试都 PASS。

- [ ] **Step 5: 提交**

```bash
git add timelapse-tool/python/server.py timelapse-tool/python/tests/test_server.py
git commit -m "feat: 后端 WebSocket 进度通道骨架"
```

---

## Task 3: 后端可独立启动（uvicorn 入口）

**Files:**
- Modify: `timelapse-tool/python/server.py`

- [ ] **Step 1: 添加 main 启动块**

在 `timelapse-tool/python/server.py` 末尾追加：

```python
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8756)
```

- [ ] **Step 2: 手动验证服务可启动**

Run: `cd timelapse-tool/python && .venv/bin/python server.py &` 然后 `sleep 2 && curl -s http://127.0.0.1:8756/health`
Expected: 输出 `{"status":"ok"}`。验证后 `kill %1` 停掉。

- [ ] **Step 3: 提交**

```bash
git add timelapse-tool/python/server.py
git commit -m "feat: 后端 uvicorn 启动入口（端口 8756）"
```

---

## Task 4: Electron 项目初始化与 package.json

**Files:**
- Create: `timelapse-tool/package.json`

- [ ] **Step 1: 创建 package.json**

创建 `timelapse-tool/package.json`：

```json
{
  "name": "timelapse-tool",
  "version": "0.1.0",
  "description": "延时摄影自动化 + AI 照片筛选桌面工具",
  "main": "electron/main.js",
  "scripts": {
    "start": "electron .",
    "test": "jest"
  },
  "devDependencies": {
    "electron": "^30.0.0",
    "jest": "^29.7.0"
  }
}
```

- [ ] **Step 2: 安装依赖**

Run: `cd timelapse-tool && npm install`
Expected: 安装成功，生成 `node_modules/` 和 `package-lock.json`。

- [ ] **Step 3: 提交**

```bash
git add timelapse-tool/package.json timelapse-tool/package-lock.json
git commit -m "chore: Electron 项目初始化"
```

---

## Task 5: Electron 主进程（建窗 + 拉起 Python 后端）

**Files:**
- Create: `timelapse-tool/electron/main.js`
- Create: `timelapse-tool/electron/preload.js`

- [ ] **Step 1: 创建 preload.js**

创建 `timelapse-tool/electron/preload.js`：

```javascript
const { contextBridge } = require("electron");

// 把后端地址暴露给渲染进程，避免渲染进程硬编码
contextBridge.exposeInMainWorld("backend", {
  httpBase: "http://127.0.0.1:8756",
  wsUrl: "ws://127.0.0.1:8756/ws",
});
```

- [ ] **Step 2: 创建 main.js**

创建 `timelapse-tool/electron/main.js`：

```javascript
const { app, BrowserWindow } = require("electron");
const { spawn } = require("child_process");
const path = require("path");

let pyProc = null;

function startBackend() {
  const pythonBin = path.join(__dirname, "..", "python", ".venv", "bin", "python");
  const serverScript = path.join(__dirname, "..", "python", "server.py");
  pyProc = spawn(pythonBin, [serverScript], { stdio: "inherit" });
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.loadFile(path.join(__dirname, "renderer", "index.html"));
}

app.whenReady().then(() => {
  startBackend();
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (pyProc) pyProc.kill();
  if (process.platform !== "darwin") app.quit();
});

app.on("quit", () => {
  if (pyProc) pyProc.kill();
});
```

- [ ] **Step 3: 提交**

```bash
git add timelapse-tool/electron/main.js timelapse-tool/electron/preload.js
git commit -m "feat: Electron 主进程，建窗并拉起 Python 后端"
```

---

## Task 6: 双 Tab UI 外壳

**Files:**
- Create: `timelapse-tool/electron/renderer/index.html`
- Create: `timelapse-tool/electron/renderer/style.css`

- [ ] **Step 1: 创建 index.html**

创建 `timelapse-tool/electron/renderer/index.html`：

```html
<!DOCTYPE html>
<html lang="zh">
<head>
  <meta charset="UTF-8" />
  <title>延时摄影工具</title>
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <nav class="tabs">
    <button class="tab active" data-tab="pipeline">延时流水线</button>
    <button class="tab" data-tab="selector">照片筛选</button>
    <span id="conn-status" class="status">连接中…</span>
  </nav>
  <main>
    <section id="pipeline" class="panel active">
      <h1>延时流水线</h1>
      <p>（占位 — 由后续计划实现）</p>
    </section>
    <section id="selector" class="panel">
      <h1>照片筛选</h1>
      <p>（占位 — 由后续计划实现）</p>
    </section>
  </main>
  <script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: 创建 style.css**

创建 `timelapse-tool/electron/renderer/style.css`：

```css
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, sans-serif; color: #222; }
.tabs { display: flex; align-items: center; gap: 8px; padding: 12px; border-bottom: 1px solid #ddd; background: #fafafa; }
.tab { padding: 8px 16px; border: none; background: transparent; cursor: pointer; font-size: 14px; border-radius: 6px; }
.tab.active { background: #007aff; color: #fff; }
.status { margin-left: auto; font-size: 12px; color: #888; }
.status.ok { color: #34c759; }
.status.err { color: #ff3b30; }
.panel { display: none; padding: 24px; }
.panel.active { display: block; }
h1 { font-size: 20px; margin-bottom: 12px; }
```

- [ ] **Step 3: 提交**

```bash
git add timelapse-tool/electron/renderer/index.html timelapse-tool/electron/renderer/style.css
git commit -m "feat: 双 Tab UI 外壳与样式"
```

---

## Task 7: 前端 Tab 切换与后端连通性逻辑

**Files:**
- Create: `timelapse-tool/electron/renderer/app.js`
- Test: `timelapse-tool/tests/smoke.test.js`

- [ ] **Step 1: 写失败的测试**

创建 `timelapse-tool/tests/smoke.test.js`：

```javascript
const { switchTab, statusLabel } = require("../electron/renderer/app.js");

test("switchTab 切换激活面板", () => {
  document.body.innerHTML = `
    <button class="tab active" data-tab="pipeline"></button>
    <button class="tab" data-tab="selector"></button>
    <section id="pipeline" class="panel active"></section>
    <section id="selector" class="panel"></section>`;
  switchTab("selector");
  expect(document.getElementById("selector").classList.contains("active")).toBe(true);
  expect(document.getElementById("pipeline").classList.contains("active")).toBe(false);
});

test("statusLabel 根据健康状态返回文案", () => {
  expect(statusLabel(true)).toBe("后端已连接");
  expect(statusLabel(false)).toBe("后端连接失败");
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd timelapse-tool && npx jest --testEnvironment=jsdom tests/smoke.test.js`
Expected: FAIL，`Cannot find module '../electron/renderer/app.js'`。

- [ ] **Step 3: 写最小实现**

创建 `timelapse-tool/electron/renderer/app.js`：

```javascript
function switchTab(name) {
  document.querySelectorAll(".tab").forEach((t) => {
    t.classList.toggle("active", t.dataset.tab === name);
  });
  document.querySelectorAll(".panel").forEach((p) => {
    p.classList.toggle("active", p.id === name);
  });
}

function statusLabel(healthy) {
  return healthy ? "后端已连接" : "后端连接失败";
}

// 浏览器环境下绑定交互；测试环境（无 window.backend）跳过
if (typeof window !== "undefined" && window.backend) {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });

  const statusEl = document.getElementById("conn-status");
  fetch(window.backend.httpBase + "/health")
    .then((r) => r.json())
    .then((d) => {
      const ok = d.status === "ok";
      statusEl.textContent = statusLabel(ok);
      statusEl.className = "status " + (ok ? "ok" : "err");
    })
    .catch(() => {
      statusEl.textContent = statusLabel(false);
      statusEl.className = "status err";
    });

  const ws = new WebSocket(window.backend.wsUrl);
  ws.onopen = () => ws.send(JSON.stringify({ type: "ping" }));
}

if (typeof module !== "undefined") {
  module.exports = { switchTab, statusLabel };
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd timelapse-tool && npx jest --testEnvironment=jsdom tests/smoke.test.js`
Expected: 两个测试都 PASS。
（若报缺少 jsdom：`npm install --save-dev jest-environment-jsdom`）

- [ ] **Step 5: 提交**

```bash
git add timelapse-tool/electron/renderer/app.js timelapse-tool/tests/smoke.test.js
git commit -m "feat: 前端 Tab 切换与后端连通性检查"
```

---

## Task 8: 端到端手动验证

**Files:** 无（验证任务）

- [ ] **Step 1: 启动完整应用**

Run: `cd timelapse-tool && npm start`
Expected: Electron 窗口打开，显示双 Tab 外壳，右上角状态在约 1-2 秒内变为绿色「后端已连接」。

- [ ] **Step 2: 验证 Tab 切换**

点击「照片筛选」Tab。
Expected: 面板切换到照片筛选占位内容，Tab 高亮切换。

- [ ] **Step 3: 验证后端日志**

观察终端，应看到 uvicorn 启动日志与 WebSocket 连接（ping/pong）。
Expected: 无报错。关闭窗口后 Python 进程自动退出（再次确认无残留 `python server.py` 进程：`pgrep -f server.py` 应无输出）。

---

## Self-Review Notes

- **Spec 覆盖**：本计划对应 spec 第 3 节（架构）与第 6 节（文件结构）的外壳部分。延时流水线、AI 筛选、相机配置、错误处理细节均属后续计划，不在本计划范围。
- **端口**：后端固定 8756，前后端两处引用（preload.js / server.py）一致。
- **导出符号一致性**：`switchTab` / `statusLabel` 在 app.js 定义并在 smoke.test.js 引用，命名一致。
- **测试环境**：app.js 用 `window.backend` 存在性区分浏览器/测试环境，保证 Jest 下不执行 DOM 绑定与网络请求。
