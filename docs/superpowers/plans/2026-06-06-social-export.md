# 社媒导出（Social Export）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 AVFoundation 导出阶段替代 Premiere PR 阶段：保留 ProRes 母版，并按「格式×画幅×分辨率」自由组合导出一个社媒版（中心裁切）。

**Architecture:** 裁切/缩放数学放 Python 纯函数（`export_formats.py`，可单测）；`media_export.swift` 只执行 AVFoundation（含 `--probe` 读母版尺寸 + 转码两种模式）；`export.py` 编排「保留母版→探尺寸→算裁框→转社媒版」；`stages.py` 用 `ExportStage` 替 `PRStage`。

**Tech Stack:** Python 3.9 + pytest（后端/编排），Swift + AVFoundation（转码，swiftc 编译缓存），Jest + jsdom（前端 `pipeline.js`）。

测试约定：`cd timelapse-tool/python && .venv/bin/python -m pytest`；`cd timelapse-tool && export PATH="$HOME/.local/node/bin:$PATH" && npm test`。

---

## File Structure

| 文件 | 职责 | 动作 |
|------|------|------|
| `python/pipeline/export_formats.py` | 社媒维度事实来源：像素/裁框/校验纯函数 | 扩展 |
| `python/pipeline/media_export.swift` | AVFoundation 转码 + `--probe` 读尺寸 | 新建 |
| `python/pipeline/export.py` | 编排：保留母版、探尺寸、命令拼装、`render_exports` | 新建 |
| `python/pipeline/pr.py` | Premiere 导出（未跑通） | 删除 |
| `python/pipeline/stages.py` | `PRStage` → `ExportStage` | 修改 |
| `python/pipeline/models.py` | `PipelineConfig.export` → `social` | 修改 |
| `python/server.py` | `StartBody` 用 `social`，去掉 preset/export 展开 | 修改 |
| `electron/renderer/index.html` | 导出区重做（扁平+液态玻璃） | 修改 |
| `electron/renderer/pipeline.js` | `buildSocialConfig`，移除旧 export 逻辑 | 修改 |
| 各 `tests/test_*.py`、`tests/pipeline.test.js` | 配套测试 | 修改/新建 |

---

## Task 1: export_formats.py — 社媒像素/裁框/校验纯函数

**Files:**
- Modify: `timelapse-tool/python/pipeline/export_formats.py`
- Test: `timelapse-tool/python/tests/test_export_formats.py`

- [ ] **Step 1: 写失败的测试**

在 `tests/test_export_formats.py` 末尾追加：

```python
from pipeline import export_formats as ef


def test_social_pixels_landscape_and_portrait():
    assert ef.social_pixels("16:9", "1080p") == (1920, 1080)
    assert ef.social_pixels("9:16", "1080p") == (1080, 1920)
    assert ef.social_pixels("3:4", "1080p") == (1080, 1440)
    assert ef.social_pixels("3:4", "720p") == (720, 960)
    assert ef.social_pixels("1:1", "1080p") == (1080, 1080)
    assert ef.social_pixels("3:2", "1080p") == (1620, 1080)
    assert ef.social_pixels("16:9", "4K") == (3840, 2160)


def test_social_pixels_always_even():
    for aspect in ef.ASPECT_RATIO:
        for res in ef.SOCIAL_RESOLUTIONS:
            w, h = ef.social_pixels(aspect, res)
            assert w % 2 == 0 and h % 2 == 0


def test_crop_rect_center_portrait_from_3to2():
    # 母版 3840x2560 (3:2)，裁 9:16
    assert ef.crop_rect(3840, 2560, "9:16") == (1200, 0, 1440, 2560)


def test_crop_rect_center_landscape_169():
    assert ef.crop_rect(3840, 2560, "16:9") == (0, 200, 3840, 2160)


def test_crop_rect_square_and_34():
    assert ef.crop_rect(3840, 2560, "1:1") == (640, 0, 2560, 2560)
    assert ef.crop_rect(3840, 2560, "3:4") == (960, 0, 1920, 2560)


def test_crop_rect_native_3to2_is_full_frame():
    assert ef.crop_rect(3840, 2560, "3:2") == (0, 0, 3840, 2560)


def test_validate_social_ok_and_rejects():
    ef.validate_social({"format": "H.265", "aspect": "9:16", "resolution": "1080p"})
    with pytest.raises(ValueError, match="格式"):
        ef.validate_social({"format": "AV1", "aspect": "9:16", "resolution": "1080p"})
    with pytest.raises(ValueError, match="画幅"):
        ef.validate_social({"format": "H.265", "aspect": "21:9", "resolution": "1080p"})
    with pytest.raises(ValueError, match="分辨率"):
        ef.validate_social({"format": "H.265", "aspect": "9:16", "resolution": "8K"})
```

