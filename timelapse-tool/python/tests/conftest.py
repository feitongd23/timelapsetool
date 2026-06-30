# Copyright (c) 2026 杜非同. All rights reserved.
# Part of Timelapse Tool — proprietary software.
# Unauthorized copying, modification, or distribution is prohibited.

import pytest

from pipeline import launcher


@pytest.fixture(autouse=True)
def _no_app_launch(monkeypatch):
    """全局阻止测试真的启动外部软件（Bridge/LRTimelapse）。"""
    monkeypatch.setattr(launcher, "open_in_app", lambda app, target, **kw: None)
