"""四模式置信账本(用户 2026-07-07 拍板):谁的常态更准,用数据说话。

从闭环案例(有实际得分)× forecast_snapshots(各模式当时的原始预报)
用**当前打分器**重算每模式单独的质量%,与实际得分×10 比误差,得出
每模式的 MAE/偏差。账本落 model_skill 表;所有在场模式样本 ≥ MIN_N
后,consensus 自动切换成按 1/(MAE+5) 加权平均(否则中位数)。

打分器改进后重跑 `skyfire modelskill` 即全量重算(快照存的是原始
预报数字,不受打分器版本影响)。
"""
from skyfire.consensus import consensus
from skyfire.models import ChannelPoint
from skyfire.scoring.firecloud import FireCloudInputs, fire_cloud_score

MIN_N = 30         # 单模式样本 ≥30 才启用加权(用户口径:一段时间后再判断;
                   # 2026-07-07 播种时 18-22 样本的排名还主要是打分器噪声)
_MAE_SOFT = 5.0    # 权重 = 1/(MAE+5):防零除,也防小样本 MAE 差距被放大


def score_snapshot(payload: dict) -> float | None:
    """一份快照(某模式对燃烧时刻的原始预报)→ 当前打分器的 0-10 分。"""
    if payload.get("cloud_high") is None:
        return None
    channel = [ChannelPoint(dist_km=p["km"], cloud_low=p.get("low"),
                            cloud_total=p.get("total"))
               for p in payload.get("channel", [])]
    r = fire_cloud_score(FireCloudInputs(
        cloud_high=payload["cloud_high"],
        cloud_mid=payload.get("cloud_mid") or 0,
        cloud_low=payload.get("cloud_low") or 0,
        precipitation=payload.get("precipitation") or 0,
        aod=payload.get("aod"), channel=channel))
    return r.score


def per_model_errors(cases: list[dict]) -> dict[str, list[float]]:
    """闭环案例 → 每模式的误差序列(预测质量% - 实际得分×10)。

    cases 元素:{"actual_score": float, "snapshots": [{"model", "payload"}]}。
    """
    errors: dict[str, list[float]] = {}
    for case in cases:
        actual = case["actual_score"] * 10
        for snap in case["snapshots"]:
            score = score_snapshot(snap["payload"])
            if score is None:
                continue
            errors.setdefault(snap["model"], []).append(score * 10 - actual)
    return errors


def skill_table(errors: dict[str, list[float]]) -> list[dict]:
    """误差序列 → 账本行(按 MAE 升序 = 最准在前)。"""
    rows = []
    for model, errs in errors.items():
        n = len(errs)
        mae = sum(abs(e) for e in errs) / n
        bias = sum(errs) / n
        rows.append({"model": model, "n": n, "mae": round(mae, 1),
                     "bias": round(bias, 1)})
    return sorted(rows, key=lambda r: r["mae"])


def weights_from_skill(rows: list[dict], models: list[str],
                       min_n: int = MIN_N) -> dict[str, float] | None:
    """账本 → consensus 权重;任一在场模式样本不足 → None(退回中位数)。"""
    by_model = {r["model"]: r for r in rows}
    if not all(m in by_model and by_model[m]["n"] >= min_n for m in models):
        return None
    return {m: 1 / (by_model[m]["mae"] + _MAE_SOFT) for m in models}


def recomputed_consensus(cases: list[dict]) -> list[dict]:
    """用当前打分器整案例重算共识分(backtest --recompute 用)。

    返回 [{"date", "event", "rule_score", "actual_score"}](跳过无有效快照的案例)。
    """
    out = []
    for case in cases:
        per_model = {}
        for snap in case["snapshots"]:
            score = score_snapshot(snap["payload"])
            if score is not None:
                per_model[snap["model"]] = score
        if not per_model:
            continue
        out.append({"date": case["date"], "event": case["event"],
                    "rule_score": consensus(per_model).index,
                    "actual_score": case["actual_score"]})
    return out