确认文件顶部已 `import pytest`（已有）。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_export_formats.py -q`
Expected: FAIL（`AttributeError: module 'pipeline.export_formats' has no attribute 'social_pixels'`）。

- [ ] **Step 3: 写实现**

在 `pipeline/export_formats.py` 末尾追加：

```python
# ---- 社媒导出维度（唯一事实来源）----

SOCIAL_FORMATS = {"H.265", "H.264"}
# 画幅 → (横向 w:h)
ASPECT_RATIO = {
    "16:9": (16, 9),
    "9:16": (9, 16),
    "3:4": (3, 4),
    "1:1": (1, 1),
    "3:2": (3, 2),
}
# 分辨率档 → 短边像素
SOCIAL_RESOLUTIONS = {"720p": 720, "1080p": 1080, "4K": 2160}

# 格式 → 文件名后缀 / Swift 编码标识
FORMAT_TAG = {"H.265": "h265", "H.264": "h264"}
FORMAT_SWIFT = {"H.265": "hevc", "H.264": "h264"}


def _even(n):
    n = int(round(n))
    return n if n % 2 == 0 else n + 1


def social_pixels(aspect, resolution):
    """画幅+分辨率 → (宽, 高) 偶数像素。短边 = 分辨率档。"""
    a, b = ASPECT_RATIO[aspect]
    short = SOCIAL_RESOLUTIONS[resolution]
    long = short * max(a, b) / min(a, b)
    if a > b:        # 横向：高是短边
        return (_even(long), _even(short))
    if a < b:        # 竖向：宽是短边
        return (_even(short), _even(long))
    return (_even(short), _even(short))  # 方形


def crop_rect(src_w, src_h, aspect):
    """母版中心裁出 aspect 比例的最大矩形 → (x, y, w, h) 偶数。"""
    a, b = ASPECT_RATIO[aspect]
    r = a / b               # 目标横向比
    sr = src_w / src_h
    if abs(r - sr) < 1e-9:  # 与母版同比 → 全画幅不裁
        return (0, 0, _even(src_w), _even(src_h))
    if r > sr:              # 目标更宽 → 按宽定，裁上下
        cw, ch = src_w, src_w / r
    else:                   # 目标更高/窄 → 按高定，裁左右
        cw, ch = src_h * r, src_h
    cw, ch = _even(cw), _even(ch)
    x = _even((src_w - cw) / 2)
    y = _even((src_h - ch) / 2)
    return (x, y, cw, ch)


def validate_social(social):
    if social.get("format") not in SOCIAL_FORMATS:
        raise ValueError(f"格式不支持: {social.get('format')}")
    if social.get("aspect") not in ASPECT_RATIO:
        raise ValueError(f"画幅不支持: {social.get('aspect')}")
    if social.get("resolution") not in SOCIAL_RESOLUTIONS:
        raise ValueError(f"分辨率不支持: {social.get('resolution')}")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_export_formats.py -q`
Expected: PASS（新增 7 个全过；旧的 PRESETS/validate_export 测试仍在，下个 task 才动）。

- [ ] **Step 5: 提交**

```bash
git add timelapse-tool/python/pipeline/export_formats.py timelapse-tool/python/tests/test_export_formats.py
git commit -m "feat: 社媒导出像素/中心裁框/校验纯函数"
```

---

## Task 2: media_export.swift — AVFoundation 转码 + 探尺寸

**Files:**
- Create: `timelapse-tool/python/pipeline/media_export.swift`

无单测（外部工具）；本 task 仅编译验证，运行验证在 Task 7 实机。

- [ ] **Step 1: 写 Swift 工具**

创建 `timelapse-tool/python/pipeline/media_export.swift`：

```swift
// media_export —— 把 ProRes 母版按裁框+目标尺寸转成 H.265/H.264（社媒版）。
//
// 用法:
//   media_export --probe <src>                          # 打印母版尺寸 "W H"
//   media_export <src> <out> <hevc|h264> <cx> <cy> <cw> <ch> <ow> <oh>
//
// 裁框(cx,cy,cw,ch) 由 Python 中心裁算好；这里只把该区域映射到 ow×oh 输出。
// 用 AVAssetExportSession + AVMutableVideoComposition：renderSize=输出尺寸，
// layerInstruction transform = 平移(-裁原点) 再缩放(输出/裁框)。

import AVFoundation
import Foundation

func fail(_ msg: String) -> Never {
    FileHandle.standardError.write((msg + "\n").data(using: .utf8)!)
    exit(1)
}

let args = CommandLine.arguments

