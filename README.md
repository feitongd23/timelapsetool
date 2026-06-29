# 延时摄影自动化工具（Timelapse Tool）

> 面向摄影师的 macOS 桌面应用：把「延时摄影 RAW 序列 → 调色 → 渲染成片 → 社交媒体多版本输出」这条要在 4 个软件间手动倒腾的链路，自动化成一键流程，并内置自动运镜、主体识别、稳定等增强。

主代码在 [`timelapse-tool/`](timelapse-tool/)；产品文档见 [`docs/PRD-timelapse-tool.md`](docs/PRD-timelapse-tool.md)。

---

## ✨ 功能亮点

- **一条流水线串起全链路**：`Bridge(调色) → LRTimelapse(关键帧/去闪) → After Effects(渲染) → 导出`，手动阶段自动打开对应软件并引导，自动阶段后台跑。
- **稳健的 AE 渲染**：分块渲染防长序列崩溃 + 失败重试 + 断点续渲 + 输出封口校验；渲完用 AVFoundation 无损拼接成 ProRes 母版。
- **帧级进度条 + 异步执行**：渲染在后台线程跑，UI 不阻塞，进度条逐帧平滑推进。
- **自动识别素材**：读 RAW 的 EXIF 展示相机/镜头/快门/光圈/ISO/焦距；母版按 RAW **原始分辨率**建，自动适配 S35/全画幅，不放大虚化。
- **社媒多版本导出**：保留 ProRes 母版 + 一键出社媒版（H.265/H.264 × 16:9/9:16/3:4/1:1/原始 × 720p/1080p/4K，中心裁切）。
- **自动运镜**：Ken Burns 推拉 / Pan 平移 / 竖屏横扫；可手动拖框选放大区域，或用 **Vision 显著性**自动对准主体。
- **成片转社媒**：导入任意已有成片，直接套社媒配置出片。
- **动态背景**：选素材后自动挑饱和度最高的一帧做模糊背景，玻璃 UI 透出你的片子。

## 🏗 技术架构

```
Electron(前端 UI) ──HTTP/轮询──▶ FastAPI(本地后端, :8756)
                                     │
        ┌────────────────────────────┼──────────────────────────┐
   驱动 Adobe 套件               编排执行                   macOS 原生工具(Swift)
  Bridge / LRTimelapse / AE   PipelineRunner            · media_export  AVFoundation 转码/裁切/运镜 ramp
  (AppleScript DoScriptFile)  (异步线程 + 进度上报)      · --saliency    Vision 主体识别
  aerender(分块渲染 ProRes)                              · --meta        ImageIO 读 EXIF
                                                         · mov_concat    无损拼接
                                                         qlmanage(缩略图)
```

**设计取舍**
- **全本地、零云依赖、不装 ffmpeg** —— 缩放/转码/分析全用系统自带的 AVFoundation / Vision / ImageIO / qlmanage。
- **数学放 Python（纯函数、可单测），执行放 Swift** —— 裁切/像素/运镜/锚点的计算都是纯函数，外部命令注入 `run`/`stream` 以便测试。
- **AVFoundation 替代 Premiere** —— 母版本就是 ProRes，社媒转码用原生 AVFoundation 更可靠、无第三方依赖。

## 🚀 快速开始

**前置**：macOS、Node 20、Python 3.9；如需跑完整流水线还需 After Effects 2026 / Bridge / LRTimelapse。

```bash
cd timelapse-tool

# 后端依赖
python3 -m venv python/.venv
python/.venv/bin/pip install -r python/requirements.txt

# 前端依赖
npm install

# 启动（Electron 会自动拉起后端）
npm start
```

## 🧪 测试

```bash
# 后端（pytest，140+ 用例）
cd timelapse-tool/python && .venv/bin/python -m pytest

# 前端（Jest + jsdom）
cd timelapse-tool && npm test
```

核心逻辑（裁切/像素/运镜/进度解析等）均为纯函数并有单测；外部命令通过依赖注入在测试中替身。

## 📁 项目结构

```
timelapse-tool/
├── electron/            # 前端：主进程、preload、渲染层(UI/逻辑)
│   └── renderer/        # pipeline.js / social_tab.js / index.html / style.css
├── python/
│   ├── pipeline/        # runner/stages/ae/export/export_formats/preview/effects/...
│   ├── media_export.swift  # AVFoundation 转码 + Vision 主体 + ImageIO 元数据
│   ├── mov_concat.swift    # ProRes 无损拼接
│   └── tests/           # pytest
│   └── server.py        # FastAPI
└── tests/               # 前端 Jest
docs/                    # PRD + 设计/实现文档
```

## 💡 工程亮点（踩坑与排查）

- **aerender 渲不出 / 渲成 25fps 的真凶**：输出模块模板名误用「Apple ProRes 4444」（AE 里真实叫「ProRes 4444」），靠在 AE 内枚举模板名 + 帧率插桩定位根因。
- **变形稳定器参数静默失败**：三个属性 matchName 全猜错且被 `try/catch` 吞，靠在 AE 里枚举效果真实属性 matchName 才发现。
- **可测性设计**：把"跟外部软件/命令打交道"的副作用收到注入点，核心算法保持纯函数，使一个重外部依赖的工具仍有 140+ 自动化测试。

## 🗺 路线图

- [ ] 变形稳定器：渲染前触发并等待运动分析完成（当前分析未在渲染前跑完）
- [ ] 导出阶段帧级进度（AVAssetExportSession.progress 流式上报）
- [ ] 社媒码率自定义（AVAssetWriter）
- [ ] 运镜：多段/关键帧路径、裁切位置微调
- [ ] 照片筛选 Tab

## 📄 文档

完整产品需求与设计见 [`docs/PRD-timelapse-tool.md`](docs/PRD-timelapse-tool.md)。
