"""导出格式的唯一事实来源：编码、容器、ProRes 档位、码率范围、预设、校验。"""

CODECS = {"ProRes", "H.264", "H.265"}
PRORES_PROFILES = {"Proxy", "LT", "422", "422 HQ", "4444", "4444 XQ"}
H264_QUALITIES = {"high", "medium", "low"}
H265_BIT_DEPTHS = {8, 10}
MIN_BITRATE, MAX_BITRATE = 1, 500

_CONTAINER = {"ProRes": "MOV", "H.264": "MP4", "H.265": "MP4"}

PRESETS = {
    "母版 · ProRes 422 HQ": {"codec": "ProRes", "container": "MOV", "prores_profile": "422 HQ"},
    "母版 · ProRes 4444": {"codec": "ProRes", "container": "MOV", "prores_profile": "4444"},
    "交付 · H.265 10bit": {"codec": "H.265", "container": "MP4", "bitrate_mbps": 60, "bit_depth": 10},
    "社媒 · H.264 高质量": {"codec": "H.264", "container": "MP4", "bitrate_mbps": 80, "quality": "high"},
    "社媒 · H.264 压缩": {"codec": "H.264", "container": "MP4", "bitrate_mbps": 25, "quality": "medium"},
}


def container_for(codec):
    return _CONTAINER[codec]


def expand_preset(name):
    return dict(PRESETS[name])


def validate_export(export):
    codec = export.get("codec")
    if codec not in CODECS:
        raise ValueError(f"编码不支持: {codec}")
    if export.get("container") != container_for(codec):
        raise ValueError(f"容器与编码不匹配: {codec} 应为 {container_for(codec)}")
    if codec == "ProRes":
        if export.get("prores_profile") not in PRORES_PROFILES:
            raise ValueError(f"ProRes 档位不支持: {export.get('prores_profile')}")
    else:
        bitrate = export.get("bitrate_mbps")
        if not (isinstance(bitrate, int) and MIN_BITRATE <= bitrate <= MAX_BITRATE):
            raise ValueError(f"码率不支持: {bitrate}（应在 {MIN_BITRATE}-{MAX_BITRATE} Mbps）")
        if codec == "H.264" and export.get("quality") not in H264_QUALITIES:
            raise ValueError(f"H.264 质量档不支持: {export.get('quality')}")
        if codec == "H.265" and export.get("bit_depth") not in H265_BIT_DEPTHS:
            raise ValueError(f"位深不支持: {export.get('bit_depth')}")


# ---- 社媒导出维度（唯一事实来源）----

SOCIAL_FORMATS = {"H.265", "H.264"}
# 画幅 → (横向 w:h)
ASPECT_RATIO = {
    "16:9": (16, 9),
    "9:16": (9, 16),
    "3:4": (3, 4),
    "1:1": (1, 1),
    "3:2": (3, 2),
}
# 分辨率档 → 短边像素
SOCIAL_RESOLUTIONS = {"720p": 720, "1080p": 1080, "4K": 2160}

# 格式 → 文件名后缀 / Swift 编码标识
FORMAT_TAG = {"H.265": "h265", "H.264": "h264"}
FORMAT_SWIFT = {"H.265": "hevc", "H.264": "h264"}


def _even(n):
    n = int(round(n))
    return n if n % 2 == 0 else n + 1


def social_pixels(aspect, resolution):
    """画幅+分辨率 → (宽, 高) 偶数像素。短边 = 分辨率档。"""
    a, b = ASPECT_RATIO[aspect]
    short = SOCIAL_RESOLUTIONS[resolution]
    long = short * max(a, b) / min(a, b)
    if a > b:        # 横向：高是短边
        return (_even(long), _even(short))
    if a < b:        # 竖向：宽是短边
        return (_even(short), _even(long))
    return (_even(short), _even(short))  # 方形


def _clamp(v, lo, hi):
    return max(lo, min(v, hi))


def crop_rect(src_w, src_h, aspect, anchor=(0.5, 0.5)):
    """裁出 aspect 比例的最大矩形，以 anchor（归一化中心）为中心、clamp 到母版内。

    anchor 默认 (0.5, 0.5) = 画面正中（等于原中心裁切）。
    """
    a, b = ASPECT_RATIO[aspect]
    r = a / b               # 目标横向比
    sr = src_w / src_h
    if abs(r - sr) < 1e-9:  # 与母版同比 → 全画幅不裁
        return (0, 0, _even(src_w), _even(src_h))
    if r > sr:              # 目标更宽 → 按宽定，裁上下
        cw, ch = src_w, src_w / r
    else:                   # 目标更高/窄 → 按高定，裁左右
        cw, ch = src_h * r, src_h
    cw, ch = _even(cw), _even(ch)
    ax, ay = anchor
    x = _clamp(_even(ax * src_w - cw / 2), 0, _even(src_w - cw))
    y = _clamp(_even(ay * src_h - ch / 2), 0, _even(src_h - ch))
    return (x, y, cw, ch)


