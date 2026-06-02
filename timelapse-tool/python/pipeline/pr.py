"""PR 阶段：把 AE 输出的 ProRes 4444 中间视频导入 Premiere，按导出格式出片。

Premiere 的脚本化导出依赖导出预设(.epr)；各编码对应的 .epr 路径是真机常量，
需在本机的 Premiere 里「导出 > 存储预设」生成后回填 PRESET_EPR。
本模块负责：确定成片路径、生成导入+导出 jsx、拼装启动命令、编排执行（可注入 run 测试）。
"""

import subprocess
import tempfile
from pathlib import Path

PR_APP = "/Applications/Adobe Premiere Pro 2026/Adobe Premiere Pro 2026.app/Contents/MacOS/Adobe Premiere Pro 2026"

# 编码 → 成片容器扩展名
_EXT = {"ProRes": "mov", "H.264": "mp4", "H.265": "mp4"}

# 编码 → 导出预设(.epr) 路径 —— 真机回填（在 Premiere 里导出各格式时「存储预设」生成）
PRESET_EPR = {
    "ProRes": "",   # 待真机回填 .epr 路径
    "H.264": "",
    "H.265": "",
}

FINAL_BASENAME = "timelapse_final"


def final_output_path(output_dir, export):
    """成片路径：<output_dir>/timelapse_final.<ext>，ext 由编码决定。"""
    ext = _EXT[export["codec"]]
    return Path(output_dir) / f"{FINAL_BASENAME}.{ext}"


def build_pr_script(intermediate_video, output_path, preset_epr):
    """生成 Premiere ExtendScript：新建工程→导入中间视频→建序列→按预设导出。"""
    return f"""
app.newProject("");
var proj = app.project;
proj.importFiles(["{intermediate_video}"], true, proj.rootItem, false);
var clip = proj.rootItem.children[0];
var seq = proj.createNewSequenceFromClips("Timelapse", [clip]);
proj.activeSequence = seq;
seq.exportAsMediaDirect("{output_path}", "{preset_epr}", 1);  // 1 = 整个序列
""".strip()


def build_pr_cmd(pr_app, script_path):
    """用 Premiere 运行脚本的命令。真机可能需改为其它驱动方式（启动脚本/CEP）。"""
    return [pr_app, "--executeScript", script_path]


def render_final(intermediate_video, output_dir, export, emit, run=subprocess.run,
                 pr_app=PR_APP, preset_map=PRESET_EPR):
    """导入中间视频并按导出格式出片，返回成片路径。run 可注入便于测试。"""
    intermediate = Path(intermediate_video)
    if not intermediate.exists():
        raise RuntimeError(f"AE 中间视频不存在: {intermediate}")

    out_path = final_output_path(output_dir, export)
    preset_epr = preset_map.get(export["codec"], "")

    emit(f"PR 阶段：导入中间视频，按 {export['codec']} 导出…")
    jsx = build_pr_script(str(intermediate), str(out_path), preset_epr)
    with tempfile.NamedTemporaryFile("w", suffix=".jsx", delete=False) as f:
        f.write(jsx)
        script_path = f.name

    r = run(build_pr_cmd(pr_app, script_path))
    if getattr(r, "returncode", 0) != 0:
        raise RuntimeError("Premiere 导出失败")
    if not out_path.exists():
        raise RuntimeError(f"未生成成片: {out_path}")
    emit("PR 阶段：完成")
    return out_path