// --probe 模式
if args.count == 3 && args[1] == "--probe" {
    let asset = AVURLAsset(url: URL(fileURLWithPath: args[2]))
    let sem = DispatchSemaphore(value: 0)
    Task {
        guard let t = try? await asset.loadTracks(withMediaType: .video).first,
              let size = try? await t.load(.naturalSize) else { fail("无法读取母版尺寸") }
        print("\(Int(abs(size.width))) \(Int(abs(size.height)))")
        sem.signal()
    }
    sem.wait()
    exit(0)
}

guard args.count == 10 else {
    fail("用法: media_export <src> <out> <hevc|h264> <cx> <cy> <cw> <ch> <ow> <oh>")
}
let src = args[1], outPath = args[2], fmt = args[3]
let cx = Double(args[4])!, cy = Double(args[5])!, cw = Double(args[6])!, ch = Double(args[7])!
let ow = Int(args[8])!, oh = Int(args[9])!

let preset: String
switch fmt {
case "hevc": preset = AVAssetExportPresetHEVCHighestQuality
case "h264": preset = AVAssetExportPresetHighestQuality
default: fail("未知格式: \(fmt)")
}

let asset = AVURLAsset(url: URL(fileURLWithPath: src))
let done = DispatchSemaphore(value: 0)
Task {
    guard let track = try? await asset.loadTracks(withMediaType: .video).first else {
        fail("母版无视频轨")
    }
    let fps = (try? await track.load(.nominalFrameRate)) ?? 60

    let vc = AVMutableVideoComposition()
    vc.renderSize = CGSize(width: ow, height: oh)
    vc.frameDuration = CMTime(value: 1, timescale: CMTimeScale(fps.rounded()))

    let instruction = AVMutableVideoCompositionInstruction()
    let dur = (try? await asset.load(.duration)) ?? .zero
    instruction.timeRange = CMTimeRange(start: .zero, duration: dur)

    let layer = AVMutableVideoCompositionLayerInstruction(assetTrack: track)
    let sx = Double(ow) / cw, sy = Double(oh) / ch
    let transform = CGAffineTransform(translationX: -cx, y: -cy)
        .concatenating(CGAffineTransform(scaleX: sx, y: sy))
    layer.setTransform(transform, at: .zero)
    instruction.layerInstructions = [layer]
    vc.instructions = [instruction]

    guard let export = AVAssetExportSession(asset: asset, presetName: preset) else {
        fail("无法创建导出会话")
    }
    let outURL = URL(fileURLWithPath: outPath)
    try? FileManager.default.removeItem(at: outURL)
    export.outputURL = outURL
    export.outputFileType = .mp4
    export.videoComposition = vc

    await withCheckedContinuation { (c: CheckedContinuation<Void, Never>) in
        export.exportAsynchronously { c.resume() }
    }
    if export.status == .completed { done.signal() }
    else { fail("导出失败: \(export.error?.localizedDescription ?? "未知")") }
}
done.wait()
exit(0)
```

- [ ] **Step 2: 编译验证**

Run:
```bash
cd timelapse-tool/python/pipeline && swiftc -O media_export.swift -o /tmp/media_export_test 2>&1 | grep -v "warning:" | grep -v "deprecated" | head
```
Expected: 无 error 输出，`/tmp/media_export_test` 生成。验证 probe：
```bash
/tmp/media_export_test --probe ~/Desktop/tl_out_full/_ae_intermediate.mov
```
Expected: 打印类似 `3840 2560`（若母版还在）。

- [ ] **Step 3: 提交**

```bash
git add timelapse-tool/python/pipeline/media_export.swift
git commit -m "feat: media_export.swift（AVFoundation 转社媒版 + 探尺寸）"
```

---

## Task 3: export.py — 编排（替代 pr.py）

**Files:**
- Create: `timelapse-tool/python/pipeline/export.py`
- Delete: `timelapse-tool/python/pipeline/pr.py`
- Test: `timelapse-tool/python/tests/test_export.py`（新建）
- Delete: `timelapse-tool/python/tests/test_pr.py`

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_export.py`：

