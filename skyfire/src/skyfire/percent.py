"""免费层 → 概率%/质量% 基线(spec §3;初版简单可解释,回测迭代)。

质量% = 规则分×10,再按燃烧时刻云量修正(2026-07-07 漏报根因 #3:
此前质量与卫星实况完全脱钩,云幕就位质量分毫无反应)。

2026-07-11 对抗审计重构(F1/F6,用户"判定方式有问题"实锤):
- 甜区奖励曾是加法(+10/+15)且无门禁,叠在乘法否决链之后把被硬门槛
  压死的格子整体复活(规则分 0 也能输出 prob 24-30——今晚济南-郑州
  假色带头号根因,违反规则 consensus-multiplicative-gate)。
  改:门控乘法——仅 rule_score≥4.0(无硬门被触发)时 质量×1.10、概率×1.15;
  负向修正(<15 封顶、15-30 折减、闷盖折减)无条件保留。
- >90 封顶/折减曾看总云量,与受光带"满盖高云近西缘=最佳画布"打架
  (经典大烧配置被永久按在 20)。改:闷盖判定看遮光云 blocker(中+低),
  调用方可单独传 blocker_cloud_pct;不传时退回用 cloud(卫星路径的
  总云语义,满盖修正已由 lid 检测在上游处理)。
- 规则分 <1.0(硬门槛归零级)概率封顶 10:否决就是否决。
"""

_CONF_FACTOR = {"high": 1.0, "medium": 0.85, "low": 0.7, "degraded": 0.6}


def _clamp(v: float) -> int:
    return int(round(max(0.0, min(100.0, v))))


def baseline_percent(rule_score: float, confidence: str,
                     sat_cloud_pct: float | None,
                     projected_cloud_pct: float | None,
                     blocker_cloud_pct: float | None = None) -> tuple[int, int]:
    quality = max(0.0, min(100.0, rule_score * 10))
    cloud = projected_cloud_pct if projected_cloud_pct is not None else sat_cloud_pct
    blocker = blocker_cloud_pct if blocker_cloud_pct is not None else cloud
    gated = rule_score >= 4.0   # 正向修正门禁:硬门被触发过的分数不得复活
    if cloud is not None:
        if cloud < 15:
            # 向零收敛而非停在 20 档(2026-07-11 采纳 sunsetbot/莉景共识:
            # 无云=烧不起来=图面白色底色;旧 min(...,20) 让万里无云区留色)
            quality = min(quality, 20.0) * max(0.0, cloud) / 15.0
        elif cloud < 30:
            quality *= 0.6 + (cloud - 15) / 15 * 0.4
        elif cloud <= 70 and gated:
            quality = min(100.0, quality * 1.10)
        if blocker is not None and blocker > 90:
            quality *= 0.75
    prob = quality * _CONF_FACTOR.get(confidence, 0.6)
    if cloud is not None:
        if cloud < 15 or (blocker is not None and blocker > 90):
            prob = min(prob, 20.0)
        elif 30 <= cloud <= 70 and gated:
            prob *= 1.15
    if rule_score < 1.0:
        prob = min(prob, 10.0)
    return _clamp(prob), _clamp(quality)
