"""回测:规则分 vs 实际打分的 Spearman 相关性(spec 9 首要验收)。"""


def _average_ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 3:
        raise ValueError("need at least 3 paired samples")
    rx, ry = _average_ranks(xs), _average_ranks(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    if vx == 0 or vy == 0:
        raise ValueError("zero variance in ranks")
    return cov / (vx * vy) ** 0.5


def pct_report(rows: list[dict]) -> dict:
    """终版预测百分数 vs 实际得分:相关性 + 命中率(spec 里程碑 4)。

    报烧 = probability_pct>=50;真烧 = actual_score>=6。
    """
    n = len(rows)
    out = {"n": n, "spearman_quality": None,
           "hit_rate": None, "precision": None, "recall": None}
    if n >= 3:
        try:
            out["spearman_quality"] = spearman(
                [r["quality_pct"] for r in rows],
                [r["actual_score"] for r in rows])
        except ValueError:
            pass
    if n:
        tp = sum(1 for r in rows if r["probability_pct"] >= 50
                 and r["actual_score"] >= 6)
        fp = sum(1 for r in rows if r["probability_pct"] >= 50
                 and r["actual_score"] < 6)
        fn = sum(1 for r in rows if r["probability_pct"] < 50
                 and r["actual_score"] >= 6)
        tn = n - tp - fp - fn
        out["hit_rate"] = (tp + tn) / n
        out["precision"] = tp / (tp + fp) if tp + fp else None
        out["recall"] = tp / (tp + fn) if tp + fn else None
    return out
