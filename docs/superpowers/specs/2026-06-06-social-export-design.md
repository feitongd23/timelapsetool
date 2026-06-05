# 社媒导出（Social Export）设计

> 在 AE 出 ProRes 母版的基础上，新增「导出阶段」：保留母版 + 用 AVFoundation 转出一个可自由配置的社媒版（横/竖屏常用画幅）。用 AVFoundation 原生导出**替代**原 Premiere PR 阶段。

## 目标

- 每次跑流水线，固定**保留 ProRes 母版**（`_ae_intermediate.mov` 落地为 `timelapse_master.mov`）。
- 额外导出 **1 个社媒版**，三个维度**自由组合**：格式、画幅、分辨率。
- 覆盖抖音/小红书/B站常用横竖屏画幅，保持母版「不裁切」哲学（原始画幅可选）。
- 全 macOS 原生（AVFoundation + Swift），不依赖 ffmpeg / Premiere / `.epr`，硬件加速。

## 架构与数据流

流水线从 `BR → LRT → AE → PR(Premiere)` 改为 `BR → LRT → AE → 导出(AVFoundation)`。

```
AE 出 _ae_intermediate.mov (ProRes 4444 母版)
   └─ 导出阶段
       ├─ ① 保留母版 → timelapse_master.mov
       └─ ② AVFoundation 转码 → timelapse_social_<WxH>_<fmt>.mp4
```

## 转码规格

社媒版 = 三个独立维度自由组合：

