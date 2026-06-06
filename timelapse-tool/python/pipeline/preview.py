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


def best_frame(folder, binary, sample=12, run=subprocess.run):
    """均匀采样若干帧，用 media_export --saturation 挑平均饱和度最高的，返回帧名。"""
    frames = list_frames(folder)
    if not frames:
        return None
    sampled = anim_names(frames, sample)
    paths = [str(Path(folder) / n) for n in sampled]
    r = run([binary, "--saturation", *paths], capture_output=True, text=True)
    out = (getattr(r, "stdout", "") or "").strip()
    return Path(out).name if out else sampled[0]


def read_metadata(folder, binary, run=subprocess.run):
    """读首帧的相机/拍摄/分辨率元数据（media_export --meta）。无帧或失败返回 {}。"""
    import json
    frames = list_frames(folder)
    if not frames:
        return {}
    first = str(Path(folder) / frames[0])
    r = run([binary, "--meta", first], capture_output=True, text=True)
    try:
        return json.loads((getattr(r, "stdout", "") or "").strip() or "{}")
    except (ValueError, TypeError):
        return {}
