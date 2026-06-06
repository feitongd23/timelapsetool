# AE 渲染进度条 设计

> 把流水线执行从同步阻塞改为异步，AE 分块渲染上报帧级进度，前端轮询显示平滑进度条。

## 目标

- 点「继续」后 HTTP 立即返回（`running`），不再阻塞 ~40 分钟。
- AE 渲染**帧级**进度（跨段连续 0→~95%），前端进度条平滑推进 + 显示「渲染第 N/M 段 · 第 X/总 帧」。
- 导出阶段不细分（显示「导出社媒版…」），完成跳 100%。
- 保持可单测：帧解析是纯函数；流式执行器 `stream_run` 可注入。

## 执行模型（异步）

`server` 在后台线程跑非手动阶段：
- `pipeline_start` / `pipeline_continue`：起一个 **daemon 线程**跑 `_runner.start(config)` / `_runner.continue_()`，**立即返回** `_runner.status()`（此时 `running`）。
- 重入保护：server 维护 `_worker` 线程引用；若已有线程 alive，`/pipeline/continue` 返回 409「正在运行」。前端 `running` 时也禁用「继续」。
- 线程安全：runner 的状态都是简单标量/dict 赋值，GIL 下读写原子；`status()` 读快照。手动阶段（BR/LRT）`run` 很快，也在线程里跑、遇 manual 设 `WAITING` 后线程结束。

## 进度协议

`emit` 升级为 `emit(message, fraction=None)`：
- runner 注入的 `_emit` 包装：`self._progress = {"stage": self._current, "message": message, "fraction": fraction}`；同时仍 append 到日志。
- 旧调用 `emit("...")` 兼容（fraction=None → 进度条不动、只更文本）。
- `status()` 增加 `"progress": self._progress`（`{stage, message, fraction}`，fraction 可为 None）。

## AE 帧级进度

**流式执行器**（`ae.py`）：新增 `stream_run(cmd, on_line)` —— 默认用 `subprocess.Popen`（合并 stderr，`bufsize=1`）逐行读，回调 `on_line(line)`，返回 returncode 对象。仅 **aerender 调用**用 `stream_run`；AE 建工程（osascript）、合并仍用普通 `run`。`render_sequence` 增参 `stream_run=ae.stream_run` 以便测试注入。

**帧号解析**（纯函数）：`parse_aerender_frame(line) -> int | None`。aerender 行形如 `PROGRESS:  0:00:00:05 (6): 4 秒`，用正则 `\((\d+)\)` 取段内帧号；无匹配返回 None。

**全局 fraction**：`total = frame_count(seq)`；段 i 的 `start = starts[i]`；段内帧号 f → 全局帧 `g = start + f`；`fraction = min(g / total, 0.99)`（AE 阶段封顶 0.99，导出/完成才 100%）。每解析到帧号就 `emit(f"AE 阶段：渲染第 {i+1}/{N} 段 · 第 {g}/{total} 帧", fraction)`。

> aerender 的 `(N)` 为该段任务内帧序（每段从小到大）；段起始帧 `start` 来自已有的 chunk 划分 `starts`。

## 导出阶段

`ExportStage` 调 `render_exports` 前后 `emit("导出阶段：转社媒版…", 0.99)`；完成后 runner 设 `DONE`，前端把进度条补到 100%。不改 Swift、不做帧级。

## 前端

- `state==running` 时启动 `setInterval(refreshStatus, 1000)`；`done`/`failed` 时 `clearInterval`。
- 进度条 DOM（执行卡片内，玻璃风）：外层轨道 + 内层填充条，宽度 = `fraction*100%`；fraction 为 null 时显示「忙碌」态（条满宽 + 低透明脉动，或保持上次宽度）。下方一行 `progress.message` 文本。
- 纯函数 `progressPercent(status)` → 0–100 整数（done→100；running 用 fraction；无 fraction→保持/0），可 jsdom 单测。
- 「继续」按钮在 `running` 时 `disabled`。

## 测试

| 层 | 测什么 |
|----|--------|
| `ae.parse_aerender_frame` | 解析 `(6)` → 6；无括号 → None；多种行 |
| `ae.render_sequence`（注入 stream_run） | 喂假 PROGRESS 行 → emit 被调且 fraction 递增、跨段全局帧正确（如段2 第6帧→106/total） |
| `runner` | `_emit(msg, fraction)` 更新 `progress`；`status()` 含 progress；异步入口（线程跑完后状态/progress 正确，可用同步直跑 _run 验证逻辑，线程包装单独验证不重入） |
| `server` | continue/start 立即返回 running（线程未结束时 status=running）；重入返回 409 |
| 前端（jsdom） | `progressPercent`：running+fraction=0.43→43；done→100；failed/无 fraction 行为 |
| 实机 | 真实 AE 渲染时进度条平滑推进、文本逐帧更新；导出阶段显示文本；完成 100% |

## 线程安全细节

- runner 加 `_worker`（线程）非必须放 runner；放 server 更简单（server 持线程引用判重入）。runner 仅负责状态 + progress，不感知线程。
- `status()` 返回新 dict（拷贝），避免读到半更新的引用。

## 非目标 / 未来

- 导出阶段帧级进度（需 Swift 流式输出 AVAssetExportSession.progress）。
- 取消/暂停渲染。
- WebSocket 推送（先用 1s 轮询，够用；WS 已存在但只 ping/pong，本期不接进度）。

## 实机验证点

1. 点继续后请求秒回，看板 AE 高亮，进度条从 0 平滑爬升，文本「渲染第 N/M 段 · 第 X/总 帧」。
2. 段切换时帧号连续（不回跳）。
3. 导出阶段进度条停在 ~99% + 文本「导出社媒版…」，完成跳 100%。
4. 全套自动化测试（pytest + jest）绿。
