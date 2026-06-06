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
