# Copyright (c) 2026 杜非同. All rights reserved.
# Part of Timelapse Tool — proprietary software.
# Unauthorized copying, modification, or distribution is prohibited.

"""用 macOS `open` 启动外部软件并定位到目标文件夹。

BR/LRT 是手动阶段，工具帮用户「开门」：把对应软件打开并指向素材文件夹，
用户再手动操作。注入 run 便于测试。
"""

import subprocess

BRIDGE_APP = "Adobe Bridge 2026"
LRT_APP = "LRTimelapse 6"


def open_in_app(app, target, run=subprocess.run):
    """等价于 `open -a <app> <target>`，把 target 用指定软件打开。"""
    return run(["open", "-a", app, target])
