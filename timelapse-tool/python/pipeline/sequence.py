"""序列整理：处理相机计数器回绕（如 9999→0001）导致的不连续序列。

按拍摄时间（EXIF，经 mdls）排序，硬链接到新文件夹 <folder>_seq 并连续重命名，
让 LRTimelapse / AE 能正常导入。原文件不动、不占额外空间。
"""

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

IMAGE_EXTS = {".arw", ".jpg", ".jpeg", ".tif", ".tiff", ".png",
              ".dng", ".cr2", ".cr3", ".nef", ".raf", ".orf"}


def _mdls_time(path):
    """用 Spotlight 读拍摄时间（kMDItemContentCreationDate），返回可排序字符串或 None。"""
    try:
        r = subprocess.run(
            ["mdls", "-raw", "-name", "kMDItemContentCreationDate", str(path)],
            capture_output=True, text=True,
        )
        out = (r.stdout or "").strip()
        if out and out != "(null)":
            return out  # 形如 "2026-06-03 05:38:15 +0000"，定宽可字符串排序
    except Exception:
        pass
    return None


def default_time_of(path):
    """拍摄时间优先，缺失则用文件修改时间，统一成同格式可排序字符串。"""
    t = _mdls_time(path)
    if t:
        return t
    mt = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
    return mt.strftime("%Y-%m-%d %H:%M:%S +0000")


def _frames(folder):
    p = Path(folder)
    if not p.is_dir():
        return []
    return [f.name for f in p.iterdir()
            if f.is_file() and f.suffix.lower() in IMAGE_EXTS]


def ordered_frames(folder, time_of=None):
    """按拍摄时间（同时刻按文件名）升序排列的帧名。"""
    time_of = time_of or default_time_of
    folder = Path(folder)
    return sorted(_frames(folder), key=lambda n: (time_of(str(folder / n)), n))


def is_continuous(folder, time_of=None):
    """拍摄时间顺序与文件名字典序一致即为连续（不会触发回绕导入问题）。"""
    by_time = ordered_frames(folder, time_of)
    return by_time == sorted(by_time)


# 调色/元数据边车扩展名，整理时随 RAW 一起改名带过去（否则 AE 读不到调色）
SIDECAR_EXTS = [".xmp", ".acr"]


def repair(folder, time_of=None, link=os.link):
    """若序列不连续，硬链接重排到 <folder>_seq 并返回其路径；否则返回原文件夹。

    每帧 RAW 连同同名的 .xmp/.acr 调色边车一起按 TL_NNNN 改名带过去，
    保证 AE 导入时能读到 LRT/ACR 的调色。
    """
    folder = Path(folder)
    ordered = ordered_frames(str(folder), time_of)
    if not ordered or ordered == sorted(ordered):
        return str(folder)

    dest = folder.parent / (folder.name + "_seq")
    dest.mkdir(exist_ok=True)
    width = max(4, len(str(len(ordered))))
    for i, name in enumerate(ordered, 1):
        stem = Path(name).stem
        ext = Path(name).suffix
        base = f"TL_{str(i).zfill(width)}"
        target = dest / f"{base}{ext}"
        if target.exists():
            target.unlink()
        link(str(folder / name), str(target))
        # 同名调色边车一并带过去
        for sc_ext in SIDECAR_EXTS:
            sc = folder / f"{stem}{sc_ext}"
            if sc.exists():
                sc_target = dest / f"{base}{sc_ext}"
                if sc_target.exists():
                    sc_target.unlink()
                link(str(sc), str(sc_target))
    return str(dest)
