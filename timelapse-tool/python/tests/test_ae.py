from pathlib import Path

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


DISABLED = {"enabled": False}


def test_build_ae_script_contains_paths_and_fps():
    jsx = ae.build_ae_script(
        anchor_file="/seq/0001.jpg",
        fps=30,

        project_save_path="/tmp/proj.aep",
        stabilize=DISABLED,
    )
    assert "/seq/0001.jpg" in jsx
    assert "/tmp/proj.aep" in jsx
    assert "30" in jsx
    assert "Timelapse" in jsx
    assert "sequence" in jsx.lower()


def test_build_ae_script_skips_stabilizer_when_disabled():
    jsx = ae.build_ae_script(
        anchor_file="/seq/0001.jpg", fps=24,
        project_save_path="/tmp/p.aep", stabilize={"enabled": False},
    )
    assert ae.effects.WARP_STABILIZER_MATCHNAME not in jsx


def test_build_ae_script_adds_stabilizer_when_enabled():
    jsx = ae.build_ae_script(
        anchor_file="/seq/0001.jpg", fps=24,
        project_save_path="/tmp/p.aep",
        stabilize={"enabled": True, "result": "smooth", "smoothness": 70, "method": "subspace"},
    )
    assert ae.effects.WARP_STABILIZER_MATCHNAME in jsx
    assert "70" in jsx          # 平滑度
    assert "setValue(4)" in jsx  # subspace → 4
    assert "setValue(1)" in jsx  # smooth → 1


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
    assert "-OMtemplate" in cmd and "ProRes 4444" in cmd


def _mk_seq(tmp_path, n):
    seq = tmp_path / "seq"; seq.mkdir()
    for i in range(1, n + 1):
        (seq / f"{i:04d}.jpg").write_text("i")
    return seq


def test_render_sequence_builds_then_chunks(tmp_path):
    seq = _mk_seq(tmp_path, 250)  # 250 帧, chunk=100 → 3 段
    out = tmp_path / "out"; out.mkdir()
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0].endswith("aerender"):
            # 模拟 aerender 生成该段输出文件（-output 的下一个参数）
            outp = cmd[cmd.index("-output") + 1]
            __import__("pathlib").Path(outp).write_bytes(b"\x00\x00\x00\x08moov" + b"\x00" * 1100)
        class R: returncode = 0
        return R()

    chunks = ae.render_sequence(
        seq_folder=str(seq), output_dir=str(out), fps=24,
        stabilize={"enabled": False}, emit=lambda m: None, run=fake_run,
        aerender="/x/aerender", ae_app_name="TestAE", chunk=100,
    )
    # 先 AE 建工程，再 3 段 aerender
    assert calls[0][0] == "osascript" and "DoScriptFile" in calls[0][2]
    aer = [c for c in calls if c[0] == "/x/aerender"]
    assert len(aer) == 3
    # 帧范围正确
    assert "-s" in aer[0] and aer[0][aer[0].index("-s") + 1] == "0"
    assert aer[0][aer[0].index("-e") + 1] == "99"
    assert aer[2][aer[2].index("-s") + 1] == "200"
    assert aer[2][aer[2].index("-e") + 1] == "249"
    assert len(chunks) == 3
    assert all(__import__("pathlib").Path(c).exists() for c in chunks)


def test_render_sequence_retries_failed_chunk(tmp_path):
    seq = _mk_seq(tmp_path, 50)  # 1 段
    out = tmp_path / "out"; out.mkdir()
    attempts = {"n": 0}

    def fake_run(cmd, **kwargs):
        if cmd[0].endswith("aerender"):
            attempts["n"] += 1
            if attempts["n"] < 2:
                class F: returncode = 1  # 第一次失败
                return F()
            outp = cmd[cmd.index("-output") + 1]
            __import__("pathlib").Path(outp).write_bytes(b"\x00\x00\x00\x08moov" + b"\x00" * 1100)
        class R: returncode = 0
        return R()

    chunks = ae.render_sequence(
        seq_folder=str(seq), output_dir=str(out), fps=24,
        stabilize={"enabled": False}, emit=lambda m: None, run=fake_run,
        aerender="/x/aerender", ae_app_name="TestAE", chunk=100, retries=3,
    )
    assert len(chunks) == 1
    assert attempts["n"] == 2  # 重试后第二次成功


