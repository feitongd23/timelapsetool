"""热力图:网格逐格规则分 + 平滑(无分块无锯齿)PNG 渲染(spec §2 heatmap)。

概率图暖色(米→琥珀→红)、质量图紫色系;双三次插值放大,无瓦片边界。
"""
from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw

from skyfire.percent import baseline_percent
from skyfire.scoring.firecloud import FireCloudInputs, fire_cloud_score

_SCALE = 48                       # 13x9 格 → 624x432 px
_STOPS = {
    "prob": [(0xFA, 0xEE, 0xDA), (0xFA, 0xC7, 0x75), (0xEF, 0x9F, 0x27),
             (0xBA, 0x75, 0x17), (0xE2, 0x4B, 0x4A)],
    "quality": [(0xEE, 0xED, 0xFE), (0xCE, 0xCB, 0xF6), (0xAF, 0xA9, 0xEC),
                (0x7F, 0x77, 0xDD), (0x53, 0x4A, 0xB7)],
}


def score_grids(cloud: dict, confidence: str) -> dict[str, list[list[int]]]:
    """逐格 firecloud 规则分 → 概率%/质量% 两张数值网格。

    概率端经 baseline_percent(含格点云量甜区修正,cloud=该格总云近似
    high+mid+low 截断 100);channel/aod 无格点数据,置中性。缺数据格记 0。
    """
    rows, cols = len(cloud["high"]), len(cloud["high"][0])
    prob = [[0] * cols for _ in range(rows)]
    quality = [[0] * cols for _ in range(rows)]
    for r in range(rows):
        for c in range(cols):
            h, m, low = cloud["high"][r][c], cloud["mid"][r][c], cloud["low"][r][c]
            if h is None:
                continue
            p = (cloud.get("precip") or [[0] * cols] * rows)[r][c] or 0
            score = fire_cloud_score(FireCloudInputs(
                cloud_high=h, cloud_mid=m or 0, cloud_low=low or 0,
                precipitation=p, aod=None, channel=[])).score
            total = min(100.0, (h or 0) + (m or 0) + (low or 0))
            pr, qu = baseline_percent(score, confidence, None, total)
            prob[r][c], quality[r][c] = pr, qu
    return {"prob": prob, "quality": quality}


def render_heatmap_png(values: list[list[int]], kind: str,
                       marker_rc: tuple[float, float] | None) -> bytes:
    """数值网格(0-100)→ 平滑渐变 PNG bytes。

    双三次插值放大(无分块无锯齿,用户 2026-07-07 拍板)→ 色带 LUT 上色
    → 可选城市点标(双圈,marker_rc 为小数行列坐标)。
    """
    arr = np.asarray(values, dtype=np.float32)
    rows, cols = arr.shape
    small = Image.fromarray(np.clip(arr, 0, 100).astype(np.uint8), mode="L")
    big = small.resize((cols * _SCALE, rows * _SCALE), Image.BICUBIC)
    v = np.asarray(big, dtype=np.float32) / 100.0
    stops = np.asarray(_STOPS[kind], dtype=np.float32)
    pos = np.linspace(0.0, 1.0, len(stops))
    rgb = np.stack([np.interp(v, pos, stops[:, i]) for i in range(3)], axis=-1)
    img = Image.fromarray(rgb.astype(np.uint8), mode="RGB")
    if marker_rc is not None:
        d = ImageDraw.Draw(img)
        y, x = marker_rc[0] * _SCALE, marker_rc[1] * _SCALE
        d.ellipse([x - 7, y - 7, x + 7, y + 7], outline=(28, 39, 51), width=3)
        d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=(28, 39, 51))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
