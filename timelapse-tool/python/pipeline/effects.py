"""去闪/增稳配置校验 + AE 效果映射（matchName 等实机常量集中在此）。"""

STABILIZE_RESULTS = ["smooth", "none"]
STABILIZE_METHODS = ["position", "pos_scale_rot", "perspective", "subspace"]

# AE 效果 matchName —— 实机内省（Task 3）确认后回填
DEFLICKER_MATCHNAME = "ADBE Deflicker"          # 待实机确认
WARP_STABILIZER_MATCHNAME = "ADBE SubspaceStabilizer"


def validate_deflicker(deflicker):
    if not deflicker.get("enabled"):
        return
    strength = deflicker.get("strength")
    if not (isinstance(strength, int) and 0 <= strength <= 100):
        raise ValueError(f"去闪强度应在 0-100: {strength}")
    tr = deflicker.get("time_radius")
    if not (isinstance(tr, int) and 1 <= tr <= 10):
        raise ValueError(f"去闪时间半径应在 1-10: {tr}")


def validate_stabilize(stabilize):
    if not stabilize.get("enabled"):
        return
    if stabilize.get("result") not in STABILIZE_RESULTS:
        raise ValueError(f"增稳结果不支持: {stabilize.get('result')}")
    if stabilize.get("method") not in STABILIZE_METHODS:
        raise ValueError(f"增稳方法不支持: {stabilize.get('method')}")
    sm = stabilize.get("smoothness")
    if not (isinstance(sm, int) and 0 <= sm <= 100):
        raise ValueError(f"增稳平滑度应在 0-100: {sm}")
