# 自动运镜 + 主体识别（Auto Camera Motion）设计

> 给社媒导出加运镜（Ken Burns 推拉 / Pan 平移 / 竖屏横扫），方向/强度可调；外加一个"自动对准主体"开关（Vision 显著性检测）。复用现有 AVFoundation 导出架构——运镜 = 裁切框随时间从起始框渐变到结束框。

## 目标

- 社媒版可加运镜，三类：**Ken Burns 推拉**、**Pan 平移**、**竖屏横扫**。
- 运镜 **类型 / 方向 / 强度** 全手动可调；默认"无运镜"（完全等于现状，零风险）。
- 一个 **subject** 开关：开则用 Vision 显著性自动找主体，裁切/运镜锚点对准主体（解决"中心裁切切掉重点"）；关则锚点=画面正中。
- 全 macOS 原生（AVFoundation + Vision），无新依赖；不改 AE 母版那一层，只在社媒版导出做。

## 数据结构

`social` 配置扩展：
```
social = {
  format, aspect, resolution,           # 现状
  motion:  { type, direction, intensity },
  subject: true|false
}
```

| 字段 | 取值 |
|------|------|
| motion.type | `none` / `kenburns` / `pan` / `sweep` |
| motion.direction | kenburns: `in`/`out`；pan: `left`/`right`/`up`/`down`；sweep: `lr`/`rl`；none: 忽略 |
| motion.intensity | `light` / `medium` / `strong`（none/sweep 时按需忽略） |
| subject | `true`=对准主体；`false`=对准画面中心 |

## 核心机制：锚点

一切围绕一个归一化锚点 `anchor=(cx,cy)`，取值 0–1：
- `subject=false` → `anchor=(0.5,0.5)`（画面正中，等于现状）
- `subject=true` → `anchor=` Vision 显著性主体中心；检测不到则回退 `(0.5,0.5)`

裁切框 / 运镜起止框都**以 anchor 为中心**展开，并 **clamp 到母版边界**（主体靠边时整体不越界）。

## 运镜起止框语义

`export_formats.motion_frames(src_w, src_h, aspect, motion, anchor=(0.5,0.5))` → `(start_crop, end_crop)`，两框都是目标 `aspect` 比例、都在母版内、各为 `(x,y,w,h)`。

- **none** → `start = end = crop_rect(src_w, src_h, aspect, anchor)`（退化回当前固定裁切）。
- **kenburns**（同心于 anchor，尺寸差 = 强度）：
  - 基准框 `base = crop_rect(..., anchor)`（以 anchor 为中心的最大可用目标裁框）。
  - `in`（推近）：`start=base`，`end=base/intensity`（更小=放大）。
  - `out`（拉远）：`start=base/intensity`，`end=base`。
  - 强度系数：light 1.06 / medium 1.12 / strong 1.20。
- **pan**（先按强度缩小留余量，再沿方向在母版余量内移动）：
  - `box = base` 按 `pan_scale` 缩小（light 0.92 / medium 0.85 / strong 0.78），中心起于 anchor 并 clamp。
  - 沿 direction 把 box 从一端移到另一端（移动幅度 = 该方向母版余量）。`left`=向左移（画面右扫）等，以"镜头移动方向"命名。
- **sweep**（竖屏横扫，仅竖屏画幅有意义）：
  - `box` = 目标 aspect、高度=母版高（竖屏满高），宽=按比例。
  - `lr`：从 `x=0` 扫到 `x=src_w-box_w`；`rl` 反向。锚点不参与（横扫本就扫全幅）。

> 余量与清晰度：运镜要求母版比裁框大（有移动/缩放空间）。母版 3840 宽远超 1080p 目标，裁一部分再缩仍锐利。Pan/Ken Burns 的"留余量"只在母版像素里取景，不影响成片清晰度。

## 主体检测（Vision，复用 probe 模式）

`media_export.swift` 加 `--saliency <src>` 模式：
- `AVAssetImageGenerator` 抽母版**中间帧**（`duration/2`）。
- `VNGenerateAttentionBasedSaliencyImageRequest` → 取最显著对象的 bbox 中心。
- 打印归一化 `"cx cy"`（0–1，注意 Vision 坐标系原点在左下，需翻 y 到左上口径与 Python 一致）。检测不到 → 打印 `0.5 0.5`。