# ---- 运镜（裁框随时间从起始框 ramp 到结束框）----

MOTION_TYPES = {"none", "kenburns", "pan", "sweep"}
DIRECTIONS = {
    "none": set(),
    "kenburns": {"in", "out"},
    "pan": {"left", "right", "up", "down"},
    "sweep": {"lr", "rl"},
}
# Ken Burns 起止缩放差；Pan 裁框相对中心框的缩小（留移动余量）
INTENSITY_ZOOM = {"light": 1.06, "medium": 1.12, "strong": 1.20}
INTENSITY_PAN = {"light": 0.92, "medium": 0.85, "strong": 0.78}


def _scale_box(box, factor, src_w, src_h):
    """以 box 中心缩放 factor 倍（<1 缩小），clamp 到母版。"""
    x, y, w, h = box
    cx, cy = x + w / 2, y + h / 2
    nw, nh = _even(w * factor), _even(h * factor)
    nx = _clamp(_even(cx - nw / 2), 0, _even(src_w - nw))
    ny = _clamp(_even(cy - nh / 2), 0, _even(src_h - nh))
    return (nx, ny, nw, nh)


def _box_to_aspect_frame(box, src_w, src_h, aspect):
    """归一化 box → 包含它的最小 aspect 比例框（源像素，偶数、clamp）。"""
    bx, by, bw, bh = box
    pw, ph = bw * src_w, bh * src_h
    cx, cy = (bx + bw / 2) * src_w, (by + bh / 2) * src_h
    a, b = ASPECT_RATIO[aspect]
    r = a / b
    ew = max(pw, ph * r)
    ew, eh = _even(ew), _even(ew / r)
    x = _clamp(_even(cx - ew / 2), 0, _even(src_w - ew))
    y = _clamp(_even(cy - eh / 2), 0, _even(src_h - eh))
    return (x, y, ew, eh)


def motion_frames(src_w, src_h, aspect, motion, anchor=(0.5, 0.5)):
    """返回 (start_crop, end_crop) 两个裁框，均为 aspect 比例、在母版内。

    无运镜时起=止（退化回固定裁切）。
    """
    base = crop_rect(src_w, src_h, aspect, anchor)
    mtype = (motion or {}).get("type", "none")
    if mtype == "none":
        return base, base
    if mtype == "kenburns":
        if motion.get("box"):
            end = _box_to_aspect_frame(motion["box"], src_w, src_h, aspect)
            return (base, end) if motion["direction"] == "in" else (end, base)
        z = INTENSITY_ZOOM[motion["intensity"]]
        small = _scale_box(base, 1.0 / z, src_w, src_h)
        return (base, small) if motion["direction"] == "in" else (small, base)
    if mtype == "pan":
        box = _scale_box(base, INTENSITY_PAN[motion["intensity"]], src_w, src_h)
        x, y, w, h = box
        max_x, max_y = _even(src_w - w), _even(src_h - h)
        d = motion["direction"]
        if d in ("left", "right"):           # 以镜头移动方向命名
            sx, ex = (max_x, 0) if d == "left" else (0, max_x)
            return (sx, y, w, h), (ex, y, w, h)
        sy, ey = (max_y, 0) if d == "up" else (0, max_y)
        return (x, sy, w, h), (x, ey, w, h)
    if mtype == "sweep":                      # 满高，左右扫全幅
        a, b = ASPECT_RATIO[aspect]
        bw = min(_even(src_h * a / b), _even(src_w))
        max_x = _even(src_w - bw)
        left, right = (0, 0, bw, src_h), (max_x, 0, bw, src_h)
        return (right, left) if motion["direction"] == "rl" else (left, right)
    return base, base


def validate_social(social):
    if social.get("format") not in SOCIAL_FORMATS:
        raise ValueError(f"格式不支持: {social.get('format')}")
    if social.get("aspect") not in ASPECT_RATIO:
        raise ValueError(f"画幅不支持: {social.get('aspect')}")
    if social.get("resolution") not in SOCIAL_RESOLUTIONS:
        raise ValueError(f"分辨率不支持: {social.get('resolution')}")
    motion = social.get("motion")
    if motion:
        t = motion.get("type", "none")
        if t not in MOTION_TYPES:
            raise ValueError(f"运镜类型不支持: {t}")
        if t != "none":
            if motion.get("direction") not in DIRECTIONS[t]:
                raise ValueError(f"运镜方向不支持: {motion.get('direction')}")
            if t in ("kenburns", "pan") and motion.get("intensity") not in INTENSITY_ZOOM:
                raise ValueError(f"运镜强度不支持: {motion.get('intensity')}")
