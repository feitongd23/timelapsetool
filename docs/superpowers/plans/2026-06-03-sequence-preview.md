# 序列预览 (Sequence Preview) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 选中 RAW 文件夹或 LRT 导出文件夹后，在界面旁边显示该序列的缩略图条（首/中/尾）+ 帧数，并能点「播放预览」轮播抽样帧模拟延时成片动态。RAW(.ARW) 与 JPG/TIF/PNG 都支持。

**Architecture:** 后端用 macOS `qlmanage`（QuickLook）为任意图片（含 ARW）生成 PNG 缩略图并缓存，提供「列出帧 + 抽样」与「取某帧缩略图」两个端点。前端在每个文件夹输入旁加「预览」按钮，点后把该文件夹载入共享预览面板：显示首/中/尾缩略图条；「播放」按钮以固定帧率轮播抽样帧。缩略图生成与抽样逻辑可单测（注入 run）；qlmanage 实际产物靠真机/本机验证。

**Tech Stack:** Python 3.9 + FastAPI（subprocess 调 qlmanage），Electron 原生 JS + Jest。无需新增 pip 依赖。

---

## 关键约定

- 支持扩展名：`.arw .jpg .jpeg .tif .tiff .png`（大小写不敏感），按文件名排序为帧顺序。
- 缩略图：`qlmanage -t -s <size> -o <cachedir> <file>` 生成 `<cachedir>/<filename>.png`，按文件路径+mtime 缓存，重复请求不重算。
- 抽样：
  - 缩略图条 strip = 首/中/尾 3 帧（不足 3 帧则全取）。
  - 播放预览 anim = 至多 ~24 帧均匀抽样。
- 缓存目录：`<系统临时目录>/timelapse_thumbs/`。

---

## File Structure

```
timelapse-tool/python/
├── pipeline/preview.py     # 新增：列帧/抽样/缩略图生成
├── server.py               # 修改：/preview/frames、/preview/thumb
└── tests/test_preview.py   # 新增
electron/renderer/
├── index.html              # 修改：路径旁「预览」按钮 + 预览面板
├── pipeline.js             # 修改：加载帧、渲染缩略图条、播放轮播
└── style.css               # 修改：预览面板样式
tests/preview.test.js       # 新增：抽样纯函数
```

---

## Task 1: 预览后端模块（列帧/抽样/缩略图）

**Files:**
- Create: `timelapse-tool/python/pipeline/preview.py`
- Test: `timelapse-tool/python/tests/test_preview.py`

- [ ] **Step 1: 写失败的测试**

创建 `timelapse-tool/python/tests/test_preview.py`：

```python
import pytest

from pipeline import preview


def test_list_frames_sorted_filters_images(tmp_path):
    for n in ["b.jpg", "a.ARW", "c.tif", "notes.txt", "d.png"]:
        (tmp_path / n).write_text("x")
    frames = preview.list_frames(str(tmp_path))
    assert frames == ["a.ARW", "b.jpg", "c.tif", "d.png"]


def test_list_frames_empty_folder(tmp_path):
    assert preview.list_frames(str(tmp_path)) == []


def test_strip_indices_first_mid_last():
    assert preview.strip_names(["f0", "f1", "f2", "f3", "f4"]) == ["f0", "f2", "f4"]


def test_strip_names_few_frames():
    assert preview.strip_names(["a", "b"]) == ["a", "b"]
    assert preview.strip_names([]) == []


def test_anim_names_caps_count():
    frames = [f"f{i}" for i in range(100)]
    anim = preview.anim_names(frames, cap=24)
    assert len(anim) == 24
    assert anim[0] == "f0" and anim[-1] == "f99"


def test_anim_names_small_returns_all():
    assert preview.anim_names(["a", "b", "c"], cap=24) == ["a", "b", "c"]


def test_generate_thumbnail_invokes_qlmanage(tmp_path):
    src = tmp_path / "a.ARW"; src.write_text("raw")
    cache = tmp_path / "cache"
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        # 模拟 qlmanage 产出 <cache>/a.ARW.png
        (cache / "a.ARW.png").parent.mkdir(parents=True, exist_ok=True)
        (cache / "a.ARW.png").write_text("png")
        class R: returncode = 0
        return R()

    thumb = preview.generate_thumbnail(str(src), 320, str(cache), run=fake_run)
    assert thumb.endswith("a.ARW.png")
    assert "qlmanage" in calls[0][0]


def test_generate_thumbnail_uses_cache(tmp_path):
    src = tmp_path / "a.jpg"; src.write_text("img")
    cache = tmp_path / "cache"; cache.mkdir()
    (cache / "a.jpg.png").write_text("cached")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        class R: returncode = 0
        return R()

    thumb = preview.generate_thumbnail(str(src), 320, str(cache), run=fake_run)
    assert thumb.endswith("a.jpg.png")
    assert calls == []  # 命中缓存，不调 qlmanage
```

