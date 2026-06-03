import pytest

from pipeline import preview


def test_list_frames_sorted_filters_images(tmp_path):
    for n in ["b.jpg", "a.ARW", "c.tif", "notes.txt", "d.png"]:
        (tmp_path / n).write_text("x")
    frames = preview.list_frames(str(tmp_path))
    assert frames == ["a.ARW", "b.jpg", "c.tif", "d.png"]


def test_list_frames_empty_folder(tmp_path):
    assert preview.list_frames(str(tmp_path)) == []


def test_strip_indices_first_mid_last():
    assert preview.strip_names(["f0", "f1", "f2", "f3", "f4"]) == ["f0", "f2", "f4"]


def test_strip_names_few_frames():
    assert preview.strip_names(["a", "b"]) == ["a", "b"]
    assert preview.strip_names([]) == []


def test_anim_names_caps_count():
    frames = [f"f{i}" for i in range(100)]
    anim = preview.anim_names(frames, cap=24)
    assert len(anim) == 24
    assert anim[0] == "f0" and anim[-1] == "f99"


def test_anim_names_small_returns_all():
    assert preview.anim_names(["a", "b", "c"], cap=24) == ["a", "b", "c"]


def test_generate_thumbnail_invokes_qlmanage(tmp_path):
    src = tmp_path / "a.ARW"; src.write_text("raw")
    cache = tmp_path / "cache"
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        (cache / "a.ARW.png").parent.mkdir(parents=True, exist_ok=True)
        (cache / "a.ARW.png").write_text("png")
        class R: returncode = 0
        return R()

    thumb = preview.generate_thumbnail(str(src), 320, str(cache), run=fake_run)
    assert thumb.endswith("a.ARW.png")
    assert "qlmanage" in calls[0][0]


def test_generate_thumbnail_uses_cache(tmp_path):
    src = tmp_path / "a.jpg"; src.write_text("img")
    cache = tmp_path / "cache"; cache.mkdir()
    (cache / "a.jpg.png").write_text("cached")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        class R: returncode = 0
        return R()

    thumb = preview.generate_thumbnail(str(src), 320, str(cache), run=fake_run)
    assert thumb.endswith("a.jpg.png")
    assert calls == []
