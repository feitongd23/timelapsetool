from datetime import date, datetime

from skyfire.engine import PredictionResult
from skyfire.llm import LlmResult
from skyfire.report import format_pct_report, format_report


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
           "trend": "now=48%→burn=52%", "llm_status": "done",
           "reasoning": "通道通", "risks": "低云带", "city_name": "北京"}
    title, body = format_pct_report(rec)
    assert "概率72%" in title and "质量64%" in title and "北京" in title
    assert "C2" in body and "now=48%→burn=52%" in body and "通道通" in body


def test_format_pct_report_pending():
    rec = {"date": "2026-07-06", "event": "sunrise_glow", "checkpoint": "c1",
           "probability_pct": 40.0, "quality_pct": 35.0, "confidence": "low",
           "rule_score": 3.5, "sat_cloud_pct": None, "trend": None,
           "llm_status": "pending", "reasoning": None, "risks": None,
           "city_name": "北京"}
    title, body = format_pct_report(rec)
    assert "朝霞" in title and "AI 解读待补" in body
