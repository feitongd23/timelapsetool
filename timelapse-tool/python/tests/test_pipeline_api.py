import json

from fastapi.testclient import TestClient

import server

client = TestClient(server.app)

SOCIAL = {"format": "H.265", "aspect": "9:16", "resolution": "1080p"}


def test_pipeline_start_two_pauses_then_done(tmp_path, monkeypatch):
    # AE 阶段会真的启动 After Effects，测试里 mock 掉，只验流程
    from pipeline import ae, export
    monkeypatch.setattr(ae, "render_sequence",
                        lambda seq_folder, output_dir, fps, emit, **kw: emit("AE mock"))
    monkeypatch.setattr(ae, "merge_chunks",
                        lambda chunks, output_dir, emit, **kw: emit("merge mock"))
    monkeypatch.setattr(export, "render_exports",
                        lambda intermediate_video, output_dir, social, emit, **kw: emit("EXPORT mock"))
    raw = tmp_path / "raw"; raw.mkdir()
    lrt = tmp_path / "seq"; lrt.mkdir(); (lrt / "0001.tif").write_text("i")
    out = tmp_path / "out"; out.mkdir()
    body = dict(
        raw_folder=str(raw),
        stabilize={"enabled": False},
        fps=24, social=SOCIAL, output_path=str(out),
    )
    # start → 停在 BR（手动）
    r = client.post("/pipeline/start", json=body)
    assert r.status_code == 200
    assert r.json()["state"] == "waiting_for_user"
    assert r.json()["current_stage"] == "BR"

    # continue → 停在 LRT（手动）
    r2 = client.post("/pipeline/continue")
    assert r2.json()["state"] == "waiting_for_user"
    assert r2.json()["current_stage"] == "LRT"

    # continue → 跑完 AE/导出
    r3 = client.post("/pipeline/continue")
    assert r3.status_code == 200
    assert r3.json()["state"] == "done"


