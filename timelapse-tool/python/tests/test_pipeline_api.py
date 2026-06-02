from fastapi.testclient import TestClient

import server

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


def test_pipeline_start_then_status_then_continue(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    preset = tmp_path / "p.xmp"; preset.write_text("x")
    lrt = tmp_path / "seq"; lrt.mkdir(); (lrt / "0001.tif").write_text("i")
    out = tmp_path / "out"; out.mkdir()
    body = dict(
        raw_folder=str(raw), camera_name="Sony A7R IV", acr_preset_path=str(preset),
        lrt_export_folder=str(lrt), stabilize=False, resolution=[3840, 2160],
        fps=24, codec="ProRes", output_path=str(out),
    )
    r = client.post("/pipeline/start", json=body)
    assert r.status_code == 200
    assert r.json()["state"] == "waiting_for_user"

    r2 = client.get("/pipeline/status")
    assert r2.json()["state"] == "waiting_for_user"

    r3 = client.post("/pipeline/continue")
    assert r3.status_code == 200
    assert r3.json()["state"] == "done"


def test_pipeline_start_bad_fps_400(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    preset = tmp_path / "p.xmp"; preset.write_text("x")
    lrt = tmp_path / "seq"; lrt.mkdir()
    out = tmp_path / "out"; out.mkdir()
    body = dict(
        raw_folder=str(raw), camera_name="Sony A7R IV", acr_preset_path=str(preset),
        lrt_export_folder=str(lrt), stabilize=False, resolution=[3840, 2160],
        fps=99, codec="ProRes", output_path=str(out),
    )
    r = client.post("/pipeline/start", json=body)
    assert r.status_code == 400


def test_add_camera_then_listed():
    r = client.post("/cameras", json={"name": "Test Cam X", "native": [6000, 4000]})
    assert r.status_code == 201
    names = [c["name"] for c in client.get("/cameras").json()["cameras"]]
    assert "Test Cam X" in names
