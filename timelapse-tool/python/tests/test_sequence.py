import os

import pytest

from pipeline import sequence


def _touch(folder, names):
    for n in names:
        (folder / n).write_text("x")


def test_ordered_frames_by_time(tmp_path):
    _touch(tmp_path, ["DSC09999.ARW", "DSC00001.ARW", "DSC00002.ARW"])
    # 拍摄时间：9999 最早，0001/0002 在它之后（回绕）
    times = {
        "DSC09999.ARW": "2026-06-03 01:00:00 +0000",
        "DSC00001.ARW": "2026-06-03 01:00:05 +0000",
        "DSC00002.ARW": "2026-06-03 01:00:10 +0000",
    }
    time_of = lambda p: times[os.path.basename(p)]
    assert sequence.ordered_frames(str(tmp_path), time_of) == [
        "DSC09999.ARW", "DSC00001.ARW", "DSC00002.ARW",
    ]


def test_is_continuous_true_when_time_matches_lexical(tmp_path):
    _touch(tmp_path, ["0001.jpg", "0002.jpg", "0003.jpg"])
    times = {n: f"2026-06-03 01:00:0{i} +0000" for i, n in enumerate(["0001.jpg", "0002.jpg", "0003.jpg"])}
    assert sequence.is_continuous(str(tmp_path), lambda p: times[os.path.basename(p)]) is True


def test_is_continuous_false_on_wrap(tmp_path):
    _touch(tmp_path, ["DSC09999.ARW", "DSC00001.ARW"])
    times = {"DSC09999.ARW": "2026-06-03 01:00:00 +0000", "DSC00001.ARW": "2026-06-03 01:00:05 +0000"}
    assert sequence.is_continuous(str(tmp_path), lambda p: times[os.path.basename(p)]) is False


def test_repair_noop_when_continuous(tmp_path):
    _touch(tmp_path, ["0001.jpg", "0002.jpg"])
    times = {"0001.jpg": "t1", "0002.jpg": "t2"}
    out = sequence.repair(str(tmp_path), time_of=lambda p: times[os.path.basename(p)])
    assert out == str(tmp_path)  # 未整理，返回原文件夹


def test_repair_creates_hardlinked_continuous_sequence(tmp_path):
    src = tmp_path / "raw"; src.mkdir()
    _touch(src, ["DSC09999.ARW", "DSC00001.ARW", "DSC00002.ARW"])
    times = {
        "DSC09999.ARW": "2026-06-03 01:00:00 +0000",
        "DSC00001.ARW": "2026-06-03 01:00:05 +0000",
        "DSC00002.ARW": "2026-06-03 01:00:10 +0000",
    }
    out = sequence.repair(str(src), time_of=lambda p: times[os.path.basename(p)])
    out_p = tmp_path / "raw_seq"
    assert out == str(out_p)
    # 连续编号、按拍摄时间排序
    assert sorted(p.name for p in out_p.iterdir()) == ["TL_0001.ARW", "TL_0002.ARW", "TL_0003.ARW"]
    # 硬链接：与源同 inode（数据不复制）
    assert (out_p / "TL_0001.ARW").stat().st_ino == (src / "DSC09999.ARW").stat().st_ino
    assert (out_p / "TL_0002.ARW").stat().st_ino == (src / "DSC00001.ARW").stat().st_ino
