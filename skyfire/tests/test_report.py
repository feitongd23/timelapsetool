from datetime import date, datetime
from zoneinfo import ZoneInfo

from skyfire.engine import PredictionResult
from skyfire.llm import LlmResult
from skyfire.report import format_outlook_report, format_pct_report, format_report

_TZ = ZoneInfo("Asia/Shanghai")


def _result(**kw):
    base = dict(city_name="北京", event="sunset_glow", day=date(2026, 7, 3),
                index=7.5, confidence="high", spread=0.9,
                per_model={"ecmwf_ifs025": 7.8, "gfs_seamless": 7.2},
                blocked_points=1, channel_factor=0.82, aod=0.3, channel_empty=False,
                peak=datetime(2026, 7, 3, 19, 46), azimuth=301.0, llm=None)
    base.update(kw)
    return PredictionResult(**base)


def test_format_report_title_has_score_and_event():
    title, body = format_report(_result())
    assert "7.5" in title
    assert "晚霞" in title and "北京" in title


def test_format_report_body_has_key_facts():
    title, body = format_report(_result())
    assert "19:46" in body          # 日落时刻
    assert "置信度" in body
    assert "301" in body            # 方位角


def test_format_report_includes_llm_when_present():
    title, body = format_report(_result(llm=LlmResult(
        llm_score=6.5, analysis="通道有低云,较 5-12 那次略差", risks="西侧低云")))
    assert "6.5" in body and "通道有低云" in body


def test_format_report_sunrise_label():
    title, _ = format_report(_result(event="sunrise_glow"))
    assert "朝霞" in title


def test_format_pct_report():
    rec = {"date": "2026-07-06", "event": "sunset_glow", "checkpoint": "c2",
           "probability_pct": 72.0, "quality_pct": 64.0, "confidence": "high",
           "rule_score": 5.0, "sat_cloud_pct": 48.0,
           "trend": "现在48% → 届时约52%", "llm_status": "done", "aod": 0.25,
           "per_model_pct": {"ecmwf_ifs025": (72, 64), "gfs_seamless": (12, 10)},
           "reasoning": "通道通", "risks": "低云带", "city_name": "北京"}
    title, body = format_pct_report(rec)
    assert "概率72%" in title and "质量64%" in title and "北京" in title
    assert "现在48% → 届时约52%" in body and "通道通" in body
    assert "北京上空云量" in body and "AOD 0.25" in body and "通透" in body
    assert "机会较大" in body and "可信度" in body
    assert "ECMWF 72/64" in body and "GFS 12/10" in body


def test_format_pct_report_pending():
    rec = {"date": "2026-07-06", "event": "sunrise_glow", "checkpoint": "c1",
           "probability_pct": 40.0, "quality_pct": 35.0, "confidence": "low",
           "rule_score": 3.5, "sat_cloud_pct": None, "trend": None,
           "llm_status": "pending", "reasoning": None, "risks": None,
           "city_name": "北京"}
    title, body = format_pct_report(rec)
    assert "朝霞" in title and "AI 解读暂缺" in body


def _outlook_rec(event, prob, qual, hour, minute):
    return {"probability_pct": prob, "quality_pct": qual, "confidence": "high",
            "llm_status": "done", "reasoning": "高云画布可期", "risks": "低云",
            "event": event, "rule_score": 5.5, "aod": 0.3,
            "peak": datetime(2026, 7, 7, hour, minute, tzinfo=_TZ),
            "city_name": "北京",
            "per_model_pct": {"ecmwf_ifs025": (35, 40), "gfs_seamless": (20, 30)},
            "per_model_raw": {
                "ecmwf_ifs025": {"cloud_high": 80, "cloud_mid": 20,
                                 "cloud_low": 10, "precipitation": 0.0},
                "gfs_seamless": {"cloud_high": 100, "cloud_mid": 40,
                                 "cloud_low": 30, "precipitation": 5.0}}}


def test_format_outlook_report_two_sections():
    sunrise = _outlook_rec("sunrise_glow", 35, 40, 4, 50)
    sunset = _outlook_rec("sunset_glow", 60, 55, 19, 46)
    title, body = format_outlook_report(sunrise, sunset)
    assert title == "明日展望 朝霞35% 晚霞60% — 北京"
    assert "明日朝霞 日出 04:50" in body and "明日晚霞 日落 19:46" in body
    assert "EC 35/40 · 高80 中20 低10 · 无雨" in body
    assert "GFS 20/30 · 高100 中40 低30 · 雨5.0mm" in body
    assert "解读: 高云画布可期" in body


def test_format_outlook_report_missing_side():
    sunset = _outlook_rec("sunset_glow", 60, 55, 19, 46)
    title, body = format_outlook_report(None, sunset)
    assert "朝霞—%" in title and "晚霞60%" in title
    assert "明日朝霞: 数据缺失,稍后自动重试" in body
    assert "明日晚霞 日落 19:46" in body


def test_format_outlook_report_raw_none_shows_dash():
    sunset = _outlook_rec("sunset_glow", 60, 55, 19, 46)
    sunset["per_model_raw"]["ecmwf_ifs025"]["cloud_high"] = None
    _, body = format_outlook_report(None, sunset)
    assert "EC 35/40 · 高— 中20 低10 · 无雨" in body
