import pytest

from pipeline import pr


def test_final_output_path_ext_by_codec(tmp_path):
    p = pr.final_output_path(str(tmp_path), {"codec": "ProRes"})
    assert p.name == "timelapse_final.mov"
    p2 = pr.final_output_path(str(tmp_path), {"codec": "H.264"})
    assert p2.name == "timelapse_final.mp4"
    p3 = pr.final_output_path(str(tmp_path), {"codec": "H.265"})
    assert p3.name == "timelapse_final.mp4"


def test_build_pr_script_contains_paths():
    jsx = pr.build_pr_script("/in/_ae_intermediate.mov", "/out/timelapse_final.mp4", "/p/h264.epr")
    assert "/in/_ae_intermediate.mov" in jsx
    assert "/out/timelapse_final.mp4" in jsx
    assert "/p/h264.epr" in jsx
    assert "exportAsMediaDirect" in jsx


def test_build_pr_cmd():
    cmd = pr.build_pr_cmd("/x/PR", "/tmp/s.jsx")
    assert cmd[0] == "/x/PR"
    assert "/tmp/s.jsx" in cmd


def test_render_final_invokes_pr_and_returns_output(tmp_path):
    inter = tmp_path / "_ae_intermediate.mov"; inter.write_text("vid")
    out = tmp_path / "out"; out.mkdir()
    export = {"codec": "H.264", "container": "MP4", "bitrate_mbps": 80, "quality": "high"}
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        pr.final_output_path(str(out), export).write_text("final")
        class R: returncode = 0
        return R()

    result = pr.render_final(str(inter), str(out), export, emit=lambda m: None,
                             run=fake_run, pr_app="/x/PR", preset_map={"H.264": "/p/h264.epr"})
    assert result == pr.final_output_path(str(out), export)
    assert result.exists()
    assert calls[0][0] == "/x/PR"


def test_render_final_missing_intermediate_raises(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    export = {"codec": "H.264"}
    with pytest.raises(RuntimeError, match="中间视频"):
        pr.render_final(str(tmp_path / "nope.mov"), str(out), export,
                        emit=lambda m: None, run=lambda c, **k: None, pr_app="/x/PR")


def test_render_final_missing_output_raises(tmp_path):
    inter = tmp_path / "_ae_intermediate.mov"; inter.write_text("vid")
    out = tmp_path / "out"; out.mkdir()
    export = {"codec": "ProRes"}

    def fake_run(cmd, **kwargs):
        class R: returncode = 0
        return R()  # 不生成成片

    with pytest.raises(RuntimeError, match="成片"):
        pr.render_final(str(inter), str(out), export, emit=lambda m: None,
                        run=fake_run, pr_app="/x/PR", preset_map={"ProRes": ""})


def test_render_final_nonzero_returncode_raises(tmp_path):
    inter = tmp_path / "_ae_intermediate.mov"; inter.write_text("vid")
    out = tmp_path / "out"; out.mkdir()
    export = {"codec": "ProRes"}

    def fake_run(cmd, **kwargs):
        class R: returncode = 1
        return R()

    with pytest.raises(RuntimeError, match="失败"):
        pr.render_final(str(inter), str(out), export, emit=lambda m: None,
                        run=fake_run, pr_app="/x/PR", preset_map={"ProRes": ""})
