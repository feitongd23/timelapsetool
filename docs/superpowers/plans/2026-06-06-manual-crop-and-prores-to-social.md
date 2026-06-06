# 运镜手动选区 + 成片转社媒 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ken Burns 放大终点可手动框选；新增「成片转社媒」tab 把任意 ProRes 成片直接转社媒版。

**Architecture:** 把社媒转码拆成可复用的 `transcode_social(src, out_dir, social, prefix)`，流水线与新 tab 共用；`motion_frames` 加 `box` 分支（从全幅推近到框选区域）；前端选区 modal 在源首帧缩略图上拖框得归一化 box。Swift `media_export` 不改（已支持起止框 ramp）。

**Tech Stack:** Python 3.9 + pytest（后端纯函数/编排），Electron + Jest/jsdom（前端），qlmanage（缩略图）。

测试：`cd timelapse-tool/python && .venv/bin/python -m pytest`；`cd timelapse-tool && export PATH="$HOME/.local/node/bin:$PATH" && npm test`。

---

## File Structure

| 文件 | 改动 |
|------|------|
| `python/pipeline/export_formats.py` | `motion_frames` 加 box 分支 + `_box_to_aspect_frame` |
| `python/pipeline/export.py` | `social_output_path` 加 `prefix`；拆出 `transcode_social`（含 box 锚点）；`render_exports` 改调它 |
| `python/server.py` | `GET /preview/file_thumb`；`POST /export/social_from` |
| `python/tests/test_export_formats.py`、`test_export.py`、`test_pipeline_api.py` | 配套测试 |
| `electron/main.js`、`preload.js` | `choose-file` IPC + `chooseFile` |
| `electron/renderer/pipeline.js` | box 坐标转换、`buildMotionConfig` 带 box、选区 modal、Ken Burns 显示选区按钮 |
| `electron/renderer/index.html` | 选区 modal 容器；第三个 tab + panel |
| `electron/renderer/social_tab.js`（新） | 成片转社媒 tab 初始化与提交 |
| `electron/renderer/app.js` | 注册第三个 tab 切换 + 初始化 social_tab |
| `tests/pipeline.test.js` | box 坐标转换 + buildSocialConfig 带 box |

---

## Task 1: motion_frames 的 box 分支（纯函数）

**Files:**
- Modify: `timelapse-tool/python/pipeline/export_formats.py`
- Test: `timelapse-tool/python/tests/test_export_formats.py`

- [ ] **Step 1: 写失败的测试**（追加到 `tests/test_export_formats.py` 末尾）

```python
def test_box_to_aspect_frame_contains_box_and_aspect():
    # 母版 3840x2560；box 居中偏左小框，目标 9:16
    fr = ef._box_to_aspect_frame([0.3, 0.3, 0.2, 0.2], 3840, 2560, "9:16")
    x, y, w, h = fr
    # 9:16 竖：w/h ≈ 9/16
    assert abs((w / h) - (9 / 16)) < 0.02
    assert w % 2 == 0 and h % 2 == 0
    assert 0 <= x and x + w <= 3840 and 0 <= y and y + h <= 2560


def test_motion_frames_kenburns_box_in_pushes_to_box():
    motion = {"type": "kenburns", "direction": "in", "intensity": "medium",
              "box": [0.3, 0.3, 0.2, 0.2]}
    anchor = (0.4, 0.4)  # box 中心
    start, end = ef.motion_frames(3840, 2560, "9:16", motion, anchor)
    # 推近：结束框比起始框小（放大）
    assert end[2] < start[2] and end[3] < start[3]
    # 结束框中心≈ box 中心 (0.4,0.4)*尺寸
    ecx = (end[0] + end[2] / 2) / 3840
    assert abs(ecx - 0.4) < 0.03


def test_motion_frames_kenburns_box_out_reverses():
    motion = {"type": "kenburns", "direction": "out", "intensity": "medium",
              "box": [0.3, 0.3, 0.2, 0.2]}
    start, end = ef.motion_frames(3840, 2560, "9:16", motion, (0.4, 0.4))
    assert start[2] < end[2]   # out：起小→止大


def test_motion_frames_box_ignored_for_pan():
    motion = {"type": "pan", "direction": "right", "intensity": "medium",
              "box": [0.3, 0.3, 0.2, 0.2]}
    s, e = ef.motion_frames(3840, 2560, "9:16", motion, (0.4, 0.4))
    assert s[0] == 0 and e[0] > 0    # 仍是 pan 行为，未被 box 影响
```

- [ ] **Step 2: 运行确认失败**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_export_formats.py -q`
Expected: FAIL（`_box_to_aspect_frame` 未定义 / kenburns 不认 box）。

- [ ] **Step 3: 写实现**

在 `export_formats.py` 的 `_scale_box` 之后加：

```python
def _box_to_aspect_frame(box, src_w, src_h, aspect):
    """归一化 box → 包含它的最小 aspect 比例框（源像素，偶数、clamp）。"""
    bx, by, bw, bh = box
    pw, ph = bw * src_w, bh * src_h
    cx, cy = (bx + bw / 2) * src_w, (by + bh / 2) * src_h
    a, b = ASPECT_RATIO[aspect]
    r = a / b
    ew = max(pw, ph * r)
    ew, eh = _even(ew), _even(ew / r)
    x = _clamp(_even(cx - ew / 2), 0, _even(src_w - ew))
    y = _clamp(_even(cy - eh / 2), 0, _even(src_h - eh))
    return (x, y, ew, eh)