- [ ] **Step 2: 运行确认失败**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_preview.py -v`
Expected: FAIL（无模块）。

- [ ] **Step 3: 写实现**

创建 `timelapse-tool/python/pipeline/preview.py`：

```python
import subprocess
from pathlib import Path

IMAGE_EXTS = {".arw", ".jpg", ".jpeg", ".tif", ".tiff", ".png"}


def list_frames(folder):
    """文件夹内的图片文件名（按名排序）。"""
    p = Path(folder)
    if not p.is_dir():
        return []
    return sorted(
        f.name for f in p.iterdir()
        if f.is_file() and f.suffix.lower() in IMAGE_EXTS
    )


def strip_names(frames):
    """首/中/尾 3 帧（不足则全取）。"""
    if len(frames) <= 3:
        return list(frames)
    return [frames[0], frames[len(frames) // 2], frames[-1]]


def anim_names(frames, cap=24):
    """至多 cap 帧的均匀抽样（含首尾）。"""
    n = len(frames)
    if n <= cap:
        return list(frames)
    step = (n - 1) / (cap - 1)
    idxs = sorted(set(round(i * step) for i in range(cap)))
    return [frames[i] for i in idxs]


def generate_thumbnail(src_file, size, cache_dir, run=subprocess.run):
    """用 qlmanage 生成 <cache_dir>/<filename>.png 缩略图并返回其路径；命中缓存则跳过。"""
    src = Path(src_file)
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    thumb = cache / (src.name + ".png")
    if thumb.exists():
        return str(thumb)
    run(["/usr/bin/qlmanage", "-t", "-s", str(size), "-o", str(cache), str(src)])
    return str(thumb)
```

- [ ] **Step 4: 运行确认通过**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_preview.py -v`
Expected: 8 个 PASS。

- [ ] **Step 5: 提交**

```bash
git add timelapse-tool/python/pipeline/preview.py timelapse-tool/python/tests/test_preview.py
git commit -m "feat: 序列预览后端（列帧/抽样/qlmanage 缩略图）"
```

---

## Task 2: 预览 API 端点

**Files:**
- Modify: `timelapse-tool/python/server.py`
- Test: `timelapse-tool/python/tests/test_pipeline_api.py`

- [ ] **Step 1: 写失败的测试**

在 `tests/test_pipeline_api.py` 末尾追加：

```python
def test_preview_frames(tmp_path):
    for n in ["0001.jpg", "0002.jpg", "0003.jpg"]:
        (tmp_path / n).write_text("x")
    r = client.get("/preview/frames", params={"folder": str(tmp_path)})
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 3
    assert data["strip"] == ["0001.jpg", "0002.jpg", "0003.jpg"]
    assert "0001.jpg" in data["anim"]


def test_preview_frames_empty(tmp_path):
    r = client.get("/preview/frames", params={"folder": str(tmp_path)})
    assert r.json()["count"] == 0
```

- [ ] **Step 2: 运行确认失败**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/test_pipeline_api.py -k preview -v`
Expected: FAIL（404）。

- [ ] **Step 3: 写实现**

编辑 `timelapse-tool/python/server.py`：
- 顶部 import 加：`import tempfile` 与 `from fastapi.responses import FileResponse` 和 `from pipeline import preview`
- 加缓存目录常量：`_THUMB_CACHE = str(Path(tempfile.gettempdir()) / "timelapse_thumbs")`
- 加端点（`if __name__` 之前）：

```python
@app.get("/preview/frames")
def preview_frames(folder: str):
    frames = preview.list_frames(folder)
    return {
        "count": len(frames),
        "strip": preview.strip_names(frames),
        "anim": preview.anim_names(frames),
    }


@app.get("/preview/thumb")
def preview_thumb(folder: str, name: str):
    src = Path(folder) / name
    if not src.is_file():
        raise HTTPException(status_code=404, detail="帧不存在")
    thumb = preview.generate_thumbnail(str(src), 320, _THUMB_CACHE)
    if not Path(thumb).exists():
        raise HTTPException(status_code=500, detail="缩略图生成失败")
    return FileResponse(thumb, media_type="image/png")
```

- [ ] **Step 4: 运行确认通过**

Run: `cd timelapse-tool/python && .venv/bin/python -m pytest tests/ -q`
Expected: 全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add timelapse-tool/python/server.py timelapse-tool/python/tests/test_pipeline_api.py
git commit -m "feat: 预览 API（/preview/frames、/preview/thumb）"
```

---

## Task 3: 前端抽样纯函数

**Files:**
- Create: `timelapse-tool/electron/renderer/preview.js`
- Test: `timelapse-tool/tests/preview.test.js`

- [ ] **Step 1: 写失败的测试**

创建 `timelapse-tool/tests/preview.test.js`：

```javascript
const { thumbUrl, nextFrameIndex } = require("../electron/renderer/preview.js");

test("thumbUrl 拼接编码后的查询", () => {
  const url = thumbUrl("http://h", "/a b/raw", "0001.ARW");
  expect(url).toBe("http://h/preview/thumb?folder=%2Fa%20b%2Fraw&name=0001.ARW");
});

test("nextFrameIndex 循环递增", () => {
  expect(nextFrameIndex(0, 3)).toBe(1);
  expect(nextFrameIndex(2, 3)).toBe(0);
  expect(nextFrameIndex(0, 0)).toBe(0);
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd timelapse-tool && export PATH="$HOME/.local/node/bin:$PATH" && npx jest --testEnvironment=jsdom tests/preview.test.js`
Expected: FAIL（无模块）。

- [ ] **Step 3: 写实现**

创建 `timelapse-tool/electron/renderer/preview.js`：

```javascript
function thumbUrl(httpBase, folder, name) {
  return httpBase + "/preview/thumb?folder=" + encodeURIComponent(folder) + "&name=" + name;
}

function nextFrameIndex(i, len) {
  if (!len) return 0;
  return (i + 1) % len;
}

if (typeof module !== "undefined") {
  module.exports = { thumbUrl, nextFrameIndex };
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd timelapse-tool && export PATH="$HOME/.local/node/bin:$PATH" && npx jest --testEnvironment=jsdom tests/preview.test.js`
Expected: 2 个 PASS。

- [ ] **Step 5: 提交**

```bash
git add timelapse-tool/electron/renderer/preview.js timelapse-tool/tests/preview.test.js
git commit -m "feat: 预览前端纯函数（缩略图 URL / 轮播帧索引）"
```

---

## Task 4: 预览 UI（缩略图条 + 播放）

**Files:**
- Modify: `timelapse-tool/electron/renderer/index.html`
- Modify: `timelapse-tool/electron/renderer/pipeline.js`
- Modify: `timelapse-tool/electron/renderer/style.css`

无独立单测（DOM/网络/图片），靠 Task 5 实机验证。

- [ ] **Step 1: HTML —— 路径旁加「预览」按钮 + 预览面板**

在 `index.html` 中，给 RAW 文件夹与 LRT 导出文件夹的 `.path-input` 里，在「选择…」按钮之后各加一个预览按钮：

RAW 文件夹那个 `.path-input` 内追加：
```html
            <button type="button" class="btn-browse btn-preview" data-folder="raw_folder">预览</button>
```
LRT 导出文件夹那个 `.path-input` 内追加：
```html
            <button type="button" class="btn-browse btn-preview" data-folder="lrt_export_folder">预览</button>
```

在 `<script src="pipeline.js">` 之前引入 preview.js：
```html
  <script src="preview.js"></script>
```

在 `.pipeline-wrap` 里、`.glass.pipeline-form` 之后加预览面板：
```html
      <div class="glass preview-panel hidden" id="preview-panel">
        <div class="preview-head">
          <span id="preview-info">预览</span>
          <button type="button" id="preview-play" class="btn-browse">▶ 播放</button>
        </div>
        <div class="preview-strip" id="preview-strip"></div>
        <img id="preview-stage" class="preview-stage hidden" alt="预览" />
      </div>
```

- [ ] **Step 2: pipeline.js —— 接线预览**

在 `initPipeline` 内（任意靠后位置，文件夹按钮接线附近）加入：

```javascript
  // 预览：点「预览」按钮 → 拉该文件夹帧 → 显示缩略图条 + 可播放
  let animFrames = [];
  let animFolder = "";
  let animTimer = null;
  let animIdx = 0;

  function stopAnim() {
    if (animTimer) { clearInterval(animTimer); animTimer = null; }
    id("preview-play").textContent = "▶ 播放";
    id("preview-stage").classList.add("hidden");
    id("preview-strip").classList.remove("hidden");
  }

  async function loadPreview(folder) {
    stopAnim();
    const panel = id("preview-panel");
    const data = await fetch(httpBase + "/preview/frames?folder=" + encodeURIComponent(folder)).then((r) => r.json());
    panel.classList.remove("hidden");
    id("preview-info").textContent = "共 " + data.count + " 帧";
    const strip = id("preview-strip");
    strip.innerHTML = "";
    if (data.count === 0) { strip.textContent = "该文件夹没有可预览的图片"; return; }
    for (const name of data.strip) {
      const img = document.createElement("img");
      img.src = window.preview.thumbUrl(httpBase, folder, name);
      img.className = "thumb";
      strip.appendChild(img);
    }
    animFrames = data.anim;
    animFolder = folder;
  }

  document.querySelectorAll(".btn-preview").forEach((btn) => {
    btn.addEventListener("click", () => {
      const folder = id(btn.dataset.folder).value;
      if (folder) loadPreview(folder);
    });
  });

  id("preview-play").addEventListener("click", () => {
    if (animTimer) { stopAnim(); return; }
    if (!animFrames.length) return;
    const stage = id("preview-stage");
    id("preview-strip").classList.add("hidden");
    stage.classList.remove("hidden");
    id("preview-play").textContent = "⏸ 停止";
    animIdx = 0;
    animTimer = setInterval(() => {
      stage.src = window.preview.thumbUrl(httpBase, animFolder, animFrames[animIdx]);
      animIdx = window.preview.nextFrameIndex(animIdx, animFrames.length);
    }, 90);  // ~11fps 预览
  });
```

> preview.js 浏览器端需暴露 `window.preview`。在 `preview.js` 末尾的导出块改为同时挂 window：

编辑 `timelapse-tool/electron/renderer/preview.js`，把结尾改为：
```javascript
if (typeof window !== "undefined") {
  window.preview = { thumbUrl, nextFrameIndex };
}
if (typeof module !== "undefined") {
  module.exports = { thumbUrl, nextFrameIndex };
}
```

- [ ] **Step 3: CSS**

在 `style.css` 末尾追加：
```css
.preview-panel { padding: 18px; }
.preview-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
#preview-info { font-size: 13px; color: var(--text-dim); }
.preview-strip { display: flex; gap: 10px; flex-wrap: wrap; }
.preview-strip .thumb { width: 30%; max-width: 200px; border-radius: var(--radius-sm); border: 1px solid var(--glass-border); }
.preview-stage { width: 100%; border-radius: var(--radius-sm); border: 1px solid var(--glass-border); }
```

- [ ] **Step 4: 回归前端测试**

Run: `cd timelapse-tool && export PATH="$HOME/.local/node/bin:$PATH" && npx jest --testEnvironment=jsdom`
Expected: 全部 PASS（含既有用例与 preview.test.js）。

- [ ] **Step 5: 提交**

```bash
git add timelapse-tool/electron/renderer/index.html timelapse-tool/electron/renderer/pipeline.js timelapse-tool/electron/renderer/preview.js timelapse-tool/electron/renderer/style.css
git commit -m "feat: 序列预览 UI（缩略图条 + 播放轮播）"
```

---

## Task 5: 实机验证

- [ ] 选一个含真实 .ARW 的文件夹，点「预览」→ 看到首/中/尾三张缩略图 + 帧数。
- [ ] 点「▶ 播放」→ 抽样帧快速轮播，能看出延时的大致动态；再点停止恢复缩略图条。
- [ ] 对 LRT 导出的 JPG/TIF 文件夹同样可预览。
- [ ] 若 ARW 缩略图空白：确认 `qlmanage -t -s 320 -o <dir> <file.ARW>` 能否生成 png；不行则在 preview.py 增加回退（如 `sips` 或抽取嵌入预览）。

---

## Self-Review Notes

- **Spec 覆盖**：实现「选文件夹后预览」——缩略图条（首/中/尾）+ 播放轮播；RAW 与 JPG/TIF/PNG 都支持；RAW 与 LRT 两个文件夹都能预览。
- **依赖**：用 macOS 自带 `qlmanage`，不加 pip 依赖；缩略图按文件名缓存到临时目录。
- **可测性**：列帧/抽样/缩略图生成（注入 run）单测；端点 frames 单测；thumb 实际图与 UI 靠真机验证。
- **性能**：只为首/中/尾 + 至多 24 帧抽样生成缩略图，不会对上千帧全量解码。
- **类型一致性**：`/preview/frames` 返回 {count, strip, anim}；前端按此消费；thumbUrl 拼 `/preview/thumb?folder=&name=`。
- **YAGNI**：预览用 320px PNG 缩略图轮播模拟动态，不做真实 H.264 预览渲染（太重）。
