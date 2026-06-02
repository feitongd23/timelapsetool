import pytest

from pipeline import ae


def test_find_sequence_anchor_returns_first_sorted_image(tmp_path):
    (tmp_path / "seq_0003.jpg").write_text("c")
    (tmp_path / "seq_0001.jpg").write_text("a")
    (tmp_path / "seq_0002.jpg").write_text("b")
    (tmp_path / "notes.txt").write_text("x")
    anchor = ae.find_sequence_anchor(tmp_path)
    assert anchor.name == "seq_0001.jpg"


def test_find_sequence_anchor_accepts_tiff(tmp_path):
    (tmp_path / "0001.tif").write_text("a")
    assert ae.find_sequence_anchor(tmp_path).name == "0001.tif"


def test_find_sequence_anchor_no_images_raises(tmp_path):
    (tmp_path / "readme.txt").write_text("x")
    with pytest.raises(ValueError, match="序列"):
        ae.find_sequence_anchor(tmp_path)


def test_intermediate_path_derived_from_output(tmp_path):
    p = ae.intermediate_path(str(tmp_path))
    assert p.name == "_ae_intermediate.mov"
    assert p.parent == tmp_path


def test_build_ae_script_contains_paths_and_fps():
    jsx = ae.build_ae_script(
        anchor_file="/seq/0001.jpg",
        fps=30,
        project_save_path="/tmp/proj.aep",
    )
    assert "/seq/0001.jpg" in jsx
    assert "/tmp/proj.aep" in jsx
    assert "30" in jsx
    assert "Timelapse" in jsx
    assert "sequence" in jsx.lower()


def test_build_aerender_cmd_args():
    cmd = ae.build_aerender_cmd(
        aerender="/x/aerender",
        project_path="/tmp/proj.aep",
        output_path="/out/_ae_intermediate.mov",
    )
    assert cmd[0] == "/x/aerender"
    assert "-project" in cmd and "/tmp/proj.aep" in cmd
    assert "-comp" in cmd and "Timelapse" in cmd
    assert "-output" in cmd and "/out/_ae_intermediate.mov" in cmd
    assert "-OMtemplate" in cmd and "Apple ProRes 4444" in cmd


def test_render_sequence_invokes_ae_then_aerender(tmp_path):
    seq = tmp_path / "seq"; seq.mkdir(); (seq / "0001.jpg").write_text("i")
    out = tmp_path / "out"; out.mkdir()
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0].endswith("aerender"):
            ae.intermediate_path(str(out)).write_text("video")
        class R: returncode = 0
        return R()

    result = ae.render_sequence(
        seq_folder=str(seq), output_dir=str(out), fps=24,
        emit=lambda m: None, run=fake_run,
        aerender="/x/aerender", ae_app="/x/AE",
    )
    assert result == ae.intermediate_path(str(out))
    assert result.exists()
    assert "/x/AE" in calls[0]
    assert calls[1][0] == "/x/aerender"


def test_render_sequence_missing_output_raises(tmp_path):
    seq = tmp_path / "seq"; seq.mkdir(); (seq / "0001.jpg").write_text("i")
    out = tmp_path / "out"; out.mkdir()

    def fake_run(cmd, **kwargs):
        class R: returncode = 0
        return R()

    with pytest.raises(RuntimeError, match="中间视频"):
        ae.render_sequence(
            seq_folder=str(seq), output_dir=str(out), fps=24,
            emit=lambda m: None, run=fake_run,
            aerender="/x/aerender", ae_app="/x/AE",
        )


def test_render_sequence_nonzero_returncode_raises(tmp_path):
    seq = tmp_path / "seq"; seq.mkdir(); (seq / "0001.jpg").write_text("i")
    out = tmp_path / "out"; out.mkdir()

    def fake_run(cmd, **kwargs):
        class R: returncode = 1
        return R()

    with pytest.raises(RuntimeError, match="失败"):
        ae.render_sequence(
            seq_folder=str(seq), output_dir=str(out), fps=24,
            emit=lambda m: None, run=fake_run,
            aerender="/x/aerender", ae_app="/x/AE",
        )
