import pytest

from skyfire.wechatconf import load_wechat_config


def test_missing_file_returns_none(tmp_path):
    assert load_wechat_config(tmp_path / "nope.yaml") is None


def test_loads_credentials(tmp_path):
    p = tmp_path / "wechat.local.yaml"
    p.write_text("app_id: wx123\napp_secret: abc\n", encoding="utf-8")
    cfg = load_wechat_config(p)
    assert cfg == {"app_id": "wx123", "app_secret": "abc"}


def test_incomplete_raises(tmp_path):
    p = tmp_path / "wechat.local.yaml"
    p.write_text("app_id: wx123\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_wechat_config(p)