```python
from pathlib import Path

import pytest

from pipeline import export

_MOOV = b"\x00\x00\x00\x08moov" + b"\x00" * 1100


def test_master_path():
    assert export.master_path("/out").name == "timelapse_master.mov"


def test_social_output_path_named_by_pixels_and_fmt():
    p = export.social_output_path("/out", "H.265", 1080, 1920)
    assert p.name == "timelapse_social_1080x1920_h265.mp4"


def test_build_export_cmd_order():
    cmd = export.build_export_cmd(
        "/x/bin", "/m.mov", "/s.mp4", "hevc", (1200, 0, 1440, 2560), (1080, 1920))
    assert cmd == ["/x/bin", "/m.mov", "/s.mp4", "hevc",
                   "1200", "0", "1440", "2560", "1080", "1920"]


def test_build_probe_cmd():
    assert export.build_probe_cmd("/x/bin", "/m.mov") == ["/x/bin", "--probe", "/m.mov"]


def test_render_exports_keeps_master_then_transcodes(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    inter = out / "_ae_intermediate.mov"; inter.write_bytes(_MOOV)
    fake_bin = tmp_path / "bin"; fake_bin.write_text("b")
    social = {"format": "H.265", "aspect": "9:16", "resolution": "1080p"}
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        class R:
            returncode = 0
            stdout = "3840 2560\n"   # probe 返回母版尺寸
        if cmd[1] != "--probe":
            Path(cmd[2]).write_bytes(_MOOV)  # 转码产出社媒版
        return R()

    master, social_out = export.render_exports(
        str(inter), str(out), social, emit=lambda m: None,
        run=fake_run, binary=str(fake_bin))

    assert master == export.master_path(str(out)) and master.exists()
    assert not inter.exists()                       # 母版是“移动”得到的
    assert social_out.name == "timelapse_social_1080x1920_h265.mp4" and social_out.exists()
    # 先 probe 母版，再转码；裁框来自 crop_rect(3840,2560,"9:16")
    assert calls[0][1] == "--probe"
    tc = calls[-1]
    assert tc[3] == "hevc"
    assert tc[4:8] == ["1200", "0", "1440", "2560"]
    assert tc[8:10] == ["1080", "1920"]


def test_render_exports_missing_intermediate_raises(tmp_path):
    with pytest.raises(RuntimeError, match="中间视频"):
        export.render_exports(
            str(tmp_path / "nope.mov"), str(tmp_path), {"format": "H.265"},
            emit=lambda m: None, run=lambda c, **k: None, binary="b")


def test_render_exports_missing_social_output_raises(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    inter = out / "_ae_intermediate.mov"; inter.write_bytes(_MOOV)
    fake_bin = tmp_path / "bin"; fake_bin.write_text("b")
    social = {"format": "H.265", "aspect": "9:16", "resolution": "1080p"}

    def fake_run(cmd, **kw):
        class R:
            returncode = 0
            stdout = "3840 2560\n"
        return R()  # 不产出社媒版文件

    with pytest.raises(RuntimeError, match="社媒"):
        export.render_exports(str(inter), str(out), social,
                              emit=lambda m: None, run=fake_run, binary=str(fake_bin))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_export.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'pipeline.export'`）。

- [ ] **Step 3: 写实现**

创建 `pipeline/export.py`：

```python
"""导出阶段：保留 ProRes 母版 + 用 AVFoundation 出社媒版（替代 Premiere PR）。

裁切/缩放数学在 export_formats（纯函数、可单测）；media_export.swift 只执行。
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

from pipeline import export_formats as ef

EXPORT_SWIFT = Path(__file__).parent / "media_export.swift"
EXPORT_BIN = str(Path(tempfile.gettempdir()) / "timelapse_media_export")

MASTER_NAME = "timelapse_master.mov"


def master_path(output_dir):
    return Path(output_dir) / MASTER_NAME


def social_output_path(output_dir, fmt, w, h):
    tag = ef.FORMAT_TAG[fmt]
    return Path(output_dir) / f"timelapse_social_{w}x{h}_{tag}.mp4"


def build_probe_cmd(binary, src):
    return [binary, "--probe", src]


def build_export_cmd(binary, src, out, fmt_swift, crop, outsize):
    cx, cy, cw, ch = crop
    ow, oh = outsize
    return [binary, src, out, fmt_swift,
            str(cx), str(cy), str(cw), str(ch), str(ow), str(oh)]


def ensure_export_binary(run=subprocess.run, binary=EXPORT_BIN, source=EXPORT_SWIFT):
    if Path(binary).exists():
        return binary
    r = run(["swiftc", "-O", str(source), "-o", binary])
    if getattr(r, "returncode", 0) != 0 or not Path(binary).exists():
        raise RuntimeError("无法编译 media_export（swiftc）")
    return binary


def probe_master_size(binary, master, run=subprocess.run):
    r = run(build_probe_cmd(binary, str(master)), capture_output=True, text=True)
    if getattr(r, "returncode", 0) != 0:
        raise RuntimeError("无法探测母版尺寸")
    w, h = r.stdout.split()
    return int(w), int(h)


def render_exports(intermediate_video, output_dir, social, emit,
                   run=subprocess.run, binary=EXPORT_BIN):
    """保留母版 + 出社媒版。返回 (母版路径, 社媒版路径)。"""
    inter = Path(intermediate_video)
    if not inter.exists():
        raise RuntimeError(f"AE 中间视频不存在: {inter}")
    ef.validate_social(social)

    # ① 保留母版（移动，省空间；母版本身就是 ProRes 4444）
    master = master_path(output_dir)
    emit("导出阶段：保留 ProRes 母版…")
    if master.exists():
        master.unlink()
    shutil.move(str(inter), str(master))

    # ② 社媒版：探母版尺寸 → 中心裁框 → 目标像素 → 转码
    bin_path = ensure_export_binary(run=run, binary=binary)
    src_w, src_h = probe_master_size(bin_path, master, run=run)
    crop = ef.crop_rect(src_w, src_h, social["aspect"])
    ow, oh = ef.social_pixels(social["aspect"], social["resolution"])
    fmt_swift = ef.FORMAT_SWIFT[social["format"]]
    social_out = social_output_path(output_dir, social["format"], ow, oh)
    if social_out.exists():
        social_out.unlink()

    emit(f"导出阶段：转社媒版 {ow}x{oh} · {social['format']}…")
    run(build_export_cmd(bin_path, str(master), str(social_out), fmt_swift, crop, (ow, oh)))
    if not social_out.exists():
        raise RuntimeError(f"未生成社媒版: {social_out}")
    emit("导出阶段：完成（母版 + 社媒版）")
    return master, social_out
```