| 维度 | 取值 |
|------|------|
| 格式 | H.265(HEVC，更小）/ H.264（最兼容） |
| 画幅 | 16:9 横 / 9:16 竖 / 3:4 竖 / 1:1 方 / 3:2 原始（不裁） |
| 分辨率 | 720 / 1080 / 4K（**按短边**计） |

**像素表**（短边 = 分辨率档；以 1080 为例）：

| 画幅 | 720 | 1080 | 4K |
|------|-----|------|----|
| 16:9 横 | 1280×720 | 1920×1080 | 3840×2160 |
| 9:16 竖 | 720×1280 | 1080×1920 | 2160×3840 |
| 3:4 竖 | 720×960 | 1080×1440 | 2160×2880 |
| 1:1 方 | 720×720 | 1080×1080 | 2160×2160 |
| 3:2 原 | 1080×720 | 1620×1080 | 3240×2160 |

**裁切**：非「原始」画幅一律**中心裁切**——从母版（实际尺寸由 RAW 比例决定，不写死）中心取目标宽高比的最大矩形，再缩放到目标像素。原始 3:2 不裁、仅缩放。

> 裁切位置固定取正中。延时构图重点通常居中，中心裁是合理默认。

## 模块边界与职责

沿用项目既有「Swift 干活 + Python 编排 + 可注入 run 单测」模式。**裁切/缩放数学全部放 Python（纯函数、可单测），Swift 只执行 AVFoundation。**

| 文件 | 职责 |
|------|------|
| `pipeline/media_export.swift`（新） | 收 `源 / 裁框(x,y,w,h) / 输出尺寸(w,h) / 格式`，用 `AVAssetExportSession` + `AVMutableVideoComposition` 出 HEVC/H.264。`presetName`：H.265→`HEVCHighestQuality`，H.264→`HighestQuality`；`renderSize`=输出尺寸；`layerInstruction` transform = 平移(−裁框原点) + 缩放(输出/裁框)。 |
| `pipeline/export.py`（由 `pr.py` 重构） | 编排：①保留母版（移动/复制为 `timelapse_master.mov`）②调 Swift 出社媒版。含路径、命令拼装、`ensure_export_binary`（首次 swiftc 编译缓存）、`render_exports`。缺中间视频/缺输出报错的逻辑从旧 `render_final` 保留。 |
| `pipeline/export_formats.py`（扩展） | 社媒维度的唯一事实来源：`social_pixels(aspect, resolution)→(w,h)`、`crop_rect(src_w, src_h, aspect)→(x,y,w,h)`、`validate_social(social)`。 |
| `pipeline/stages.py` | `PRStage` → `ExportStage`（`manual=False`），委托 `export.render_exports`。`default_stages` 末位换成 `ExportStage`。 |
| `pipeline/models.py` / `server.py` | `PipelineConfig` 增 `social` 字段；`StartBody` 接收 `social`。 |
| UI `index.html` / `pipeline.js` | 导出区重做（见下）。 |

**删除**：`pr.py` 的 Premiere 部分（`build_pr_script`/`build_pr_cmd`/`.epr`/`PRESET_EPR`）整体移除——未跑通且不再需要。

**文件命名**：母版 `timelapse_master.mov`；社媒版 `timelapse_social_<W>x<H>_<fmt>.mp4`（如 `timelapse_social_1080x1920_h265.mp4`），带尺寸避免不同配置互相覆盖。

## 前后端数据结构

前端 → 后端：
```json
social = { "format": "H.265", "aspect": "9:16", "resolution": "1080p" }
```
后端 `export_formats` 展开为 `social_pixels` + `crop_rect`，连同源母版路径传给 Swift。

## UI（延续扁平化 + 液态玻璃）

复用现有 `.glass` 卡片、`.field`/`.row` 布局与原生 `select` 样式，**不引入新视觉/新组件**，与「延时流水线」表单同一调性。极简、统一、高级。

```
导出
  母版    自动保留 ProRes 母版 → timelapse_master.mov     （说明文字，固定）
  社媒版  格式 [H.265 ▾]   画幅 [9:16 竖 ▾]   分辨率 [1080p ▾]
          → 预览：1080×1920 · H.265 · timelapse_social_1080x1920_h265.mp4   （现有小字提示样式）
```

`pipeline.js`：`buildSocialConfig(form)` 取三个下拉值；`readForm` 加三字段；移除旧 `export_mode`/`preset`/`manual` 相关 DOM 与逻辑。预览串由前端按选择实时算出（与后端 `social_pixels` 同口径）。

## 测试策略（TDD，与 AE/合并一致）

| 层 | 测什么 |
|----|--------|
| `export_formats` | `social_pixels` 各画幅×分辨率像素正确（含偶数化）；`crop_rect` 中心裁框正确（含横/竖/方/原始）；`validate_social` 拒非法组合 |
| `export.py` | `master_path`/`social_output_path` 命名；`build_export_cmd` 参数顺序；`ensure_export_binary`（注入 run，缺二进制触发 swiftc）；`render_exports` 编排（先保留母版后转社媒、缺中间视频报错、缺输出报错） |
| `media_export.swift` | swiftc 编译通过；真机用真实母版转一小段（HEVC 1080p 竖屏）验证可播、尺寸/裁切正确（实机验证点） |
| stages / API | `ExportStage` 委托 `render_exports`；`/pipeline/start` 带 `social` 跑通 |
| UI（jsdom） | `buildSocialConfig` 构造正确；预览串与 `social_pixels` 同口径 |

## 偶数化与编码约束

输出宽高均取偶数（H.264/H.265 要求）。`social_pixels` 计算后对宽高各向上/就近取偶。

## 非目标 / 未来扩展

- **精细码率控制**：先走 `AVAssetExportPreset...HighestQuality` 系统码率（社媒够用）。未来要控码率改用 `AVAssetReader`+`AVAssetWriter`。
- **裁切位置微调**（上/中/下、左/中/右）：先固定中心。`crop_rect` 预留 anchor 参数位即可，UI 暂不暴露。
- **多社媒版同时导出**：本期就 1 个。`render_exports` 接口设计成可接受列表，便于以后扩展。
- 竖屏不做防裁智能构图/主体检测。

## 实机验证点

1. swiftc 编译 `media_export.swift` 通过。
2. 用本会话已产出的真实母版 `~/Desktop/tl_out_full/_ae_intermediate.mov` 转一版 H.265 1080p 9:16，确认：能播、帧率仍 60、尺寸 1080×1920、中心裁构图合理、文件明显小于母版。
3. 端到端：`/pipeline/start` 带 `social` 跑到导出阶段，母版 + 社媒版都落地。
