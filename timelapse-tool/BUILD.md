# 打包成 macOS 安装包（.dmg）指南

> 目标：把这个 Electron + Python + Swift 应用打成一个 macOS `.dmg`，分享给（装了 Adobe 全套的 macOS）摄影师朋友。
> ⚠️ 打不进安装包的硬依赖：**After Effects 2026 / Bridge / LRTimelapse**（完整流水线需要）；没装 Adobe 的人只能用「成片转社媒」。
> 现状：PyInstaller / electron-builder 都未装；Python 3.9.6；Node 在 `~/.local/node`。

---

## 总体思路

Electron 打包只管前端，但本应用还有 **Python 后端** 和 **Swift 工具**，都要一并塞进 `.app`：

1. **Python 后端** → PyInstaller 打成独立可执行 `server`（含 fastapi/uvicorn/pipeline），不依赖目标机有 Python。
2. **Swift 工具** → 预编译 `media_export` / `mov_concat` 二进制（目标机不一定有 swiftc，且不能联网现编）。
3. **Electron** → `main.js` 改成 spawn 打包后的 `server` 可执行；`ensure_*_binary` 改成用打包的 Swift 二进制。
4. **electron-builder** → 把 `server` + Swift 二进制作为 `extraResources` 打进 `.app`，产出 `.dmg`。
5. **签名/公证** → 没 Apple 开发者账号就出**未签名** `.dmg`，告诉对方「右键 → 打开」绕过 Gatekeeper。

---

## Task 1：PyInstaller 打包后端

```bash
cd timelapse-tool/python
.venv/bin/pip install pyinstaller
# uvicorn 是动态 import，需补 hidden imports；swift 源文件作为数据带上
# 用 --onedir 而非 --onefile：onefile 每次启动都解压临时目录，冷启动 ~21s 且每次都慢；
# onedir 产物是文件夹（首次冷 ~22s，之后启动 0.4s，文件固定走 OS 缓存）。工具会反复开，onedir 明显更优。
.venv/bin/pyinstaller --onedir --name server \
  --hidden-import=uvicorn.lifespan.on \
  --hidden-import=uvicorn.lifespan.off \
  --hidden-import=uvicorn.protocols.http.auto \
  --hidden-import=uvicorn.protocols.http.h11_impl \
  --hidden-import=uvicorn.protocols.websockets.auto \
  --hidden-import=uvicorn.protocols.websockets.websockets_impl \
  --hidden-import=uvicorn.loops.auto \
  --hidden-import=uvicorn.loops.asyncio \
  --collect-submodules=pipeline \
  server.py
# 产物：python/dist/server/（目录，含可执行 server + _internal/）
# 验证：./dist/server/server &  然后 curl 127.0.0.1:8756/health
```
踩坑预案：若启动报缺模块，把对应模块加到 `--hidden-import` 再打。FastAPI/pydantic 一般能自动收。

## Task 2：预编译 Swift 二进制

```bash
cd timelapse-tool/python/pipeline
swiftc -O media_export.swift -o /tmp/build/media_export
swiftc -O mov_concat.swift  -o /tmp/build/mov_concat
# 这两个二进制随包分发
```

## Task 3：改代码——用打包资源而非现编/venv

- `pipeline/export.py` `ensure_export_binary` 和 `pipeline/ae.py` `ensure_concat_binary`：
  打包态下不要 `swiftc` 现编，直接用随包二进制。判断方式：环境变量（Electron 启动 server 时设 `TLT_RESOURCES=<resourcesPath>`），存在则 `binary = $TLT_RESOURCES/media_export`（或 mov_concat），跳过编译。
- `electron/main.js` `startBackend`：打包态下 spawn `process.resourcesPath` 下的 `server` 可执行，并设 `env.TLT_RESOURCES`；开发态保持现在的 `.venv/bin/python server.py`。用 `app.isPackaged` 区分。

```js
function startBackend() {
  const { app } = require("electron");
  if (app.isPackaged) {
    const res = process.resourcesPath;               // .app/Contents/Resources
    // onedir：可执行在 Resources/server/server（同目录有 _internal/）
    pyProc = spawn(path.join(res, "server", "server"), [], {
      stdio: "inherit",
      env: { ...process.env, TLT_RESOURCES: res },
    });
  } else {
    const pythonBin = path.join(__dirname, "..", "python", ".venv", "bin", "python");
    pyProc = spawn(pythonBin, [path.join(__dirname, "..", "python", "server.py")], { stdio: "inherit" });
  }
}
```

## Task 4：electron-builder 配置 + 打包

```bash
cd timelapse-tool
export PATH="$HOME/.local/node/bin:$PATH"
# ⚠️ 必须锁 24.13.3：26.x 依赖纯 ESM 的 @noble/hashes@2，自身却用 require() 加载，
# 打 dmg 到 blockmap 阶段会 ERR_REQUIRE_ESM 直接崩。24.13.3 实测可用。
npm install --save-dev electron-builder@24.13.3
```
`package.json` 加：
```json
"build": {
  "appId": "com.feitong.timelapsetool",
  "productName": "延时摄影工具",
  "files": ["electron/**/*"],
  "extraResources": [
    { "from": "python/dist/server", "to": "server" },
    { "from": "/tmp/build/media_export", "to": "media_export" },
    { "from": "/tmp/build/mov_concat", "to": "mov_concat" }
  ],
  "mac": { "target": "dmg", "category": "public.app-category.video" }
}
```
`package.json` scripts 加：`"dist": "electron-builder"`，然后：
```bash
npm run dist
# 产物（带 arch 后缀）：dist/延时摄影工具-0.1.0-arm64.dmg
```

## Task 5：未签名分发说明

没有 Apple Developer 账号 → `.dmg` 未签名/未公证。给对方的话术：
> 下载后右键 `.app` → 打开 → 再点「打开」（第一次会拦，之后正常）。或系统设置 → 隐私与安全性 → 仍要打开。

要彻底免拦：需 Apple Developer Program（$99/年）做签名 + 公证（`electron-builder` 配 `mac.identity` + `afterSign` 公证脚本）。

---

## 验证清单（打完包后）
1. 在**另一台没装 Python venv** 的 macOS（或先 `mv` 掉本机 venv 模拟）上装 `.dmg`、打开，后端能起、`/health` 通。
2. 「成片转社媒」整条能跑（不依赖 Adobe，最容易验）。
3. 若那台机装了 AE/LRT，验证完整流水线。

## 已知限制
- Adobe（AE/Bridge/LRT）打不进包，完整流水线需对方自备。
- 未签名 → Gatekeeper 拦，需手动放行。
- Python 3.9 + PyInstaller 偶有 hidden-import 缺失，按报错补。
- 后端冷启动：onedir 首次开 ~22s（文件系统缓存冷 + dyld 首次加载一堆 .so），之后每次 0.4s。
  onefile 则每次都 ~21s（每次重解压新临时目录）。已选 onedir。
  首次那 22s 的体验兜底：可在 Electron 起来后先显示「后端启动中…」loading，`/health` 通了再放行。
