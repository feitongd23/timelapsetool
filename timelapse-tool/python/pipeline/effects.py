"""增稳配置校验 + AE 效果映射（matchName 等实机常量集中在此）。

去闪只在 LRT 手动完成，AE 不做去闪（AE 无可用去闪效果）。
"""

STABILIZE_RESULTS = ["smooth", "none"]
STABILIZE_METHODS = ["position", "pos_scale_rot", "perspective", "subspace"]

# AE 变形稳定器 matchName 与属性 matchName —— 按已知值，待真机渲染时确认/微调
WARP_STABILIZER_MATCHNAME = "ADBE SubspaceStabilizer"
WS_PROP_RESULT = "ADBE SubspaceStabilizer-0019"      # 结果（平滑运动/无运动）实机确认
WS_PROP_SMOOTHNESS = "ADBE SubspaceStabilizer-0020"  # 平滑度 % 实机确认
WS_PROP_METHOD = "ADBE SubspaceStabilizer-0028"      # 方法 实机确认
WS_RESULT_VALUE = {"smooth": 1, "none": 2}
WS_METHOD_VALUE = {"position": 1, "pos_scale_rot": 2, "perspective": 3, "subspace": 4}


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
