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
        "/x/bin", "/m.mov", "/s.mp4", "hevc", (1200, 0, 1440, 2560), (1080, 1920))
    assert cmd == ["/x/bin", "/m.mov", "/s.mp4", "hevc",
                   "1200", "0", "1440", "2560", "1080", "1920"]


def test_build_probe_cmd():
    assert export.build_probe_cmd("/x/bin", "/m.mov") == ["/x/bin", "--probe", "/m.mov"]


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
    assert tc[4:8] == ["1200", "0", "1440", "2560"]
    assert tc[8:10] == ["1080", "1920"]


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
