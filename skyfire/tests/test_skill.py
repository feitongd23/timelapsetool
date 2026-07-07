"""四模式置信账本(skill.py):快照重打分、误差账本、共识权重。"""
from skyfire.skill import (MIN_N, per_model_errors, recomputed_consensus,
                           score_snapshot, skill_table, weights_from_skill)


def _payload(high=100, mid=0, low=9, precip=0.0, aod=0.2):
    return {"cloud_high": high, "cloud_mid": mid, "cloud_low": low,
            "precipitation": precip, "aod": aod,
            "channel": [{"km": d, "low": 5, "total": 20}
                        for d in range(100, 401, 50)]}


def test_score_snapshot_uses_current_scorer():
    assert score_snapshot(_payload()) >= 8.0       # 满天高云=好画布(新口径)
    assert score_snapshot(_payload(high=None)) is None
    assert score_snapshot(_payload(high=0, mid=0)) == 0.0


def test_per_model_errors_and_skill_table():
    cases = [
        {"date": "2026-07-07", "event": "sunset_glow", "actual_score": 7.5,
         "snapshots": [
             {"model": "ecmwf_ifs025", "payload": _payload()},          # ≈满分画布
             {"model": "gfs_seamless", "payload": _payload(high=5, mid=5)},  # 几乎没画布
         ]},
        {"date": "2026-07-06", "event": "sunset_glow", "actual_score": 8.0,
         "snapshots": [
             {"model": "ecmwf_ifs025", "payload": _payload()},
             {"model": "gfs_seamless", "payload": _payload(high=10, mid=0)},
         ]},
    ]
    errors = per_model_errors(cases)
    assert len(errors["ecmwf_ifs025"]) == 2
    rows = skill_table(errors)
    assert rows[0]["model"] == "ecmwf_ifs025"      # EC 误差更小,排第一
    assert rows[0]["mae"] < rows[1]["mae"]
    assert rows[1]["bias"] < 0                     # GFS 一直报低 → 负偏差


def test_weights_require_min_samples_per_model():
    rows = [{"model": "ecmwf_ifs025", "n": MIN_N, "mae": 10.0, "bias": 0.0},
            {"model": "gfs_seamless", "n": MIN_N - 1, "mae": 20.0, "bias": 0.0}]
    assert weights_from_skill(rows, ["ecmwf_ifs025", "gfs_seamless"]) is None
    rows[1]["n"] = MIN_N
    w = weights_from_skill(rows, ["ecmwf_ifs025", "gfs_seamless"])
    assert w["ecmwf_ifs025"] > w["gfs_seamless"]   # MAE 小 → 权重大
    # 在场模式不在账本里 → 不加权
    assert weights_from_skill(rows, ["cma_grapes_global"]) is None


def test_recomputed_consensus_shape():
    cases = [{"date": "2026-07-07", "event": "sunset_glow", "actual_score": 7.5,
              "snapshots": [{"model": "ecmwf_ifs025", "payload": _payload()}]}]
    rows = recomputed_consensus(cases)
    assert rows[0]["actual_score"] == 7.5
    assert rows[0]["rule_score"] >= 8.0