```

在 `motion_frames` 里，把 `if mtype == "kenburns":` 整段替换为：

```python
    if mtype == "kenburns":
        if motion.get("box"):
            end = _box_to_aspect_frame(motion["box"], src_w, src_h, aspect)
            return (base, end) if motion["direction"] == "in" else (end, base)
        z = INTENSITY_ZOOM[motion["intensity"]]
        small = _scale_box(base, 1.0 / z, src_w, src_h)
        return (base, small) if motion["direction"] == "in" else (small, base)
```

> `base = crop_rect(..., anchor)`，调用方（transcode_social）会把 anchor 设成 box 中心，故起始框（全貌）与结束框（box）同心。

- [ ] **Step 4: 运行确认通过**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_export_formats.py -q`
Expected: PASS（新增 4 个 + 原有全过）。

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app && git add timelapse-tool/python/pipeline/export_formats.py timelapse-tool/python/tests/test_export_formats.py
git commit -m "feat: motion_frames 支持手动 box（Ken Burns 推近到框选区域）"
```

---

## Task 2: 拆出 transcode_social + social_output_path 前缀

**Files:**
- Modify: `timelapse-tool/python/pipeline/export.py`
- Test: `timelapse-tool/python/tests/test_export.py`

- [ ] **Step 1: 写失败的测试**（追加到 `tests/test_export.py` 末尾）

```python
def test_social_output_path_custom_prefix():
    p = export.social_output_path("/out", "H.265", 1080, 1920, prefix="myclip")
    assert p.name == "myclip_social_1080x1920_h265.mp4"