- [ ] **Step 4: 删除 pr.py 与其测试**

```bash
git rm timelapse-tool/python/pipeline/pr.py timelapse-tool/python/tests/test_pr.py
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_export.py -q`
Expected: PASS（7 个）。此时 `test_stages.py`/`test_pipeline_api.py` 仍引用 `pr`，下个 task 修。

- [ ] **Step 6: 提交**

```bash
git add timelapse-tool/python/pipeline/export.py timelapse-tool/python/tests/test_export.py
git commit -m "feat: export.py 导出编排（保留母版+AVFoundation 社媒版），移除 pr.py"
```

---

## Task 4: stages.py — PRStage → ExportStage

**Files:**
- Modify: `timelapse-tool/python/pipeline/stages.py:65-81`
- Test: `timelapse-tool/python/tests/test_stages.py`

- [ ] **Step 1: 改测试**

编辑 `tests/test_stages.py`：把 import 行与 `test_pr_stage_delegates_to_render` 替换。

import 行改为：
```python
from pipeline.stages import BRStage, LRTStage, AEStage, ExportStage, default_stages
```

`test_default_stages_order` 改为：
```python
def test_default_stages_order():
    names = [s.name for s in default_stages()]
    assert names == ["BR", "LRT", "AE", "导出"]
```

`test_br_and_lrt_are_manual` 里 `PRStage().manual` 改为 `ExportStage().manual`。

把 `test_pr_stage_delegates_to_render` 整个替换为：
```python
def test_export_stage_delegates(monkeypatch, tmp_path):
    from pipeline import ae, export
    called = {}

    def fake_render(intermediate_video, output_dir, social, emit, **kwargs):
        called["inter"] = intermediate_video
        called["out"] = output_dir
        called["social"] = social
        emit("导出 done")
        return (export.master_path(output_dir), tmp_path / "s.mp4")

    monkeypatch.setattr(export, "render_exports", fake_render)

    class Cfg:
        output_path = str(tmp_path / "out")
        social = {"format": "H.265", "aspect": "9:16", "resolution": "1080p"}

    msgs = []
    ExportStage().run(Cfg(), msgs.append)
    assert called["inter"] == str(ae.intermediate_path(str(tmp_path / "out")))
    assert called["social"]["aspect"] == "9:16"
    assert any("导出" in m for m in msgs)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_stages.py -q`
Expected: FAIL（`ImportError: cannot import name 'ExportStage'`）。

- [ ] **Step 3: 改实现**

编辑 `pipeline/stages.py`：把 `PRStage` 类整体替换为：

```python
class ExportStage(Stage):
    name = "导出"
    manual = False

    def run(self, config, emit):
        from pipeline import ae, export
        intermediate = ae.intermediate_path(config.output_path)
        export.render_exports(
            intermediate_video=str(intermediate),
            output_dir=config.output_path,
            social=config.social,
            emit=emit,
        )
```

并把 `default_stages` 改为：
```python
def default_stages():
    return [BRStage(), LRTStage(), AEStage(), ExportStage()]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_stages.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add timelapse-tool/python/pipeline/stages.py timelapse-tool/python/tests/test_stages.py
git commit -m "feat: ExportStage 替代 PRStage（流水线末位改导出阶段）"
```

---

## Task 5: models.py / server.py — config 用 social

**Files:**
- Modify: `timelapse-tool/python/pipeline/models.py`
- Modify: `timelapse-tool/python/server.py`
- Test: `timelapse-tool/python/tests/test_models.py`、`tests/test_pipeline_api.py`、`tests/test_workflows.py`

- [ ] **Step 1: 看依赖 export 字段的工作流构造**

Run: `grep -rn "config.export\|\.export\b\|build_stages\|workflow" timelapse-tool/python/pipeline/workflows.py timelapse-tool/python/server.py | head`
确认 `workflows.build_stages` 用阶段名映射（`PR`/`导出`），下面据此改。

