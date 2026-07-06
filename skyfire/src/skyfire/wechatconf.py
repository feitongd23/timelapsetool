"""微信小程序凭证加载(gitignored 本地文件,含 AppSecret)。"""
from pathlib import Path

import yaml


def load_wechat_config(path: Path) -> dict | None:
    """读取微信凭证。文件不存在返回 None(视为未配置,login 返回 503)。"""
    if not Path(path).exists():
        return None
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    app_id, app_secret = data.get("app_id"), data.get("app_secret")
    if not app_id or not app_secret:
        raise ValueError("wechat 配置需同时含 app_id 与 app_secret")
    return {"app_id": str(app_id), "app_secret": str(app_secret)}
