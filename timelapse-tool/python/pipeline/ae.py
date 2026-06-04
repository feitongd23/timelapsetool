import subprocess
import tempfile
from pathlib import Path

from pipeline import effects

# AE 经 Camera Raw 直接导入 RAW 序列，也支持已导出的 JPG/TIF
SEQUENCE_EXTS = {".jpg", ".jpeg", ".tif", ".tiff", ".png",
                 ".arw", ".dng", ".cr2", ".cr3", ".nef", ".raf", ".orf"}

AERENDER = "/Applications/Adobe After Effects 2026/aerender"
AE_APP = "/Applications/Adobe After Effects 2026/Adobe After Effects 2026.app/Contents/MacOS/After Effects"

INTERMEDIATE_NAME = "_ae_intermediate.mov"
PRORES_OM_TEMPLATE = "Apple ProRes 4444"
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


def build_ae_script(anchor_file, fps, project_save_path, stabilize):
    """生成构建 AE 工程的 ExtendScript：导入序列→建合成→(增稳)→入渲染队列→保存。

    渲染由后续 aerender 执行；这里只搭好工程并保存。
    """
    return f"""
var anchor = new File("{anchor_file}");
var io = new ImportOptions(anchor);
if (io.canImportAs(ImportAsType.FOOTAGE)) {{
    io.importAs = ImportAsType.FOOTAGE;
}}
io.sequence = true;
var footage = app.project.importFile(io);
footage.mainSource.conformFrameRate = {fps};

var comp = app.project.items.addComp(
    "{COMP_NAME}",
    footage.width,
    footage.height,
    footage.pixelAspect,
    footage.duration,
    {fps}
);
comp.layers.add(footage);
{_stabilizer_jsx(stabilize)}
app.project.renderQueue.items.add(comp);

app.project.save(new File("{project_save_path}"));
app.quit();
""".strip()


def build_aerender_cmd(aerender, project_path, output_path):
    return [
        aerender,
        "-project", project_path,
        "-comp", COMP_NAME,
        "-OMtemplate", PRORES_OM_TEMPLATE,
        "-output", output_path,
    ]


def render_sequence(seq_folder, output_dir, fps, stabilize, emit, run=subprocess.run,
                    aerender=AERENDER, ae_app=AE_APP):
    """跑完整 AE 阶段，返回中间视频路径。

    run: 可注入的命令执行器（默认 subprocess.run），签名 run(cmd, **kwargs) -> 有 returncode 的对象。
    """
    anchor = find_sequence_anchor(seq_folder)
    out_video = intermediate_path(output_dir)
    proj_path = str(Path(tempfile.gettempdir()) / "timelapse_ae_project.aep")

    emit("AE 阶段：新建工程并导入图像序列…")
    jsx = build_ae_script(str(anchor), fps, proj_path, stabilize)
    with tempfile.NamedTemporaryFile("w", suffix=".jsx", delete=False) as f:
        f.write(jsx)
        jsx_path = f.name
    r1 = run([ae_app, "-r", jsx_path])
    if getattr(r1, "returncode", 0) != 0:
        raise RuntimeError("AE 建工程失败")

    emit("AE 阶段：aerender 渲染中间视频（ProRes 4444）…")
    cmd = build_aerender_cmd(aerender, proj_path, str(out_video))
    r2 = run(cmd)
    if getattr(r2, "returncode", 0) != 0:
        raise RuntimeError("aerender 渲染失败")

    if not out_video.exists():
        raise RuntimeError(f"未生成中间视频: {out_video}")
    emit("AE 阶段：完成")
    return out_video
