# Copyright (c) 2026 杜非同. All rights reserved.
# Part of Timelapse Tool — proprietary software.
# Unauthorized copying, modification, or distribution is prohibited.

import json

from fastapi.testclient import TestClient

import server

client = TestClient(server.app)

SOCIAL = {"format": "H.265", "aspect": "9:16", "resolution": "1080p"}


def _join_worker():
    if server._worker is not None:
        server._worker.join(5)


def test_pipeline_start_two_pauses_then_done(tmp_path, monkeypatch):
    # AE/导出真跑会启动 AE，测试里 mock；launcher 也 mock 避免真开 Bridge/LRT
    from pipeline import ae, export, launcher
    monkeypatch.setattr(launcher, "open_in_app", lambda *a, **k: None)
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
    # start → 停在 BR（手动），异步执行先等线程到稳定态
    r = client.post("/pipeline/start", json=body); _join_worker()
    assert r.status_code == 200
    s = client.get("/pipeline/status").json()
    assert s["state"] == "waiting_for_user" and s["current_stage"] == "BR"

    # continue → 停在 LRT（手动）
    client.post("/pipeline/continue"); _join_worker()
    s = client.get("/pipeline/status").json()
    assert s["state"] == "waiting_for_user" and s["current_stage"] == "LRT"

    # continue → 跑完 AE/导出
    client.post("/pipeline/continue"); _join_worker()
    s = client.get("/pipeline/status").json()
    assert s["state"] == "done"


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
    from pipeline import ae, export, launcher
    monkeypatch.setattr(launcher, "open_in_app", lambda *a, **k: None)
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
    r = client.post("/pipeline/start", json=body); _join_worker()
    assert r.status_code == 200
    s = client.get("/pipeline/status").json()
    assert s["current_stage"] == "LRT"
    client.post("/pipeline/continue"); _join_worker()
    s = client.get("/pipeline/status").json()
    assert s["state"] == "done"


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


def test_continue_rejects_when_busy(monkeypatch):
    import threading, time
    t = threading.Thread(target=lambda: time.sleep(1), daemon=True); t.start()
    monkeypatch.setattr(server, "_worker", t)
    try:
        assert client.post("/pipeline/continue").status_code == 409
    finally:
        t.join()


def test_pipeline_reset_returns_idle():
    r = client.post("/pipeline/reset")
    assert r.status_code == 200
    assert r.json()["state"] == "idle"
    assert r.json()["current_stage"] is None


def test_reset_rejects_when_busy(monkeypatch):
    import threading, time
    t = threading.Thread(target=lambda: time.sleep(1), daemon=True); t.start()
    monkeypatch.setattr(server, "_worker", t)
    try:
        assert client.post("/pipeline/reset").status_code == 409
    finally:
        t.join()