- [ ] **Step 2: 改 models 测试**

编辑 `tests/test_models.py`：把构造 `PipelineConfig` 的 `export=...` 改为 `social=...`，并把校验断言改为社媒校验。具体：找到含 `export={...}` 的用例，替换该 kwarg 为：
```python
        social={"format": "H.265", "aspect": "9:16", "resolution": "1080p"},
```
若有断言 `validate_export` 报错的用例，改为构造非法 social（如 `"format": "AV1"`）并 `match="格式"`。

- [ ] **Step 3: 运行确认失败**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_models.py -q`
Expected: FAIL（`PipelineConfig` 仍要求 `export`）。

- [ ] **Step 4: 改 models 实现**

编辑 `pipeline/models.py`：
- import 行 `from pipeline.export_formats import validate_export` 改为 `from pipeline.export_formats import validate_social`。
- `PipelineConfig` 的 `export: dict` 字段改名为 `social: dict`。
- `validate()` 里 `validate_export(self.export)` 改为 `validate_social(self.social)`。

- [ ] **Step 5: 改 server**

编辑 `server.py`：
- `StartBody`：把 `export: Optional[dict] = None` 与 `preset: Optional[str] = None` 两个字段删除，新增 `social: dict`。
- `pipeline_start` 里删除 preset→export 展开那段（`workflow_names`/`preset` 相关到 `data["export"] = expand_preset(preset)` 的 try 块），改为直接构造：
```python
@app.post("/pipeline/start")
def pipeline_start(body: StartBody):
    global _runner
    data = body.dict()
    workflow_names = data.pop("workflow", None)
    config = PipelineConfig(**data)
    notice = None
    try:
        original = config.raw_folder
        repaired = sequence.repair(original)
        if repaired != original:
            n = len(sequence._frames(repaired))
            config.raw_folder = repaired
            notice = f"检测到序列回绕，已按拍摄时间整理 {n} 帧到「{repaired}」，请在该文件夹操作。"
    except Exception:
        pass
    try:
        stages = workflows.build_stages(workflow_names) if workflow_names else default_stages()
        _runner = PipelineRunner(stages=stages, emit=_progress_log.append)
        _runner.start(config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _runner._notice = notice
    return _runner.status()
```
- 删除文件顶部 `from pipeline.export_formats import PRESETS` 与 `/export/presets` 路由（社媒维度走前端固定枚举，不再用 PRESETS）。同时删除 `export_formats.py` 里的 `PRESETS`/`expand_preset`/`validate_export`/相关旧常量？**不删**——保留以免其他测试引用；仅停止在 server 用。若 `grep PRESETS` 仅剩定义与其自身测试，可在本 task 末顺手删定义与 `test_export_formats.py` 中旧 PRESETS 用例。

- [ ] **Step 6: 改 API 测试**

编辑 `tests/test_pipeline_api.py`：所有 `body = dict(... export=...|preset=...)` 改为带 `social={"format":"H.265","aspect":"9:16","resolution":"1080p"}` 且去掉 `export`/`preset`。把对 `pr.render_final` 的 monkeypatch 改为 `export.render_exports`：
```python
    from pipeline import ae, export
    monkeypatch.setattr(ae, "render_sequence",
                        lambda seq_folder, output_dir, fps, emit, **kw: emit("AE"))
    monkeypatch.setattr(ae, "merge_chunks",
                        lambda chunks, output_dir, emit, **kw: emit("merge"))
    monkeypatch.setattr(export, "render_exports",
                        lambda intermediate_video, output_dir, social, emit, **kw: emit("EXPORT"))
```
删除 `test_get_export_presets` 与 `test_pipeline_start_with_preset`（preset 概念已移除）。`test_default_stages`/工作流相关里 `"PR"` 改 `"导出"`（若有）。

- [ ] **Step 7: 改 workflows**

编辑 `pipeline/workflows.py` 与 `workflows.json`：阶段名 `"PR"` 全改为 `"导出"`；`build_stages` 的名称→类映射把 `PR`/`PRStage` 改 `导出`/`ExportStage`。编辑 `tests/test_workflows.py` 中 `"PR"` → `"导出"`。

Run: `grep -rn '"PR"\|PRStage' timelapse-tool/python` 确认无残留（除历史 spec/plan 文档）。

- [ ] **Step 8: 运行全套测试**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest -q`
Expected: 全 PASS。

- [ ] **Step 9: 提交**

```bash
git add -A timelapse-tool/python
git commit -m "feat: config/server/workflows 改用 social，移除 Premiere preset 概念"
```

---

## Task 6: UI 导出区重做（扁平 + 液态玻璃）

**Files:**
- Modify: `timelapse-tool/electron/renderer/index.html`
- Modify: `timelapse-tool/electron/renderer/pipeline.js`
- Test: `timelapse-tool/tests/pipeline.test.js`

- [ ] **Step 1: 写失败的 JS 测试**

编辑 `tests/pipeline.test.js`：把顶部 require 增补 `buildSocialConfig`，并删除/替换 `buildExportConfig` 相关用例。追加：
```javascript
const { buildSocialConfig, socialPixels } = require("../electron/renderer/pipeline.js");

test("buildSocialConfig 取三个下拉值", () => {
  expect(buildSocialConfig({ social_format: "H.265", social_aspect: "9:16", social_resolution: "1080p" }))
    .toEqual({ format: "H.265", aspect: "9:16", resolution: "1080p" });
});

test("socialPixels 与后端同口径", () => {
  expect(socialPixels("9:16", "1080p")).toEqual([1080, 1920]);
  expect(socialPixels("3:4", "720p")).toEqual([720, 960]);
  expect(socialPixels("3:2", "1080p")).toEqual([1620, 1080]);
});
```
若旧文件 require 了 `buildExportConfig`，从解构里移除它，并删除 `buildExportConfig`/preset 相关旧测试用例。

- [ ] **Step 2: 运行确认失败**

Run: `cd timelapse-tool && export PATH="$HOME/.local/node/bin:$PATH" && npm test -- pipeline.test.js`
Expected: FAIL（`buildSocialConfig is not a function`）。

- [ ] **Step 3: 改 pipeline.js**

编辑 `pipeline/.../pipeline.js`：

a) 删除 `CONTAINER` 常量与 `buildExportConfig` 函数。

