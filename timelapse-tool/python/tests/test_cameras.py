import json
from pathlib import Path

import pytest

from pipeline.cameras import CameraStore

STANDARD = {"8K": [7680, 4320], "4K": [3840, 2160], "2K": [2048, 1080], "1080p": [1920, 1080]}


@pytest.fixture
def store(tmp_path):
    cfg = tmp_path / "cameras.json"
    cfg.write_text(json.dumps({"cameras": [{"name": "Sony A7R IV", "native": [9504, 6336]}]}))
    return CameraStore(cfg)


def test_list_returns_seeded_cameras(store):
    names = [c["name"] for c in store.list()]
    assert "Sony A7R IV" in names


def test_resolution_options_includes_native_and_smaller_standards(store):
    opts = store.resolution_options("Sony A7R IV")
    assert opts[0] == {"label": "原分辨率", "size": [9504, 6336]}
    labels = [o["label"] for o in opts]
    assert "8K" in labels and "4K" in labels and "1080p" in labels


def test_resolution_options_unknown_camera_raises(store):
    with pytest.raises(KeyError):
        store.resolution_options("Nonexistent")


def test_add_camera_persists_to_disk(store, tmp_path):
    store.add("Custom Cam", [6000, 4000])
    reloaded = CameraStore(tmp_path / "cameras.json")
    assert any(c["name"] == "Custom Cam" for c in reloaded.list())


def test_add_duplicate_name_raises(store):
    with pytest.raises(ValueError):
        store.add("Sony A7R IV", [1, 1])