def test_render_sequence_chunk_fails_all_retries(tmp_path):
    seq = _mk_seq(tmp_path, 50)
    out = tmp_path / "out"; out.mkdir()

    def fake_run(cmd, **kwargs):
        class R: returncode = 0 if not cmd[0].endswith("aerender") else 1
        return R()

    with pytest.raises(RuntimeError, match="失败"):
        ae.render_sequence(
            seq_folder=str(seq), output_dir=str(out), fps=24,
            stabilize={"enabled": False}, emit=lambda m: None, run=fake_run,
            aerender="/x/aerender", ae_app_name="TestAE", chunk=100, retries=3,
        )


# ---- 分块片段合并成中间视频 ----

_MOOV = b"\x00\x00\x00\x08moov" + b"\x00" * 1100  # 假装封口完整的 MOV


def test_build_concat_cmd_order():
    cmd = ae.build_concat_cmd("/x/bin", "/out/_ae_intermediate.mov",
                              ["/a/chunk_000.mov", "/a/chunk_001.mov"])
    assert cmd == ["/x/bin", "/out/_ae_intermediate.mov",
                   "/a/chunk_000.mov", "/a/chunk_001.mov"]


def test_merge_chunks_builds_intermediate(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    chunks = [str(tmp_path / f"chunk_{i:03d}.mov") for i in range(3)]
    for c in chunks:
        Path(c).write_bytes(_MOOV)
    fake_bin = tmp_path / "concat_bin"; fake_bin.write_text("bin")  # 已存在→跳过编译
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if cmd[0] == str(fake_bin):
            Path(cmd[1]).write_bytes(_MOOV)  # 模拟拼接出封口 MOV
        class R: returncode = 0
        return R()

    result = ae.merge_chunks(chunks, str(out), emit=lambda m: None,
                             run=fake_run, binary=str(fake_bin))
    assert result == ae.intermediate_path(str(out))
    assert result.exists()
    # 拼接命令含全部片段、按序、输出在前
    concat = calls[-1]
    assert concat[0] == str(fake_bin)
    assert concat[1] == str(ae.intermediate_path(str(out)))
    assert concat[2:] == chunks


def test_merge_chunks_compiles_binary_when_missing(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    chunks = [str(tmp_path / "chunk_000.mov")]; Path(chunks[0]).write_bytes(_MOOV)
    binary = tmp_path / "concat_bin"  # 不存在 → 触发 swiftc 编译
    compiled = []

    def fake_run(cmd, **kw):
        if cmd[0] == "swiftc":
            out_i = cmd.index("-o")
            Path(cmd[out_i + 1]).write_text("compiled")
            compiled.append(cmd)
        else:
            Path(cmd[1]).write_bytes(_MOOV)
        class R: returncode = 0
        return R()

    ae.merge_chunks(chunks, str(out), emit=lambda m: None,
                    run=fake_run, binary=str(binary))
    assert binary.exists()
    assert compiled and "mov_concat.swift" in compiled[0][-3]


def test_merge_chunks_empty_raises(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    with pytest.raises(RuntimeError, match="片段"):
        ae.merge_chunks([], str(out), emit=lambda m: None,
                        run=lambda c, **k: None, binary=str(tmp_path / "b"))


def test_merge_chunks_invalid_output_raises(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    chunks = [str(tmp_path / "chunk_000.mov")]; Path(chunks[0]).write_bytes(_MOOV)
    fake_bin = tmp_path / "b"; fake_bin.write_text("b")

    def fake_run(cmd, **kw):
        class R: returncode = 0
        return R()  # 不生成有效 MOV

    with pytest.raises(RuntimeError, match="合并"):
        ae.merge_chunks(chunks, str(out), emit=lambda m: None,
                        run=fake_run, binary=str(fake_bin))