b) 新增（放在文件上部工具区）：
```javascript
const SOCIAL_RATIO = { "16:9": [16, 9], "9:16": [9, 16], "3:4": [3, 4], "1:1": [1, 1], "3:2": [3, 2] };
const SOCIAL_SHORT = { "720p": 720, "1080p": 1080, "4K": 2160 };

function _even(n) { n = Math.round(n); return n % 2 === 0 ? n : n + 1; }

function socialPixels(aspect, resolution) {
  const [a, b] = SOCIAL_RATIO[aspect];
  const short = SOCIAL_SHORT[resolution];
  const long = short * Math.max(a, b) / Math.min(a, b);
  if (a > b) return [_even(long), _even(short)];
  if (a < b) return [_even(short), _even(long)];
  return [_even(short), _even(short)];
}

function buildSocialConfig(values) {
  return { format: values.social_format, aspect: values.social_aspect, resolution: values.social_resolution };
}
```

c) `readForm()` 增加三字段：
```javascript
    social_format: id("social_format").value,
    social_aspect: id("social_aspect").value,
    social_resolution: id("social_resolution").value,
```

d) `buildStartBody()`：删除 `export_mode`/`preset`/`manual` 分支，改为：
```javascript
  function buildStartBody() {
    const payload = buildStartPayload(readForm());
    payload.social = buildSocialConfig(readForm());
    payload.workflow = workflowMap[id("workflow_select").value] || null;
    return payload;
  }
```

e) 删除 `initPipeline` 中加载 `/export/presets`、`syncExportMode`、`syncManualCodec` 的整段逻辑（这些 DOM 已移除）。新增社媒预览联动：
```javascript
  function syncSocialPreview() {
    const [w, h] = socialPixels(id("social_aspect").value, id("social_resolution").value);
    const tag = id("social_format").value === "H.265" ? "h265" : "h264";
    id("social-preview").textContent = `${w}×${h} · ${id("social_format").value} · timelapse_social_${w}x${h}_${tag}.mp4`;
  }
  ["social_format", "social_aspect", "social_resolution"].forEach((x) =>
    id(x).addEventListener("change", syncSocialPreview));
  syncSocialPreview();
```

f) 文件底部 `module.exports` 增加 `buildSocialConfig, socialPixels`，移除 `buildExportConfig`。

- [ ] **Step 4: 改 index.html 导出区**

编辑 `index.html`：把从 `<div class="field"><label>导出模式</label>...` 到 `manual-fields` 结束的整块（导出模式/预设/手动编码字段）替换为：
```html
        <div class="field">
          <label>母版</label>
          <div class="hint-line">自动保留 ProRes 母版 → timelapse_master.mov</div>
        </div>
        <div class="row">
          <div class="field">
            <label>社媒格式</label>
            <select id="social_format">
              <option value="H.265">H.265（更小）</option>
              <option value="H.264">H.264（最兼容）</option>
            </select>
          </div>
          <div class="field">
            <label>画幅</label>
            <select id="social_aspect">
              <option value="9:16">9:16 竖（抖音/小红书）</option>
              <option value="3:4">3:4 竖（小红书）</option>
              <option value="16:9">16:9 横（B站/横屏）</option>
              <option value="1:1">1:1 方</option>
              <option value="3:2">3:2 原始（不裁）</option>
            </select>
          </div>
          <div class="field">
            <label>分辨率</label>
            <select id="social_resolution">
              <option value="1080p">1080p</option>
              <option value="720p">720p</option>
              <option value="4K">4K</option>
            </select>
          </div>
        </div>
        <div id="social-preview" class="hint-line"></div>
```