def test_transcode_social_box_anchor(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    src = tmp_path / "clip.mov"; src.write_bytes(_MOOV)
    fake_bin = tmp_path / "bin"; fake_bin.write_text("b")
    social = {"format": "H.265", "aspect": "9:16", "resolution": "1080p",
              "motion": {"type": "kenburns", "direction": "in", "intensity": "medium",
                         "box": [0.3, 0.3, 0.2, 0.2]}}
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if cmd[1] not in ("--probe", "--saliency"):
            Path(cmd[2]).write_bytes(_MOOV)
        return type("R", (), {"returncode": 0, "stdout": "3840 2560\n"})()

    res = export.transcode_social(str(src), str(out), social, emit=lambda m: None,
                                  run=fake_run, binary=str(fake_bin), prefix="clip")
    assert res.name == "clip_social_1080x1920_h265.mp4" and res.exists()
    # 有 box 时不调用 --saliency（box 中心即锚点）
    assert not any(len(c) > 1 and c[1] == "--saliency" for c in calls)
    tc = calls[-1]
    assert tc[4:8] != tc[8:12]   # Ken Burns 起≠止


def test_render_exports_still_keeps_master(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    inter = out / "_ae_intermediate.mov"; inter.write_bytes(_MOOV)
    fake_bin = tmp_path / "bin"; fake_bin.write_text("b")
    social = {"format": "H.265", "aspect": "9:16", "resolution": "1080p"}

    def fake_run(cmd, **kw):
        if cmd[1] not in ("--probe", "--saliency"):
            Path(cmd[2]).write_bytes(_MOOV)
        return type("R", (), {"returncode": 0, "stdout": "3840 2560\n"})()

    master, social_out = export.render_exports(str(inter), str(out), social,
                                               emit=lambda m: None, run=fake_run, binary=str(fake_bin))
    assert master == export.master_path(str(out)) and master.exists()
    assert not inter.exists()
    assert social_out.name == "timelapse_social_1080x1920_h265.mp4" and social_out.exists()
```

- [ ] **Step 2: 运行确认失败**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_export.py -q`
Expected: FAIL（`social_output_path` 无 prefix / `transcode_social` 未定义）。

- [ ] **Step 3: 写实现**

编辑 `export.py`：把 `social_output_path` 改为：

```python
def social_output_path(output_dir, fmt, w, h, prefix="timelapse"):
    tag = ef.FORMAT_TAG[fmt]
    return Path(output_dir) / f"{prefix}_social_{w}x{h}_{tag}.mp4"
```

新增 `transcode_social`（放在 `render_exports` 之前）：

```python
def transcode_social(src_mov, output_dir, social, emit,
                     run=subprocess.run, binary=EXPORT_BIN, prefix="timelapse"):
    """把任意视频按 social 配置转社媒版，返回社媒版路径。流水线与成片转社媒共用。"""
    src = Path(src_mov)
    if not src.exists():
        raise RuntimeError(f"源视频不存在: {src}")
    ef.validate_social(social)
    bin_path = ensure_export_binary(run=run, binary=binary)
    src_w, src_h = probe_master_size(bin_path, src, run=run)

    motion = social.get("motion") or {"type": "none"}
    if motion.get("box"):                      # 手动框中心优先
        bx, by, bw, bh = motion["box"]
        anchor = (bx + bw / 2, by + bh / 2)
    elif social.get("subject"):
        anchor = saliency_center(bin_path, src, run=run)
    else:
        anchor = (0.5, 0.5)

    start_crop, end_crop = ef.motion_frames(src_w, src_h, social["aspect"], motion, anchor)
    ow, oh = ef.social_pixels(social["aspect"], social["resolution"])
    fmt_swift = ef.FORMAT_SWIFT[social["format"]]
    out = social_output_path(output_dir, social["format"], ow, oh, prefix)
    if out.exists():
        out.unlink()
    emit(f"转社媒版 {ow}x{oh} · {social['format']} · 运镜 {motion['type']}…")
    run(build_export_cmd(bin_path, str(src), str(out), fmt_swift, start_crop, end_crop, (ow, oh)))
    if not out.exists():
        raise RuntimeError(f"未生成社媒版: {out}")
    return out
```

把 `render_exports` 的 ② 段（从 `bin_path = ensure_export_binary` 到 `run(build_export_cmd(...))` 及其后校验）整体替换为调用：

```python
def render_exports(intermediate_video, output_dir, social, emit,
                   run=subprocess.run, binary=EXPORT_BIN):
    """保留母版 + 出社媒版。返回 (母版路径, 社媒版路径)。"""
    inter = Path(intermediate_video)
    if not inter.exists():
        raise RuntimeError(f"AE 中间视频不存在: {inter}")
    master = master_path(output_dir)
    emit("导出阶段：保留 ProRes 母版…")
    if master.exists():
        master.unlink()
    shutil.move(str(inter), str(master))
    social_out = transcode_social(str(master), output_dir, social, emit, run=run, binary=binary)
    emit("导出阶段：完成（母版 + 社媒版）")
    return master, social_out
```

- [ ] **Step 4: 运行确认通过**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_export.py -q`
Expected: PASS（含原有 render_exports 测试，因 transcode_social 内部仍 probe→转码、缺输出报错"社媒"）。

> 注：原 `test_render_exports_missing_social_output_raises` 期望 match "社媒"，`transcode_social` 抛 `未生成社媒版` 含"社媒"，仍通过。

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app && git add timelapse-tool/python/pipeline/export.py timelapse-tool/python/tests/test_export.py
git commit -m "refactor: 拆出 transcode_social（流水线/成片转社媒共用）+ 输出名前缀 + box 锚点"
```

---

## Task 3: /preview/file_thumb（通用缩略图，选区底图）

**Files:**
- Modify: `timelapse-tool/python/server.py`
- Test: `timelapse-tool/python/tests/test_pipeline_api.py`

> 复用现有 `preview.generate_thumbnail`（qlmanage 对任意图片/视频出缩略图），无需新函数。

- [ ] **Step 1: 写失败的测试**（追加到 `tests/test_pipeline_api.py` 末尾）

```python
def test_preview_file_thumb_missing_404():
    r = client.get("/preview/file_thumb", params={"src": "/no/such/file.mov"})
    assert r.status_code == 404


def test_preview_file_thumb_ok(tmp_path, monkeypatch):
    src = tmp_path / "clip.mov"; src.write_text("x")
    thumb = tmp_path / "t.png"; thumb.write_bytes(b"\x89PNG\r\n")
    from pipeline import preview
    monkeypatch.setattr(preview, "generate_thumbnail", lambda s, size, cache, **k: str(thumb))
    r = client.get("/preview/file_thumb", params={"src": str(src)})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_pipeline_api.py -q`
Expected: FAIL（404 路由不存在 → 返回 404 但第二个测试拿不到 png；实际首个可能已 404 命中，第二个失败）。

- [ ] **Step 3: 写实现**（`server.py`，加在 `preview_meta` 之后）

```python
@app.get("/preview/file_thumb")
def preview_file_thumb(src: str):
    """任意单个图片/视频文件的缩略图（选区窗口底图）。"""
    if not Path(src).is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    thumb = preview.generate_thumbnail(src, 640, _THUMB_CACHE)
    if not Path(thumb).exists():
        raise HTTPException(status_code=500, detail="缩略图生成失败")
    return FileResponse(thumb, media_type="image/png")
```

- [ ] **Step 4: 运行确认通过**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_pipeline_api.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app && git add timelapse-tool/python/server.py timelapse-tool/python/tests/test_pipeline_api.py
git commit -m "feat: /preview/file_thumb 通用缩略图（选区窗口底图）"
```

---

## Task 4: /export/social_from（成片转社媒后端）

**Files:**
- Modify: `timelapse-tool/python/server.py`
- Test: `timelapse-tool/python/tests/test_pipeline_api.py`

- [ ] **Step 1: 写失败的测试**（追加）

```python
def test_export_social_from_missing_src_404():
    r = client.post("/export/social_from", json={"src": "/no/file.mov", "social": SOCIAL})
    assert r.status_code == 404


def test_export_social_from_ok(tmp_path, monkeypatch):
    src = tmp_path / "clip.mov"; src.write_text("x")
    from pipeline import export
    monkeypatch.setattr(export, "ensure_export_binary", lambda *a, **k: "/bin")
    monkeypatch.setattr(export, "transcode_social",
                        lambda s, out_dir, social, emit, **k: __import__("pathlib").Path(out_dir) / "clip_social_1080x1920_h265.mp4")
    r = client.post("/export/social_from", json={"src": str(src), "social": SOCIAL})
    assert r.status_code == 200
    assert r.json()["output"].endswith("clip_social_1080x1920_h265.mp4")
```

- [ ] **Step 2: 运行确认失败**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_pipeline_api.py -q`
Expected: FAIL（路由不存在）。

- [ ] **Step 3: 写实现**（`server.py`）

`StartBody` 附近加：

```python
class SocialFromBody(BaseModel):
    src: str
    social: dict
```

加在 `preview_file_thumb` 之后：

```python
@app.post("/export/social_from")
def export_social_from(body: SocialFromBody):
    """把已有成片（mov）直接转社媒版，输出到源同目录。"""
    from pipeline import export
    src = Path(body.src)
    if not src.is_file():
        raise HTTPException(status_code=404, detail="成片不存在")
    binary = export.ensure_export_binary()
    try:
        out = export.transcode_social(str(src), str(src.parent), body.social,
                                      emit=_progress_log.append, binary=binary, prefix=src.stem)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"output": str(out)}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest -q`
Expected: 全 PASS。

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app && git add timelapse-tool/python/server.py timelapse-tool/python/tests/test_pipeline_api.py
git commit -m "feat: /export/social_from 成片直接转社媒版"
```

---

## Task 5: Electron 选文件（chooseFile）

**Files:**
- Modify: `timelapse-tool/electron/main.js`
- Modify: `timelapse-tool/electron/preload.js`

> 无自动化测试（Electron 主进程 IPC）；Task 8 实机验证。

- [ ] **Step 1: main.js 加 IPC**

在 `ipcMain.handle("choose-directory", …)` 之后加：

```javascript
ipcMain.handle("choose-file", async () => {
  const result = await dialog.showOpenDialog({
    properties: ["openFile"],
    filters: [{ name: "视频", extensions: ["mov", "mp4", "m4v"] }],
  });
  if (result.canceled || result.filePaths.length === 0) return null;
  return result.filePaths[0];
});
```

- [ ] **Step 2: preload.js 暴露 chooseFile**

在 `preload.js` 的 `contextBridge.exposeInMainWorld("api", { … })` 里，`chooseDirectory` 旁加：

```javascript
  chooseFile: () => ipcRenderer.invoke("choose-file"),
```

- [ ] **Step 3: 提交**

```bash
cd /Users/feitong/photo-app && git add timelapse-tool/electron/main.js timelapse-tool/electron/preload.js
git commit -m "feat: Electron chooseFile（选单个视频文件）"
```

---

## Task 6: 前端 box 坐标转换 + buildSocialConfig 带 box（纯函数）

**Files:**
- Modify: `timelapse-tool/electron/renderer/pipeline.js`
- Test: `timelapse-tool/tests/pipeline.test.js`

- [ ] **Step 1: 写失败的测试**（追加到 `tests/pipeline.test.js`）

```javascript
const { boxToNormalized } = require("../electron/renderer/pipeline.js");

test("boxToNormalized 像素框转归一化并夹紧", () => {
  expect(boxToNormalized({ x: 100, y: 50, w: 200, h: 400 }, 1000, 1000))
    .toEqual([0.1, 0.05, 0.2, 0.4]);
  // 越界夹紧到 [0,1]
  const n = boxToNormalized({ x: -10, y: 0, w: 2000, h: 100 }, 1000, 1000);
  expect(n[0]).toBe(0);
  expect(n[2]).toBe(1);
});

test("buildSocialConfig 带 box（有框时写入 motion.box）", () => {
  const s = buildSocialConfig({
    social_format: "H.265", social_aspect: "9:16", social_resolution: "1080p",
    motion_type: "kenburns", motion_direction: "in", motion_intensity: "medium",
    motion_subject: false, motion_box: [0.3, 0.3, 0.2, 0.2],
  });
  expect(s.motion.box).toEqual([0.3, 0.3, 0.2, 0.2]);
});

test("buildSocialConfig 无 box 时 motion 不含 box", () => {
  const s = buildSocialConfig({
    social_format: "H.265", social_aspect: "9:16", social_resolution: "1080p",
    motion_type: "kenburns", motion_direction: "in", motion_intensity: "medium",
    motion_subject: false, motion_box: null,
  });
  expect(s.motion).not.toHaveProperty("box");
});
```

把顶部 require 那行补上 `boxToNormalized`（与其它解构项并列）。

- [ ] **Step 2: 运行确认失败**

Run: `cd timelapse-tool && export PATH="$HOME/.local/node/bin:$PATH" && npm test -- pipeline.test.js`
Expected: FAIL（`boxToNormalized` 未导出 / box 未进 config）。

- [ ] **Step 3: 改实现**（`pipeline.js`）

在 `socialPixels` 附近加：

```javascript
function boxToNormalized(rect, dispW, dispH) {
  const clamp = (v) => Math.max(0, Math.min(1, v));
  return [clamp(rect.x / dispW), clamp(rect.y / dispH), clamp(rect.w / dispW), clamp(rect.h / dispH)];
}
```

把 `buildMotionConfig` 改为带 box：

```javascript
function buildMotionConfig(values) {
  const m = { type: values.motion_type, direction: values.motion_direction, intensity: values.motion_intensity };
  if (values.motion_box) m.box = values.motion_box;
  return m;
}
```

底部 `module.exports` 增加 `boxToNormalized`。

- [ ] **Step 4: 运行确认通过**

Run: `cd timelapse-tool && export PATH="$HOME/.local/node/bin:$PATH" && npm test`
Expected: 全 PASS。

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app && git add timelapse-tool/electron/renderer/pipeline.js timelapse-tool/tests/pipeline.test.js
git commit -m "feat: box 坐标转换 + buildSocialConfig 带 motion.box"
```

---

## Task 7: 选区 modal + Ken Burns 选区按钮（流水线导出区）

**Files:**
- Modify: `timelapse-tool/electron/renderer/index.html`
- Modify: `timelapse-tool/electron/renderer/pipeline.js`
- Modify: `timelapse-tool/electron/renderer/style.css`

> 拖拽交互手动验证（Task 8）；本任务接通「Ken Burns 显示按钮 → 弹 modal → 框选 → 存 box」。

- [ ] **Step 1: index.html 加 modal 容器 + 选区按钮**

在运镜 `<div class="row">…强度…</div>` 之后、`motion_subject` 开关之前，加：

```html
        <div id="motion-box-row" class="field hidden">
          <button type="button" id="btn-pick-box" class="btn-browse">选放大区域…</button>
          <span id="motion-box-hint" class="hint-line"></span>
        </div>
```

在 `</main>` 之前加全局 modal：

```html
  <div id="crop-modal" class="modal hidden">
    <div class="modal-card glass">
      <div class="modal-head">框选放大区域（Ken Burns 终点）</div>
      <div id="crop-stage" class="crop-stage">
        <img id="crop-img" alt="底图" />
        <div id="crop-box" class="crop-box"></div>
      </div>
      <div class="modal-actions">
        <button type="button" id="crop-reset" class="btn btn-ghost">重置为自动</button>
        <button type="button" id="crop-cancel" class="btn btn-ghost">取消</button>
        <button type="button" id="crop-ok" class="btn btn-primary">确定</button>
      </div>
    </div>
  </div>
```

- [ ] **Step 2: style.css 加 modal/选框样式**（追加到末尾）

```css
.modal { position: fixed; inset: 0; z-index: 50; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,0.45); }
.modal-card { padding: 18px; max-width: 80vw; max-height: 86vh; display: flex; flex-direction: column; gap: 12px; }
.modal-head { font-weight: 600; }
.crop-stage { position: relative; display: inline-block; max-width: 72vw; max-height: 66vh; overflow: hidden; }
.crop-stage img { display: block; max-width: 72vw; max-height: 66vh; user-select: none; -webkit-user-drag: none; }
.crop-box { position: absolute; border: 2px solid var(--accent); background: rgba(0,122,255,0.15); cursor: move; }
.modal-actions { display: flex; gap: 10px; justify-content: flex-end; }
```

- [ ] **Step 3: pipeline.js 接通选区**

在 `syncMotion()` 里（运镜类型联动），追加显示/隐藏选区按钮的逻辑——在 `syncMotion` 函数体末尾加：

```javascript
    id("motion-box-row").classList.toggle("hidden", type !== "kenburns");
```

在 `initPipeline` 内、`syncMotion()` 调用之后，加选区状态 + modal 逻辑：

```javascript
  let pickedBox = null;  // 归一化 [x,y,w,h] 或 null

  function refreshBoxHint() {
    id("motion-box-hint").textContent = pickedBox ? "已框选放大区域" : "未选（自动）";
  }
  refreshBoxHint();

  function openCropModal(thumbSrc) {
    const modal = id("crop-modal"), img = id("crop-img"), boxEl = id("crop-box");
    img.src = thumbSrc;
    modal.classList.remove("hidden");
    img.onload = () => {
      // 默认框：居中 50%
      const w = img.clientWidth, h = img.clientHeight;
      let rect = { x: w * 0.25, y: h * 0.25, w: w * 0.5, h: h * 0.5 };
      const draw = () => { boxEl.style.left = rect.x + "px"; boxEl.style.top = rect.y + "px"; boxEl.style.width = rect.w + "px"; boxEl.style.height = rect.h + "px"; };
      draw();
      let drag = null;
      boxEl.onmousedown = (e) => { drag = { sx: e.clientX, sy: e.clientY, ox: rect.x, oy: rect.y }; e.preventDefault(); };
      window.onmousemove = (e) => {
        if (!drag) return;
        rect.x = Math.max(0, Math.min(drag.ox + (e.clientX - drag.sx), w - rect.w));
        rect.y = Math.max(0, Math.min(drag.oy + (e.clientY - drag.sy), h - rect.h));
        draw();
      };
      window.onmouseup = () => { drag = null; };
      id("crop-ok").onclick = () => { pickedBox = boxToNormalized(rect, w, h); refreshBoxHint(); closeCrop(); };
    };
    function closeCrop() { modal.classList.add("hidden"); window.onmousemove = null; window.onmouseup = null; }
    id("crop-cancel").onclick = closeCrop;
    id("crop-reset").onclick = () => { pickedBox = null; refreshBoxHint(); closeCrop(); };
  }

  id("btn-pick-box").addEventListener("click", () => {
    const folder = id("raw_folder").value.trim();
    if (!folder) { id("motion-box-hint").textContent = "请先选 RAW 文件夹"; return; }
    // 用首帧缩略图当底图
    fetch(httpBase + "/preview/frames?folder=" + encodeURIComponent(folder)).then((r) => r.json()).then((d) => {
      if (!d.count) { id("motion-box-hint").textContent = "该文件夹无可预览帧"; return; }
      const first = d.strip[0];
      openCropModal(window.preview.thumbUrl(httpBase, folder, first));
    });
  });
```

把 `buildStartBody()` 里 `payload.social = buildSocialConfig(readForm())` 之前，给 readForm 结果补上 box：在 `buildStartBody` 内改为：

```javascript
  function buildStartBody() {
    const form = readForm();
    form.motion_box = pickedBox;
    const payload = buildStartPayload(form);
    payload.social = buildSocialConfig(form);
    payload.workflow = workflowMap[id("workflow_select").value] || null;
    return payload;
  }
```

- [ ] **Step 4: 运行 JS 测试（确保没破）**

Run: `cd timelapse-tool && export PATH="$HOME/.local/node/bin:$PATH" && npm test`
Expected: 全 PASS（本任务主要是 DOM 接线，纯函数测试在 Task 6）。

- [ ] **Step 5: 提交**

```bash
cd /Users/feitong/photo-app && git add timelapse-tool/electron
git commit -m "feat: 运镜选区 modal（Ken Burns 拖框选放大区域）接入流水线导出区"
```

---

## Task 8: 成片转社媒 tab

**Files:**
- Modify: `timelapse-tool/electron/renderer/index.html`
- Create: `timelapse-tool/electron/renderer/social_tab.js`
- Modify: `timelapse-tool/electron/renderer/app.js`

- [ ] **Step 1: index.html 加第三个 tab + panel**

`<nav class="tabs">` 里「照片筛选」按钮后加：

```html
    <button class="tab" data-tab="social">成片转社媒</button>
```

`<section id="selector" …>` 之后加 panel（社媒控件用 `b_` 前缀 id）：

```html
    <section id="social" class="panel">
      <div class="pipeline-wrap">
      <div class="glass form-section">
        <h2 class="section-title">成片转社媒</h2>
        <div class="field">
          <label>成片文件（mov）</label>
          <div class="path-input">
            <input id="b_src" type="text" placeholder="点右侧选择成片" />
            <button type="button" id="b_choose" class="btn-browse">选择…</button>
          </div>
        </div>
        <div class="row">
          <div class="field"><label>社媒格式</label>
            <select id="b_social_format"><option value="H.265">H.265（更小）</option><option value="H.264">H.264（最兼容）</option></select>
          </div>
          <div class="field"><label>画幅</label>
            <select id="b_social_aspect">
              <option value="9:16">9:16 竖（抖音/小红书）</option>
              <option value="3:4">3:4 竖（小红书）</option>
              <option value="16:9">16:9 横（B站/横屏）</option>
              <option value="1:1">1:1 方</option>
              <option value="3:2">3:2 原始（不裁）</option>
            </select>
          </div>
          <div class="field"><label>分辨率</label>
            <select id="b_social_resolution"><option value="1080p">1080p</option><option value="720p">720p</option><option value="4K">4K</option></select>
          </div>
        </div>
        <div id="b_social-preview" class="hint-line"></div>
        <div class="row">
          <div class="field"><label>运镜</label>
            <select id="b_motion_type"><option value="none">无</option><option value="kenburns">Ken Burns 推拉</option><option value="pan">平移 Pan</option><option value="sweep">竖屏横扫</option></select>
          </div>
          <div class="field"><label>方向</label><select id="b_motion_direction"></select></div>
          <div class="field"><label>强度</label>
            <select id="b_motion_intensity"><option value="light">轻</option><option value="medium" selected>中</option><option value="strong">明显</option></select>
          </div>
        </div>
        <div id="b_motion-box-row" class="field hidden">
          <button type="button" id="b_btn-pick-box" class="btn-browse">选放大区域…</button>
          <span id="b_motion-box-hint" class="hint-line"></span>
        </div>
        <div class="field switch-field">
          <label for="b_motion_subject">自动对准主体（Vision 显著性）</label>
          <input id="b_motion_subject" type="checkbox" />
        </div>
        <div class="pipeline-actions">
          <button id="b_convert" class="btn btn-primary">转换为社媒版</button>
        </div>
        <div id="b_result" class="hint-line"></div>
        <div id="b_error" class="error-text"></div>
      </div>
      </div>
    </section>
```

- [ ] **Step 2: social_tab.js（新）**

复用 pipeline.js 已导出的 `socialPixels` / `motionTypesFor` / `motionDirections` / `buildSocialConfig` / `boxToNormalized`（它们已在 module.exports；浏览器里全局函数同名可直接用，因 pipeline.js 在前加载且这些是全局 function 声明）。创建 `social_tab.js`：

```javascript
async function initSocialTab(httpBase) {
  const id = (x) => document.getElementById(x);
  let pickedBox = null;

  function syncDirections() {
    const sel = id("b_motion_direction"); sel.innerHTML = "";
    for (const [v, l] of motionDirections(id("b_motion_type").value)) {
      const o = document.createElement("option"); o.value = v; o.textContent = l; sel.appendChild(o);
    }
  }
  function syncTypes() {
    const cur = id("b_motion_type").value;
    const types = motionTypesFor(id("b_social_aspect").value);
    const sel = id("b_motion_type"); sel.innerHTML = "";
    for (const [v, l] of types) { const o = document.createElement("option"); o.value = v; o.textContent = l; sel.appendChild(o); }
    sel.value = types.some((t) => t[0] === cur) ? cur : "none";
    syncDirections();
    id("b_motion-box-row").classList.toggle("hidden", sel.value !== "kenburns");
  }
  function syncPreview() {
    const [w, h] = socialPixels(id("b_social_aspect").value, id("b_social_resolution").value);
    id("b_social-preview").textContent = `${w}×${h} · ${id("b_social_format").value}`;
  }
  function refreshHint() { id("b_motion-box-hint").textContent = pickedBox ? "已框选放大区域" : "未选（自动）"; }

  id("b_social_aspect").addEventListener("change", () => { syncTypes(); syncPreview(); });
  ["b_social_format", "b_social_resolution"].forEach((x) => id(x).addEventListener("change", syncPreview));
  id("b_motion_type").addEventListener("change", () => { syncDirections(); id("b_motion-box-row").classList.toggle("hidden", id("b_motion_type").value !== "kenburns"); });
  syncTypes(); syncPreview(); refreshHint();

  id("b_choose").addEventListener("click", async () => {
    if (!window.api || !window.api.chooseFile) return;
    const f = await window.api.chooseFile();
    if (f) { id("b_src").value = f; pickedBox = null; refreshHint(); }
  });

  id("b_btn-pick-box").addEventListener("click", () => {
    const src = id("b_src").value.trim();
    if (!src) { id("b_motion-box-hint").textContent = "请先选成片"; return; }
    window.cropModal.open(httpBase + "/preview/file_thumb?src=" + encodeURIComponent(src), (box) => { pickedBox = box; refreshHint(); });
  });

  id("b_convert").addEventListener("click", async () => {
    id("b_error").textContent = ""; id("b_result").textContent = "转换中…";
    const social = buildSocialConfig({
      social_format: id("b_social_format").value, social_aspect: id("b_social_aspect").value,
      social_resolution: id("b_social_resolution").value, motion_type: id("b_motion_type").value,
      motion_direction: id("b_motion_direction").value, motion_intensity: id("b_motion_intensity").value,
      motion_subject: id("b_motion_subject").checked, motion_box: pickedBox,
    });
    const res = await fetch(httpBase + "/export/social_from", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ src: id("b_src").value, social: social }),
    });
    if (!res.ok) { const e = await res.json().catch(() => ({})); id("b_result").textContent = ""; id("b_error").textContent = "失败：" + (e.detail || res.status); return; }
    const data = await res.json();
    id("b_result").textContent = "完成：" + data.output;
  });
}
if (typeof window !== "undefined") window.initSocialTab = initSocialTab;
```

- [ ] **Step 3: 把选区 modal 抽成可复用的 window.cropModal**

为让两个 tab 共用，在 `pipeline.js` 里把 Task 7 的 `openCropModal` 重构为挂在 `window.cropModal.open(thumbSrc, onConfirm)`（onConfirm 收归一化 box）。在 `pipeline.js` 顶部（initPipeline 外）加：

```javascript
function setupCropModal() {
  const id = (x) => document.getElementById(x);
  const modal = id("crop-modal"), img = id("crop-img"), boxEl = id("crop-box");
  let onConfirm = null;
  function close() { modal.classList.add("hidden"); window.onmousemove = null; window.onmouseup = null; }
  function open(thumbSrc, cb) {
    onConfirm = cb; img.src = thumbSrc; modal.classList.remove("hidden");
    img.onload = () => {
      const w = img.clientWidth, h = img.clientHeight;
      let rect = { x: w * 0.25, y: h * 0.25, w: w * 0.5, h: h * 0.5 };
      const draw = () => { boxEl.style.left = rect.x + "px"; boxEl.style.top = rect.y + "px"; boxEl.style.width = rect.w + "px"; boxEl.style.height = rect.h + "px"; };
      draw();
      let drag = null;
      boxEl.onmousedown = (e) => { drag = { sx: e.clientX, sy: e.clientY, ox: rect.x, oy: rect.y }; e.preventDefault(); };
      window.onmousemove = (e) => { if (!drag) return; rect.x = Math.max(0, Math.min(drag.ox + (e.clientX - drag.sx), w - rect.w)); rect.y = Math.max(0, Math.min(drag.oy + (e.clientY - drag.sy), h - rect.h)); draw(); };
      window.onmouseup = () => { drag = null; };
      id("crop-ok").onclick = () => { if (onConfirm) onConfirm(boxToNormalized(rect, w, h)); close(); };
    };
  }
  id("crop-cancel").onclick = close;
  id("crop-reset").onclick = () => { if (onConfirm) onConfirm(null); close(); };
  return { open };
}
if (typeof window !== "undefined") window.addEventListener("DOMContentLoaded", () => { window.cropModal = setupCropModal(); });
```

并把 Task 7 里 `btn-pick-box` 的处理改为调用 `window.cropModal.open(thumbSrc, (box) => { pickedBox = box; refreshBoxHint(); })`，删除 Task 7 内联的 `openCropModal`（避免重复）。

- [ ] **Step 4: app.js 注册第三个 tab + 初始化**

在 `app.js` 里找到 tab 切换逻辑（点击 `.tab` 切换 `.panel`），确保 `data-tab="social"` 能切到 `#social`（现有逻辑按 `data-tab` 对应 panel id，通常已通用）。在初始化处（调用 `initPipeline(httpBase)` 之后）加：

```javascript
  if (window.initSocialTab) window.initSocialTab(httpBase);
```

并在 index.html 底部 `<script src="pipeline.js">` 之后、`app.js` 之前加：

```html
  <script src="social_tab.js"></script>
```

- [ ] **Step 5: 运行 JS 测试 + 提交**

Run: `cd timelapse-tool && export PATH="$HOME/.local/node/bin:$PATH" && npm test`
Expected: 全 PASS（jsdom 不跑 DOM 交互，纯函数过即可）。

```bash
cd /Users/feitong/photo-app && git add timelapse-tool/electron
git commit -m "feat: 成片转社媒 tab（导入 mov→社媒配置→出片）+ 复用选区 modal"
```

---

## Task 9: 实机验证

**Files:** 无（验证）。需重编 media_export（未改，但确保最新）并启动 app。

- [ ] **Step 1: 全套自动化测试**

```bash
cd timelapse-tool/python && .venv/bin/python -m pytest -q
cd /Users/feitong/photo-app/timelapse-tool && export PATH="$HOME/.local/node/bin:$PATH" && npm test
```
Expected: 全 PASS。

- [ ] **Step 2: 启动 app，验证 A（运镜选区）**

启动后在「延时流水线」：选 RAW 文件夹 → 运镜选 Ken Burns → 点「选放大区域」→ 拖框 → 确定。提示变「已框选」。（出片验证可结合 Task 9 Step 3 的成片转社媒更快。）

- [ ] **Step 3: 验证 B（成片转社媒，含选区）**

切到「成片转社媒」tab → 选 `~/Desktop/tl_out_full/timelapse_master.mov` → 画幅 9:16、Ken Burns、点「选放大区域」框一块 → 转换。
Expected: 源目录生成 `timelapse_master_social_1080x1920_h265.mp4`；用 `/tmp/probe_fps` 验尺寸 1080×1920、播放确认推近到所框区域。

```bash
/tmp/probe_fps ~/Desktop/tl_out_full/timelapse_master_social_1080x1920_h265.mp4
```

- [ ] **Step 4: 提交（如有验证产生的微调）**

```bash
cd /Users/feitong/photo-app && git add -A timelapse-tool && git commit -m "chore: 运镜选区+成片转社媒 实机验证" || echo "无改动"
```

---

## Self-Review Notes

- **Spec 覆盖**：① transcode_social 拆分（Task 2）② motion.box 分支（Task 1）③ box 锚点优先级（Task 2 transcode_social）④ file_thumb 接口（Task 3）⑤ social_from 接口（Task 4）⑥ chooseFile（Task 5）⑦ box 坐标/配置纯函数（Task 6）⑧ 选区 modal + Ken Burns 按钮（Task 7）⑨ 成片转社媒 tab + 复用 modal（Task 8）。均有对应任务。
- **类型一致**：`transcode_social(src, output_dir, social, emit, run, binary, prefix)`、`social_output_path(..., prefix="timelapse")`、`motion.box=[x,y,w,h]` 归一化、`boxToNormalized(rect,w,h)→[..]`、`window.cropModal.open(thumbSrc, cb)` 贯穿一致。
- **占位符**：无 TODO/TBD；前端拖拽给了完整可运行实现。
- **共用**：选区 modal 抽成 `window.cropModal`（Task 8 Step 3 重构），流水线与成片 tab 共用；社媒配置控件用 `b_` 前缀避免 id 冲突。
- **YAGNI**：单框单段 Ken Burns；pan/sweep 不接 box；成片转社媒单文件、无队列。
- **已知实机点**：拖拽 modal、qlmanage 对 mov 出缩略图、Electron chooseFile —— Task 9 验证。
```
