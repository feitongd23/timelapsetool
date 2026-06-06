# 运镜手动选区 + 成片转社媒 设计

> 两个相关功能，共享一套社媒配置与转码逻辑：
> **A. 运镜手动选区** —— 选 Ken Burns 时弹窗在素材底图上拖框，决定放大到哪块。
> **B. 成片转社媒** —— 新 tab 导入已有 ProRes 成片，按社媒配置直接出社媒版（不走流水线）。

## 目标

- A：Ken Burns 的放大终点可由用户**手动框选**（代替自动中心/主体）；只对 Ken Burns 生效。
- B：任意已有成片（mov）→ 完整社媒配置（格式/画幅/分辨率/运镜/主体/选区）→ 直接出社媒版。
- 复用现成 `media_export`/`export_formats`，把社媒转码拆成可复用函数；两功能共用一个选区窗口。

## 第 1 段：共享重构 + 数据结构

**① 拆出纯转码函数**（`export.py`）：
```
transcode_social(src_mov, output_dir, social, emit, run=subprocess.run, binary=EXPORT_BIN) → 社媒版路径
    探源尺寸(probe) → 锚点(手动 box 中心 / 主体 / 画面中心)
    → motion_frames 起止框 → social_pixels → build_export_cmd → media_export → 校验输出
```
- `render_exports`（流水线）= 保留母版 + 调 `transcode_social`(源=母版)。
- 功能 B = 直接调 `transcode_social`(源=用户选的成片)。

**② `social.motion` 加可选 `box`**（归一化，相对源画面，0–1）：
```
motion = { type, direction, intensity, box? }   # box = [x, y, w, h]
```

**③ `motion_frames` 的 box 分支**（纯函数，`export_formats.py`）：
`type == "kenburns"` 且有 `box` 时：
- 把归一化 box 转源像素，取**中心** `(cx, cy)`。
- **结束框** = 以 `(cx,cy)` 为中心、目标 aspect 比例、贴合 box 的最小 aspect 框：`ew = max(box_px_w, box_px_h * r)`, `eh = ew / r`（`r = aspect 横向比`），偶数化、clamp 母版。
- **起始框** = `crop_rect(W, H, aspect, anchor=(cx_norm, cy_norm))`（以 box 中心为锚的全画幅 aspect 基准框）。
- `direction == "in"` → `(start=起始框, end=结束框)`（推近到 box）；`"out"` → 反过来。
- 无 `box` → 维持现状（anchor 中心 + intensity 同心缩放）。box 只对 kenburns 生效；pan/sweep 忽略。

**④ 锚点优先级**：手动 box 中心 > 主体识别 > 画面中心，统一喂 `motion_frames`。

## 第 2 段：功能 A 拖框窗口（前端）

- 运镜类型 = `Ken Burns` 时，导出区显示「选放大区域…」按钮（其它类型隐藏）。
- 点开 → **modal**：中间是**源首帧底图**，上叠**可拖动 / 拖角缩放的矩形框**（默认居中、目标 aspect 比例）；底部「确定 / 取消 / 重置为自动」。
- 确定 → 框转**归一化** `[x,y,w,h]` 存入 `motion.box`；取消/重置 → 清 box（回退自动锚点）。
- 底图来源：新增 `GET /preview/file_thumb?src=<文件>`（`qlmanage` 对任意图片/视频出缩略图）。A 传 RAW 首帧路径，B 传选中的 mov —— **A/B 共用同一选区 modal**，仅底图源不同。
- 坐标转换（像素框 ↔ 归一化）是纯函数，单测；拖拽交互不强测。

## 第 3 段：功能 B 成片转社媒 tab

- 顶部新增第三个 tab「成片转社媒」，独立 panel：
  1. 选成片文件（Electron `chooseFile`，filters = mov/mp4/mp4）
  2. 完整社媒配置（格式/画幅/分辨率/运镜/主体/选区）——**独立 id**（如 `b_social_format`）复用同一套控件与联动逻辑
  3. 「转换」按钮 + 进度/结果提示
- 输出：源 mov 同目录，`<源名>_social_<WxH>_<fmt>.mp4`。
- 后端：`POST /export/social_from {src, social}` → `transcode_social(src, 源目录, social, …)` → 返回社媒版路径。无新转码逻辑。
- `preload.js` 加 `chooseFile`（`dialog.showOpenDialog` openFile + 视频过滤）。

## 模块边界

| 文件 | 改动 |
|------|------|
| `pipeline/export_formats.py` | `motion_frames` 加 box 分支（纯函数） |
| `pipeline/export.py` | 拆出 `transcode_social`；`render_exports` 改为调它；新增 `social_output_path` 支持自定义前缀（成片名） |
| `pipeline/preview.py` | `file_thumb(src, cache, run)`（qlmanage 单文件缩略图） |
| `server.py` | `GET /preview/file_thumb`；`POST /export/social_from` |
| `electron/preload.js` | 加 `chooseFile` |
| `electron/main.js` | `choose-file` IPC（openFile + 视频过滤） |
| `electron/renderer/index.html` | 第三个 tab + panel；选区 modal 容器 |
| `electron/renderer/pipeline.js` | box 字段进 `buildSocialConfig`；选区 modal 逻辑 + 坐标转换；`Ken Burns` 时显示选区按钮 |
| `electron/renderer/social_tab.js`（新） | 成片转社媒 tab 的初始化与提交（复用社媒配置/选区组件） |

> 选区 modal 与社媒配置控件做成可被「流水线导出区」与「成片转社媒 tab」共同调用的小单元，避免两份重复。

## 测试

| 层 | 测什么 |
|----|--------|
| `export_formats` | `motion_frames` box 分支：kenburns+box 的起止框（end 贴合 box、aspect 比例、clamp）；无 box 维持现状；pan/sweep 忽略 box |
| `export.py` | `transcode_social`（注入 run，探尺寸→转码→校验）；`render_exports` 仍先保留母版后调 transcode_social |
| `preview.py` | `file_thumb` 命令拼装/缓存（注入 run） |
| server | `/preview/file_thumb`、`/export/social_from`（注入 transcode_social/ensure_binary） |
| 前端（jsdom） | box 像素↔归一化坐标转换纯函数；`buildSocialConfig` 带 box；`Ken Burns` 显示选区按钮 |
| 实机 | RAW 首帧 + mov 各弹一次选区框选；导入一段真实 ProRes 出社媒版，校验尺寸/帧率/构图（含手动 box 放大） |

## 非目标 / 未来

- 多框 / 关键帧路径运镜（先单框=单段 Ken Burns 终点）。
- box 仅 kenburns；pan/sweep 的手动起止先不做。
- 成片转社媒的批量队列（先单文件）。
- 视频缩略图取「中间帧」优化（先用 qlmanage 默认海报帧）。

## 实机验证点

1. 流水线选 Ken Burns → 选放大区域 → 框一块 → 出片确认推近到该区域。
2. 成片转社媒 tab：导入 `~/Desktop/tl_out_full/timelapse_master.mov` → 9:16 H.265 + 手动框 → 出 `timelapse_master_social_1080x1920_h265.mp4`，构图为所框区域。
3. 全套自动化测试（pytest + jest）绿。
