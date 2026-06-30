# Copyright (c) 2026 杜非同. All rights reserved.
# Part of Timelapse Tool — proprietary software.
# Unauthorized copying, modification, or distribution is prohibited.

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
        "/x/bin", "/m.mov", "/s.mp4", "hevc",
        (1200, 0, 1440, 2560), (1100, 0, 1320, 2348), (1080, 1920))
    assert cmd == ["/x/bin", "/m.mov", "/s.mp4", "hevc",
                   "1200", "0", "1440", "2560",        # 起始框
                   "1100", "0", "1320", "2348",        # 结束框
                   "1080", "1920"]                     # 输出尺寸


def test_build_probe_cmd():
    assert export.build_probe_cmd("/x/bin", "/m.mov") == ["/x/bin", "--probe", "/m.mov"]


def test_build_saliency_cmd():
    assert export.build_saliency_cmd("/x/bin", "/m.mov") == ["/x/bin", "--saliency", "/m.mov"]


def _r(returncode, stdout=""):
    return type("R", (), {"returncode": returncode, "stdout": stdout})()


def test_saliency_center_parses_or_falls_back():
    assert export.saliency_center("/b", "/m", run=lambda c, **k: _r(0, "0.3 0.6\n")) == (0.3, 0.6)
    assert export.saliency_center("/b", "/m", run=lambda c, **k: _r(1, "")) == (0.5, 0.5)


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
    assert not inter.exists()                       # 母版是"移动"得到的
    assert social_out.name == "timelapse_social_1080x1920_h265.mp4" and social_out.exists()
    assert calls[0][1] == "--probe"
    tc = calls[-1]
    assert tc[3] == "hevc"
    # 无运镜：起=止=中心裁框，输出 1080x1920
    assert tc[4:8] == ["1200", "0", "1440", "2560"]    # 起始框
    assert tc[8:12] == ["1200", "0", "1440", "2560"]   # 结束框（=起始）
    assert tc[12:14] == ["1080", "1920"]               # 输出尺寸


def test_render_exports_subject_uses_saliency_anchor(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    inter = out / "_ae_intermediate.mov"; inter.write_bytes(_MOOV)
    fake_bin = tmp_path / "bin"; fake_bin.write_text("b")
    social = {"format": "H.265", "aspect": "9:16", "resolution": "1080p", "subject": True}
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        sub = len(cmd) > 1 and cmd[1] == "--saliency"
        out_stdout = "0.2 0.5\n" if sub else "3840 2560\n"
        if cmd[1] not in ("--probe", "--saliency"):
            Path(cmd[2]).write_bytes(_MOOV)
        return type("R", (), {"returncode": 0, "stdout": out_stdout})()

    export.render_exports(str(inter), str(out), social, emit=lambda m: None,
                          run=fake_run, binary=str(fake_bin))
    assert any(len(c) > 1 and c[1] == "--saliency" for c in calls)  # 调了显著性检测
    tc = calls[-1]
    # 锚点 cx=0.2 → 9:16 裁框 x=48（不再是中心 1200）
    assert tc[4] == "48"


def test_render_exports_kenburns_start_differs_from_end(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    inter = out / "_ae_intermediate.mov"; inter.write_bytes(_MOOV)
    fake_bin = tmp_path / "bin"; fake_bin.write_text("b")
    social = {"format": "H.265", "aspect": "9:16", "resolution": "1080p",
              "motion": {"type": "kenburns", "direction": "in", "intensity": "medium"}}

    def fake_run(cmd, **kw):
        if cmd[1] not in ("--probe", "--saliency"):
            Path(cmd[2]).write_bytes(_MOOV)
        return type("R", (), {"returncode": 0, "stdout": "3840 2560\n"})()

    calls = []
    orig = fake_run
    def rec(cmd, **kw):
        calls.append(cmd); return orig(cmd, **kw)

    export.render_exports(str(inter), str(out), social, emit=lambda m: None,
                          run=rec, binary=str(fake_bin))
    tc = calls[-1]
    # Ken Burns 推近：起始框 ≠ 结束框
    assert tc[4:8] != tc[8:12]


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
    assert not any(len(c) > 1 and c[1] == "--saliency" for c in calls)
    tc = calls[-1]
    assert tc[4:8] != tc[8:12]


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


def test_master_path_custom_prefix():
    assert export.master_path("/out", prefix="myclip").name == "myclip_master.mov"
