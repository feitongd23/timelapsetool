"""推送配置加载(gitignored 本地文件,含密钥)。"""
from pathlib import Path

import yaml

VALID_PROVIDERS = ("bark", "serverchan")
DEFAULT_LEAD_MINUTES = 120


def load_notify_config(path: Path) -> dict | None:
    """读取推送配置。文件不存在返回 None(视为未配置,静默跳过推送)。"""
    if not Path(path).exists():
        return None
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    provider = data.get("provider")
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"未知 provider {provider!r},可用: {', '.join(VALID_PROVIDERS)}")
    return {"provider": provider, "key": str(data.get("key", "")),
            "lead_minutes": int(data.get("lead_minutes", DEFAULT_LEAD_MINUTES))}
