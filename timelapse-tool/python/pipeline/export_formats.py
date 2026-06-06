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


def crop_rect(src_w, src_h, aspect):
    """母版中心裁出 aspect 比例的最大矩形 → (x, y, w, h) 偶数。"""
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
    x = _even((src_w - cw) / 2)
    y = _even((src_h - ch) / 2)
    return (x, y, cw, ch)


def validate_social(social):
    if social.get("format") not in SOCIAL_FORMATS:
        raise ValueError(f"格式不支持: {social.get('format')}")
    if social.get("aspect") not in ASPECT_RATIO:
        raise ValueError(f"画幅不支持: {social.get('aspect')}")
    if social.get("resolution") not in SOCIAL_RESOLUTIONS:
        raise ValueError(f"分辨率不支持: {social.get('resolution')}")