> 注意：删掉旧 `export_mode`/`export_preset`/`manual_codec`/`prores_profile`/`bitrate`/`h264_quality`/`h265_bit_depth` 等元素，避免 `pipeline.js` 引用已删 DOM。

- [ ] **Step 5: 加样式（复用液态玻璃语言）**

编辑 `style.css`：若无 `.hint-line` 则追加（沿用现有 notice 小字风格）：
```css
.hint-line { font-size: 12px; opacity: 0.6; margin-top: 4px; }
```

- [ ] **Step 6: 运行 JS 测试通过**

Run: `cd timelapse-tool && export PATH="$HOME/.local/node/bin:$PATH" && npm test`
Expected: 全 PASS。

- [ ] **Step 7: 提交**

```bash
git add timelapse-tool/electron timelapse-tool/tests/pipeline.test.js
git commit -m "feat: 导出区 UI 改社媒版配置（格式/画幅/分辨率，扁平+液态玻璃）"
```

---

## Task 7: 实机验证 + 收尾

**Files:** 无（验证）。需装有 AVFoundation（macOS 自带）与一段真实母版。

- [ ] **Step 1: 编译正式二进制**

Run:
```bash
cd timelapse-tool/python/pipeline && swiftc -O media_export.swift -o "$TMPDIR/timelapse_media_export"
```
Expected: 仅 deprecation 警告，无 error。

- [ ] **Step 2: 用真实母版转一版社媒版**

```bash
cd timelapse-tool/python && .venv/bin/python -c "
from pipeline import export
m, s = export.render_exports(
    '$HOME/Desktop/tl_out_full/_ae_intermediate.mov'.replace('\$HOME','$HOME'),
    '$HOME/Desktop/tl_out_full', 
    {'format':'H.265','aspect':'9:16','resolution':'1080p'}, emit=print)
print('master:', m); print('social:', s)
"
```
> 若母版已被前面移动成 `timelapse_master.mov`，把第一个参数指向它，并注意 `render_exports` 会再 move——验证时可先复制一份中间视频。
Expected: 生成 `timelapse_social_1080x1920_h265.mp4`。

- [ ] **Step 3: 探测社媒版**

```bash
/tmp/probe_fps ~/Desktop/tl_out_full/timelapse_social_1080x1920_h265.mp4
```
Expected: `nominalFrameRate=60.0`，时长 ≈ 母版（11.6s）。用 QuickTime 打开确认：尺寸 1080×1920、中心裁构图合理、明显比母版小。

- [ ] **Step 4: 全套自动化测试回归**

```bash
cd timelapse-tool/python && .venv/bin/python -m pytest -q
cd timelapse-tool && export PATH="$HOME/.local/node/bin:$PATH" && npm test
```
Expected: 全 PASS。

- [ ] **Step 5: 提交（如有验证产生的清理）**

```bash
git add -A && git commit -m "chore: 社媒导出实机验证通过" || echo "无改动"
```

---

## Self-Review Notes

- **Spec 覆盖**：① 保留母版（Task 3 render_exports move）② 社媒版自由组合格式/画幅/分辨率（Task 1 像素表 + Task 6 UI）③ 中心裁切（Task 1 crop_rect）④ AVFoundation 替 Premiere（Task 2/3，删 pr.py）⑤ Python 算数学 Swift 执行（Task 1 纯函数 + Task 2 probe/transcode）⑥ UI 扁平+液态玻璃（Task 6 复用 .glass/.field/.hint-line）⑦ 文件命名（Task 3）。均有对应任务。
- **类型一致**：`render_exports(intermediate_video, output_dir, social, emit, run, binary)` 在 Task 3/4/5 调用签名一致；`social` 字段贯穿 models/server/stages/export 一致；`FORMAT_TAG`（文件名 h265/h264）与 `FORMAT_SWIFT`（hevc/h264）分开且各处引用正确。
- **占位符**：无 TODO/TBD；Swift `args[9]` 读取在 Task 2 Step 2 已修正为干净版本。
- **已知实机风险**：母版 `preferredTransform` 假设为 identity（AE 输出标准 mov，成立）；`HEVCHighestQuality`+`.mp4`+自定义 `renderSize` 组合需实机确认（Task 7）。
- **YAGNI**：本期单社媒版、中心裁、系统码率；裁切位置/多版本/码率控制留接口位不实现。
```