`export.py`：`subject=true` 时先 `saliency_center(bin, master, run)` 拿锚点，否则 `(0.5,0.5)`，再算 `motion_frames`。**Vision 只"找主体"，裁框数学仍全在 Python 纯函数。**

## Swift 转码（transform ramp）

转码参数从「单裁框」改为「起止两框」：
```
media_export <src> <out> <hevc|h264> <sx sy sw sh> <ex ey ew eh> <ow oh>
```
- 对 `start_crop` 算 `startTransform = translate(-sx,-sy).concatenating(scale(ow/sw, oh/sh))`，对 `end_crop` 同理算 `endTransform`。
- `layer.setTransformRamp(fromStart: startTransform, toEnd: endTransform, timeRange: 整段)`。
- 起=止时 ramp 为静止，等于当前固定裁切（无运镜路径不变）。

## 模块边界

| 文件 | 改动 |
|------|------|
| `pipeline/export_formats.py` | `crop_rect` 加 `anchor` 参数；新增 `motion_frames`、强度/方向常量、`validate_social` 扩展校验 motion/subject |
| `pipeline/media_export.swift` | 加 `--saliency` 模式；转码改收起止两框 + `setTransformRamp` |
| `pipeline/export.py` | `saliency_center()`；`render_exports` 按 subject 取锚点、用 `motion_frames`；`build_export_cmd` 传起止两框 |
| `pipeline/models.py` | `validate_social` 已校验整个 social（含 motion/subject），无需改字段 |
| UI `index.html`/`pipeline.js` | 运镜下拉(类型/方向/强度) + 主体复选框；方向按类型联动；type=none 时禁用方向/强度 |

## UI（延续扁平 + 液态玻璃）

社媒版三个下拉下面加一行，复用 `.row`/`.field`/原生 `select`/`.hint-line`：
```
运镜 [无 ▾]   方向 [放大 ▾]   强度 [中 ▾]   ☐ 自动对准主体
```
- 方向 `<select>` 选项随运镜类型联动（JS，与后端 direction 集合同口径）。
- `运镜=无` 时方向/强度 `disabled`。
- `buildMotionConfig(values)` → `{type,direction,intensity}`；`buildSocialConfig` 增 `motion` 与 `subject`。

## 测试策略（TDD）

| 层 | 测什么 |
|----|--------|
| `export_formats` | `crop_rect` 带 anchor（中心/偏移/clamp 边界）；`motion_frames` 四类型起止框（none 起=止、kenburns 同心尺寸比、pan 端到端、sweep 满幅）；`validate_social` 收 motion/subject 合法、拒非法 |
| `export.py` | `saliency_center` 解析 `"cx cy"`；`build_export_cmd` 起止两框参数序（10 个数值：起止两框 8 + 输出尺寸 2）；`render_exports` 在 subject 开（fake_run 模拟 `--saliency` 返回锚点）与关两条分支正确 |
| `media_export.swift` | 编译；实机 `--saliency` 对真实母版输出合理主体中心；实机一版带 Ken Burns 的社媒版可播、有推拉 |
| UI（jsdom） | `buildMotionConfig`；方向联动表与后端同口径；type=none 禁用 |

## 非目标 / 未来扩展

- **动态主体跟随**（多帧追踪、运镜跟主体移动）：本期只做静态锚点（抽中间帧）。
- 多段/关键帧运镜、非线性缓动（`setTransformRamp` 是线性匀速；先匀速）。
- 人脸/特定物体优先：先用通用显著性。
- 多社媒版本同时导出（仍单版本）。

## 实机验证点

1. `swiftc` 编译 `media_export.swift` 通过（含 Vision import）。
2. `media_export --saliency ~/Desktop/tl_out_full/timelapse_master.mov` 输出一个 0–1 范围、对夕阳/地标合理的中心。
3. 用真实母版导一版 9:16 H.265、Ken Burns `in` medium：可播、60fps、时长不变、肉眼能看到缓慢推近。
4. `subject=true` 导一版：裁切/运镜明显对准主体而非死中心。
5. 全套自动化测试（pytest + jest）绿。