def test_pipeline_start_bad_fps_400(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    lrt = tmp_path / "seq"; lrt.mkdir()
    out = tmp_path / "out"; out.mkdir()
    body = dict(
        raw_folder=str(raw),
        stabilize={"enabled": False},
        fps=0, social=SOCIAL, output_path=str(out),
    )
    r = client.post("/pipeline/start", json=body)
    assert r.status_code == 400


def test_get_workflows_lists_builtin():
    r = client.get("/workflows")
    assert r.status_code == 200
    wf = r.json()["workflows"]
    assert wf["全流程"] == ["BR", "LRT", "AE", "导出"]
    assert "极简" in wf


def test_start_with_custom_workflow_runs_only_those_stages(tmp_path, monkeypatch):
    from pipeline import ae, export
    monkeypatch.setattr(ae, "render_sequence",
                        lambda seq_folder, output_dir, fps, emit, **kw: emit("AE"))
    monkeypatch.setattr(ae, "merge_chunks",
                        lambda chunks, output_dir, emit, **kw: emit("merge"))
    monkeypatch.setattr(export, "render_exports",
                        lambda intermediate_video, output_dir, social, emit, **kw: emit("EXPORT"))
    raw = tmp_path / "raw"; raw.mkdir()
    lrt = tmp_path / "seq"; lrt.mkdir(); (lrt / "0001.tif").write_text("i")
    out = tmp_path / "out"; out.mkdir()
    body = dict(
        raw_folder=str(raw),
        stabilize={"enabled": False},
        fps=24, social=SOCIAL,
        output_path=str(out), workflow=["LRT", "AE"],
    )
    r = client.post("/pipeline/start", json=body)
    assert r.status_code == 200
    assert r.json()["current_stage"] == "LRT"
    r2 = client.post("/pipeline/continue")
    assert r2.json()["state"] == "done"


def test_save_custom_workflow(tmp_path, monkeypatch):
    from pipeline import workflows
    p = tmp_path / "workflows.json"; p.write_text('{"workflows": {}}')
    monkeypatch.setattr(server, "_workflow_store", workflows.WorkflowStore(p))
    r = client.post("/workflows", json={"name": "测试流", "stages": ["LRT", "AE", "导出"]})
    assert r.status_code == 201
    assert "测试流" in client.get("/workflows").json()["workflows"]


def test_preview_frames(tmp_path):
    for n in ["0001.jpg", "0002.jpg", "0003.jpg"]:
        (tmp_path / n).write_text("x")
    r = client.get("/preview/frames", params={"folder": str(tmp_path)})
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 3
    assert data["strip"] == ["0001.jpg", "0002.jpg", "0003.jpg"]
    assert "0001.jpg" in data["anim"]


def test_preview_frames_empty(tmp_path):
    r = client.get("/preview/frames", params={"folder": str(tmp_path)})
    assert r.json()["count"] == 0


def test_start_repairs_wrapped_sequence(tmp_path, monkeypatch):
    # 模拟 9999→0001 回绕：在 raw 里建两文件，注入拍摄时间让 0001 在 9999 之后
    from pipeline import ae, export, sequence
    monkeypatch.setattr(ae, "render_sequence",
                        lambda seq_folder, output_dir, fps, emit, **kw: emit("AE"))
    monkeypatch.setattr(ae, "merge_chunks",
                        lambda chunks, output_dir, emit, **kw: emit("merge"))
    monkeypatch.setattr(export, "render_exports",
                        lambda intermediate_video, output_dir, social, emit, **kw: emit("EXPORT"))
    times = {"DSC09999.ARW": "2026-06-03 01:00:00 +0000",
             "DSC00001.ARW": "2026-06-03 01:00:05 +0000"}
    monkeypatch.setattr(sequence, "default_time_of",
                        lambda p: times.get(__import__("os").path.basename(p), "z"))
    raw = tmp_path / "raw"; raw.mkdir()
    (raw / "DSC09999.ARW").write_text("a"); (raw / "DSC00001.ARW").write_text("b")
    lrt = tmp_path / "seq"; lrt.mkdir(); (lrt / "0001.tif").write_text("i")
    out = tmp_path / "out"; out.mkdir()
    body = dict(
        raw_folder=str(raw),
        stabilize={"enabled": False},
        fps=24, social=SOCIAL,
        output_path=str(out),
    )
    r = client.post("/pipeline/start", json=body)
    assert r.status_code == 200
    assert "回绕" in (r.json().get("notice") or "")  # 提示用户已整理
    # 已生成整理后的 _seq 文件夹，连续命名
    seq_dir = tmp_path / "raw_seq"
    assert seq_dir.is_dir()
    assert sorted(p.name for p in seq_dir.iterdir()) == ["TL_0001.ARW", "TL_0002.ARW"]


def test_preview_best_frame(tmp_path, monkeypatch):
    from pipeline import preview, export
    monkeypatch.setattr(export, "ensure_export_binary", lambda *a, **k: "/bin")
    monkeypatch.setattr(preview, "best_frame", lambda folder, binary, **k: "0002.jpg")
    r = client.get("/preview/best_frame", params={"folder": str(tmp_path)})
    assert r.status_code == 200
    assert r.json()["name"] == "0002.jpg"


def test_preview_meta(tmp_path, monkeypatch):
    from pipeline import preview, export
    monkeypatch.setattr(export, "ensure_export_binary", lambda *a, **k: "/bin")
    monkeypatch.setattr(preview, "read_metadata", lambda folder, binary, **k: {"camera": "ILCE-7RM4A", "width": 9504})
    r = client.get("/preview/meta", params={"folder": str(tmp_path)})
    assert r.status_code == 200
    assert r.json()["camera"] == "ILCE-7RM4A"


def test_preview_file_thumb_missing_404():
    r = client.get("/preview/file_thumb", params={"src": "/no/such/file.mov"})
    assert r.status_code == 404


def test_preview_file_thumb_ok(tmp_path, monkeypatch):
    src = tmp_path / "clip.mov"; src.write_text("x")
    thumb = tmp_path / "t.png"; thumb.write_bytes(b"\x89PNG\r\n")
    from pipeline import preview
    monkeypatch.setattr(preview, "generate_thumbnail", lambda s, size, cache, **k: str(thumb))
    r = client.get("/preview/file_thumb", params={"src": str(src)})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


def test_export_social_from_missing_src_404():
    r = client.post("/export/social_from", json={"src": "/no/file.mov", "social": SOCIAL})
    assert r.status_code == 404


def test_export_social_from_ok(tmp_path, monkeypatch):
    src = tmp_path / "clip.mov"; src.write_text("x")
    from pipeline import export
    monkeypatch.setattr(export, "ensure_export_binary", lambda *a, **k: "/bin")
    monkeypatch.setattr(export, "transcode_social",
                        lambda s, out_dir, social, emit, **k: __import__("pathlib").Path(out_dir) / "clip_social_1080x1920_h265.mp4")
    r = client.post("/export/social_from", json={"src": str(src), "social": SOCIAL})
    assert r.status_code == 200
    assert r.json()["output"].endswith("clip_social_1080x1920_h265.mp4")
