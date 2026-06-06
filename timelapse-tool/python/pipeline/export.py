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


def social_output_path(output_dir, fmt, w, h, prefix="timelapse"):
    tag = ef.FORMAT_TAG[fmt]
    return Path(output_dir) / f"{prefix}_social_{w}x{h}_{tag}.mp4"


def build_probe_cmd(binary, src):
    return [binary, "--probe", src]


def build_saliency_cmd(binary, src):
    return [binary, "--saliency", src]


def build_export_cmd(binary, src, out, fmt_swift, start_crop, end_crop, outsize):
    """转码命令：起止两个裁框（运镜 ramp）+ 输出尺寸。无运镜时起=止。"""
    return [binary, src, out, fmt_swift,
            *map(str, start_crop), *map(str, end_crop), *map(str, outsize)]


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


def saliency_center(binary, master, run=subprocess.run):
    """Vision 显著性主体中心（归一化 0–1）。失败/检测不到回退画面正中。"""
    r = run(build_saliency_cmd(binary, str(master)), capture_output=True, text=True)
    if getattr(r, "returncode", 0) != 0:
        return (0.5, 0.5)
    try:
        cx, cy = r.stdout.split()
        return (float(cx), float(cy))
    except (ValueError, AttributeError):
        return (0.5, 0.5)


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
    if motion.get("box"):
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
