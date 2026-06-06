import subprocess
import tempfile
from pathlib import Path

from pipeline import effects

# AE 经 Camera Raw 直接导入 RAW 序列，也支持已导出的 JPG/TIF
SEQUENCE_EXTS = {".jpg", ".jpeg", ".tif", ".tiff", ".png",
                 ".arw", ".dng", ".cr2", ".cr3", ".nef", ".raf", ".orf"}

AERENDER = "/Applications/Adobe After Effects 2026/aerender"
# 用 AppleScript DoScriptFile 驱动（AE 的命令行 -r 在 2026 上不可靠）
AE_APP_NAME = "Adobe After Effects 2026"

INTERMEDIATE_NAME = "_ae_intermediate.mov"
# AE 内置输出模块模板名就叫「ProRes 4444」（不带 Apple）。带 Apple 会让 aerender
# 报 "No output module template was found"，既渲不出、回退默认还可能改帧率。实机确认。
PRORES_OM_TEMPLATE = "ProRes 4444"
COMP_NAME = "Timelapse"


def find_sequence_anchor(folder):
    """返回序列里排序最靠前的图片文件（AE 导入序列的锚点）。"""
    images = sorted(
        p for p in Path(folder).iterdir()
        if p.suffix.lower() in SEQUENCE_EXTS
    )
    if not images:
        raise ValueError(f"序列文件夹里没有图片: {folder}")
    return images[0]


def intermediate_path(output_dir):
    return Path(output_dir) / INTERMEDIATE_NAME


def _stabilizer_jsx(stabilize):
    """生成给图层加变形稳定器并设参数的 jsx 片段；未启用时返回空串。

    注意：变形稳定器需要「分析」才真正生效，分析触发是真机迭代点（Task 6）。
    """
    if not stabilize.get("enabled"):
        return ""
    result_val = effects.WS_RESULT_VALUE[stabilize["result"]]
    method_val = effects.WS_METHOD_VALUE[stabilize["method"]]
    smoothness = stabilize["smoothness"]
    return f"""
var layer = comp.layer(1);
var ws = layer.property("ADBE Effect Parade").addProperty("{effects.WARP_STABILIZER_MATCHNAME}");
try {{ ws.property("{effects.WS_PROP_RESULT}").setValue({result_val}); }} catch (e) {{}}
try {{ ws.property("{effects.WS_PROP_METHOD}").setValue({method_val}); }} catch (e) {{}}
try {{ ws.property("{effects.WS_PROP_SMOOTHNESS}").setValue({smoothness}); }} catch (e) {{}}
"""


def build_ae_script(anchor_file, fps, resolution, project_save_path, stabilize):
    """生成构建 AE 工程的 ExtendScript：导入序列→按导出分辨率建合成（画面缩放铺满）→(增稳)→入渲染队列→保存。

    resolution: [宽, 高]。合成按此尺寸建，RAW 画面缩放铺满（cover，超出裁掉）。
    渲染由后续 aerender 执行；这里只搭好工程并保存。
    """
    width = int(resolution[0])
    return f"""
var anchor = new File("{anchor_file}");
var io = new ImportOptions(anchor);
if (io.canImportAs(ImportAsType.FOOTAGE)) {{
    io.importAs = ImportAsType.FOOTAGE;
}}
io.sequence = true;
var footage = app.project.importFile(io);
footage.mainSource.conformFrameRate = {fps};

// 不裁切：合成按 RAW 原始宽高比，宽取目标宽，高按比例算
var compW = {width};
var compH = Math.round(compW * footage.height / footage.width);
if (compH % 2 != 0) {{ compH += 1; }}  // 保持偶数，编码友好
var comp = app.project.items.addComp(
    "{COMP_NAME}",
    compW,
    compH,
    1.0,
    footage.duration,
    {fps}
);
var layer = comp.layers.add(footage);
// 缩放铺满（不裁切，宽高同比，因合成已是原始比例）
var s = (compW / footage.width) * 100;
layer.property("ADBE Transform Group").property("ADBE Scale").setValue([s, s]);
{_stabilizer_jsx(stabilize)}
app.project.renderQueue.items.add(comp);

app.project.save(new File("{project_save_path}"));
app.quit();
""".strip()


def build_run_script_cmd(jsx_path, app_name=AE_APP_NAME):
    """用 AppleScript 让（运行中的/将启动的）AE 执行脚本文件。"""
    apple = (
        f'with timeout of 1800 seconds\n'
        f'tell application "{app_name}" to DoScriptFile "{jsx_path}"\n'
        f'end timeout'
    )
    return ["osascript", "-e", apple]


def build_aerender_cmd(aerender, project_path, output_path, start=None, end=None):
    cmd = [
        aerender,
        "-project", project_path,
        "-comp", COMP_NAME,
        "-OMtemplate", PRORES_OM_TEMPLATE,
        "-output", output_path,
    ]
    if start is not None:
        cmd += ["-s", str(start)]
    if end is not None:
        cmd += ["-e", str(end)]
    return cmd


CHUNKS_DIRNAME = "_ae_chunks"

# 无损拼接工具：用 AVFoundation passthrough 把分块 ProRes 拼成一条（见 mov_concat.swift）
CONCAT_SWIFT = Path(__file__).parent / "mov_concat.swift"
CONCAT_BIN = str(Path(tempfile.gettempdir()) / "timelapse_mov_concat")


