import json

from fastapi.testclient import TestClient

import server
from pipeline.cameras import CameraStore

client = TestClient(server.app)


def test_get_cameras_lists_presets():
    r = client.get("/cameras")
    assert r.status_code == 200
    names = [c["name"] for c in r.json()["cameras"]]
    assert "Sony A7R IV" in names


def test_get_resolutions_for_camera():
    r = client.get("/cameras/Sony A7R IV/resolutions")
    assert r.status_code == 200
    assert r.json()["options"][0]["label"] == "原分辨率"


def test_get_resolutions_unknown_camera_404():
    r = client.get("/cameras/Nope/resolutions")
    assert r.status_code == 404


def test_pipeline_start_two_pauses_then_done(tmp_path, monkeypatch):
    # AE 阶段会真的启动 After Effects，测试里 mock 掉，只验流程
    from pipeline import ae, pr
    monkeypatch.setattr(ae, "render_sequence",
                        lambda seq_folder, output_dir, fps, emit, **kw: emit("AE mock"))
    monkeypatch.setattr(ae, "merge_chunks",
                        lambda chunks, output_dir, emit, **kw: emit("merge mock"))
    monkeypatch.setattr(pr, "render_final",
                        lambda intermediate_video, output_dir, export, emit, **kw: emit("PR mock"))
    raw = tmp_path / "raw"; raw.mkdir()
    lrt = tmp_path / "seq"; lrt.mkdir(); (lrt / "0001.tif").write_text("i")
    out = tmp_path / "out"; out.mkdir()
    body = dict(
        raw_folder=str(raw), camera_name="Sony A7R IV",
        stabilize={"enabled": False}, resolution=[3840, 2160],
        fps=24, export={"codec": "ProRes", "container": "MOV", "prores_profile": "422 HQ"}, output_path=str(out),
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

    # continue → 跑完 AE/PR
    r3 = client.post("/pipeline/continue")
    assert r3.status_code == 200
    assert r3.json()["state"] == "done"


def test_pipeline_start_bad_fps_400(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    lrt = tmp_path / "seq"; lrt.mkdir()
    out = tmp_path / "out"; out.mkdir()
    body = dict(
        raw_folder=str(raw), camera_name="Sony A7R IV",
        stabilize={"enabled": False}, resolution=[3840, 2160],
        fps=0, export={"codec": "ProRes", "container": "MOV", "prores_profile": "422 HQ"}, output_path=str(out),
    )
    r = client.post("/pipeline/start", json=body)
    assert r.status_code == 400


def test_add_camera_then_listed(tmp_path, monkeypatch):
    # 用临时 cameras.json 隔离，避免污染仓库里的真实配置
    cfg = tmp_path / "cameras.json"
    cfg.write_text(json.dumps({"cameras": [{"name": "Sony A7R IV", "native": [9504, 6336]}]}))
    monkeypatch.setattr(server, "_camera_store", CameraStore(cfg))

    r = client.post("/cameras", json={"name": "Test Cam X", "native": [6000, 4000]})
    assert r.status_code == 201
    names = [c["name"] for c in client.get("/cameras").json()["cameras"]]
    assert "Test Cam X" in names


def test_get_export_presets():
    r = client.get("/export/presets")
    assert r.status_code == 200
    names = r.json()["presets"]
    assert "母版 · ProRes 422 HQ" in names
    assert "社媒 · H.264 高质量" in names


def test_pipeline_start_with_preset(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    lrt = tmp_path / "seq"; lrt.mkdir(); (lrt / "0001.tif").write_text("i")
    out = tmp_path / "out"; out.mkdir()
    body = dict(
        raw_folder=str(raw), camera_name="Sony A7R IV",
        stabilize={"enabled": False}, resolution=[3840, 2160],
        fps=24, output_path=str(out), preset="母版 · ProRes 422 HQ",
    )
    r = client.post("/pipeline/start", json=body)
    assert r.status_code == 200
    assert r.json()["state"] == "waiting_for_user"


def test_get_workflows_lists_builtin():
    r = client.get("/workflows")
    assert r.status_code == 200
    wf = r.json()["workflows"]
    assert wf["全流程"] == ["BR", "LRT", "AE", "PR"]
    assert "极简" in wf


def test_start_with_custom_workflow_runs_only_those_stages(tmp_path, monkeypatch):
    from pipeline import ae, pr
    monkeypatch.setattr(ae, "render_sequence",
                        lambda seq_folder, output_dir, fps, emit, **kw: emit("AE"))
    monkeypatch.setattr(ae, "merge_chunks",
                        lambda chunks, output_dir, emit, **kw: emit("merge"))
    monkeypatch.setattr(pr, "render_final",
                        lambda intermediate_video, output_dir, export, emit, **kw: emit("PR"))
    raw = tmp_path / "raw"; raw.mkdir()
    lrt = tmp_path / "seq"; lrt.mkdir(); (lrt / "0001.tif").write_text("i")
    out = tmp_path / "out"; out.mkdir()
    body = dict(
        raw_folder=str(raw), camera_name="Sony A7R IV",
        stabilize={"enabled": False}, resolution=[3840, 2160],
        fps=24, export={"codec": "ProRes", "container": "MOV", "prores_profile": "422 HQ"},
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
    r = client.post("/workflows", json={"name": "测试流", "stages": ["LRT", "AE", "PR"]})
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
    from pipeline import ae, pr, sequence
    monkeypatch.setattr(ae, "render_sequence",
                        lambda seq_folder, output_dir, fps, emit, **kw: emit("AE"))
    monkeypatch.setattr(ae, "merge_chunks",
                        lambda chunks, output_dir, emit, **kw: emit("merge"))
    monkeypatch.setattr(pr, "render_final",
                        lambda intermediate_video, output_dir, export, emit, **kw: emit("PR"))
    times = {"DSC09999.ARW": "2026-06-03 01:00:00 +0000",
             "DSC00001.ARW": "2026-06-03 01:00:05 +0000"}
    monkeypatch.setattr(sequence, "default_time_of",
                        lambda p: times.get(__import__("os").path.basename(p), "z"))
    raw = tmp_path / "raw"; raw.mkdir()
    (raw / "DSC09999.ARW").write_text("a"); (raw / "DSC00001.ARW").write_text("b")
    lrt = tmp_path / "seq"; lrt.mkdir(); (lrt / "0001.tif").write_text("i")
    out = tmp_path / "out"; out.mkdir()
    body = dict(
        raw_folder=str(raw), camera_name="Sony A7R IV",
        stabilize={"enabled": False}, resolution=[3840, 2160],
        fps=24, export={"codec": "ProRes", "container": "MOV", "prores_profile": "422 HQ"},
        output_path=str(out),
    )
    r = client.post("/pipeline/start", json=body)
    assert r.status_code == 200
    assert "回绕" in (r.json().get("notice") or "")  # 提示用户已整理
    # 已生成整理后的 _seq 文件夹，连续命名
    seq_dir = tmp_path / "raw_seq"
    assert seq_dir.is_dir()
    assert sorted(p.name for p in seq_dir.iterdir()) == ["TL_0001.ARW", "TL_0002.ARW"]
