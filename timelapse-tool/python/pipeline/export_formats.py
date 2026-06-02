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