def chunks_dir(output_dir):
    return Path(output_dir) / CHUNKS_DIRNAME


def build_concat_cmd(binary, output_path, chunk_files):
    """拼接命令：<binary> <输出> <片段1> <片段2> …（顺序即拼接顺序）。"""
    return [binary, output_path, *chunk_files]


def ensure_concat_binary(run=subprocess.run, binary=CONCAT_BIN, source=CONCAT_SWIFT):
    """首次用时把 Swift 拼接工具编译到缓存二进制；已存在则跳过。返回二进制路径。"""
    if Path(binary).exists():
        return binary
    r = run(["swiftc", "-O", str(source), "-o", binary])
    if getattr(r, "returncode", 0) != 0 or not Path(binary).exists():
        raise RuntimeError("无法编译 MOV 拼接工具（swiftc）")
    return binary


def merge_chunks(chunk_files, output_dir, emit, run=subprocess.run, binary=CONCAT_BIN):
    """把分块 ProRes 片段无损拼接成 _ae_intermediate.mov，返回其路径。

    各 chunk 同编码/同尺寸/同帧率（分块渲染天然满足），passthrough 拼接不重编码。
    """
    if not chunk_files:
        raise RuntimeError("没有可合并的渲染片段")
    out = intermediate_path(output_dir)
    emit(f"AE 阶段：合并 {len(chunk_files)} 段为中间视频…")
    bin_path = ensure_concat_binary(run=run, binary=binary)
    if out.exists():
        out.unlink()  # 清掉旧的再拼
    run(build_concat_cmd(bin_path, str(out), list(chunk_files)))
    # 只认真正封口（有 moov）的输出
    if not is_valid_mov(out):
        raise RuntimeError(f"中间视频合并失败（未封口）: {out}")
    emit("AE 阶段：中间视频合并完成")
    return out


def frame_count(seq_folder):
    """序列帧数 = 文件夹里图片数量（每张 RAW 一帧）。"""
    return len([p for p in Path(seq_folder).iterdir()
                if p.is_file() and p.suffix.lower() in SEQUENCE_EXTS])


def is_valid_mov(path):
    """检查 MOV 是否真正封口（含 moov 索引）。aerender 崩溃后可能假成功留下无索引残档。"""
    import struct
    p = Path(path)
    if not p.exists() or p.stat().st_size < 1024:
        return False
    try:
        size = p.stat().st_size
        off = 0
        with open(p, "rb") as fh:
            while off < size:
                fh.seek(off)
                h = fh.read(8)
                if len(h) < 8:
                    break
                asz = struct.unpack(">I", h[:4])[0]
                atype = h[4:8]
                if atype == b"moov":
                    return True
                if asz == 1:
                    asz = struct.unpack(">Q", fh.read(8))[0]
                if asz == 0:
                    break
                off += asz
    except Exception:
        return False
    return False


def render_sequence(seq_folder, output_dir, fps, resolution, stabilize, emit, run=subprocess.run,
                    aerender=AERENDER, ae_app_name=AE_APP_NAME, chunk=100, retries=3):
    """分块渲染（防崩+可重试），返回各段 ProRes 片段路径列表。

    每段单独跑一个 aerender 进程（内存清零、抗累积崩溃）；某段失败自动重试。
    run: 可注入的命令执行器。
    """
    anchor = find_sequence_anchor(seq_folder)
    total = frame_count(seq_folder)
    proj_path = str(Path(tempfile.gettempdir()) / "timelapse_ae_project.aep")
    cdir = chunks_dir(output_dir)
    cdir.mkdir(parents=True, exist_ok=True)

    emit("AE 阶段：打开 After Effects、新建工程并导入 RAW 序列…")
    jsx = build_ae_script(str(anchor), fps, resolution, proj_path, stabilize)
    with tempfile.NamedTemporaryFile("w", suffix=".jsx", delete=False) as f:
        f.write(jsx)
        jsx_path = f.name
    r1 = run(build_run_script_cmd(jsx_path, ae_app_name))
    if getattr(r1, "returncode", 0) != 0:
        raise RuntimeError("AE 建工程失败")

    chunk_files = []
    starts = list(range(0, total, chunk)) if total else [0]
    for i, start in enumerate(starts):
        end = min(start + chunk - 1, total - 1) if total else None
        out = cdir / f"chunk_{i:03d}.mov"
        # 断点续渲：已存在且封口完整的段跳过
        if is_valid_mov(out):
            emit(f"AE 阶段：第 {i+1}/{len(starts)} 段已完成，跳过")
            chunk_files.append(str(out))
            continue
        ok = False
        for attempt in range(retries):
            emit(f"AE 阶段：渲染第 {i+1}/{len(starts)} 段（帧 {start}-{end}，第 {attempt+1} 次）…")
            if out.exists():
                out.unlink()  # 清掉上次的残档再渲
            run(build_aerender_cmd(aerender, proj_path, str(out), start, end))
            # 只认真正封口（有 moov）的输出，规避 aerender 崩溃后假成功
            if is_valid_mov(out):
                ok = True
                break
            emit(f"AE 阶段：第 {i+1} 段未封口（崩溃残档），重试…")
        if not ok:
            raise RuntimeError(f"第 {i+1} 段渲染重试 {retries} 次仍失败")
        chunk_files.append(str(out))
    emit(f"AE 阶段：完成，共 {len(chunk_files)} 段 ProRes 片段")
    return chunk_files
