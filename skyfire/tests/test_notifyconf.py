import pytest

from skyfire.notifyconf import load_notify_config


def test_load_valid(tmp_path):
    p = tmp_path / "notify.yaml"
    p.write_text("provider: bark\nkey: ABC123\nlead_minutes: 150\n", encoding="utf-8")
    cfg = load_notify_config(p)
    assert cfg == {"provider": "bark", "key": "ABC123", "lead_minutes": 150}


def test_load_defaults_lead_minutes(tmp_path):
    p = tmp_path / "notify.yaml"
    p.write_text("provider: serverchan\nkey: SCT9\n", encoding="utf-8")
    cfg = load_notify_config(p)
    assert cfg["lead_minutes"] == 120   # 默认日落/日出前 2 小时


def test_load_missing_file_returns_none(tmp_path):
    assert load_notify_config(tmp_path / "nope.yaml") is None


def test_load_rejects_bad_provider(tmp_path):
    p = tmp_path / "notify.yaml"
    p.write_text("provider: telegram\nkey: X\n", encoding="utf-8")
    with pytest.raises(ValueError, match="provider"):
        load_notify_config(p)
