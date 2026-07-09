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
    assert "2026年7月3日" in body   # 预测日期(年月日,用户2026-07-07要求)


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
    assert "预测日期: 2026年7月6日" in body


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
    # 简化:只给概率/质量/等级,不再有分模型明细/解读(用户 2026-07-08)
    assert "概率 35% · 质量 40%" in body and "概率 60% · 质量 55%" in body
    assert "EC 35/40" not in body and "解读" not in body
    assert "预测日期: 2026年7月7日" in body   # 无 date 键时从 peak 回退


def test_format_outlook_report_missing_side():
    sunset = _outlook_rec("sunset_glow", 60, 55, 19, 46)
    title, body = format_outlook_report(None, sunset)
    assert "朝霞—%" in title and "晚霞60%" in title
    assert "明日朝霞: 数据缺失(后续检查点自动补上)" in body
    assert "明日晚霞 日落 19:46" in body


def _pct_rec(**kw):
    base = {"date": "2026-07-07", "event": "sunset_glow", "checkpoint": "gated",
            "probability_pct": 52.0, "quality_pct": 40.0, "confidence": "medium",
            "rule_score": 0.6, "sat_cloud_pct": 58.0, "trend": None,
            "llm_status": "done", "reasoning": "满天高云", "risks": "低云",
            "city_name": "北京"}
    base.update(kw)
    return base


def test_format_pct_report_seq_level_and_delta():
    rec = _pct_rec(seq=9, minutes_to_peak=42,
                   prev={"probability_pct": 52.0, "quality_pct": 38.0,
                         "checkpoint": "c3", "time_local": "19:05",
                         "minutes_ago": 30})
    title, body = format_pct_report(rec)
    assert "第9报" in title and "[小烧]" in title       # 质量40 → 小烧
    assert "⚡" not in title and "🔥" not in title       # Δ<15pp 非突变
    assert "日落前第9次推送" in body and "距日落约42分钟" in body
    assert "较上次19:05(30分钟前)" in body
    assert "质量38%→40%(+2)" in body
    assert "等级 小烧" in body


def test_format_pct_report_major_jump_marks_title_and_body():
    rec = _pct_rec(seq=9, minutes_to_peak=42,
                   prev={"probability_pct": 22.0, "quality_pct": 18.0,
                         "checkpoint": "gated", "time_local": "18:34",
                         "minutes_ago": 31})
    title, body = format_pct_report(rec)
    assert title.startswith("⚡突变·")                   # 概率+30pp ≥ 15
    assert "⚠️ 重大变化" in body and "概率22%→52%(+30)" in body


def test_format_pct_report_major_jump_near_peak_uses_fire_marker():
    rec = _pct_rec(seq=10, minutes_to_peak=12,
                   prev={"probability_pct": 22.0, "quality_pct": 18.0,
                         "checkpoint": "gated", "time_local": "19:05",
                         "minutes_ago": 30})
    title, _ = format_pct_report(rec)
    assert title.startswith("🔥临近突变·")               # 距日落≤20分钟的跳变


def test_format_pct_report_first_push_and_long_lead():
    rec = _pct_rec(checkpoint="c1", seq=1, minutes_to_peak=527, prev=None)
    title, body = format_pct_report(rec)
    assert "第1报" in title
    assert "日落前第1次推送 · 早间首报 · 距日落约8.8小时" in body
    assert "较上次" not in body                          # 首报无对比行


def test_format_pct_report_sunrise_wording_and_burn_levels():
    rec = _pct_rec(event="sunrise_glow", checkpoint="c3", seq=4,
                   minutes_to_peak=30, quality_pct=75.0, prev=None)
    title, body = format_pct_report(rec)
    assert "[中烧]" in title and "日出前第4次推送" in body


def test_format_pct_report_without_new_fields_degrades_to_old_layout():
    title, body = format_pct_report(_pct_rec())
    assert "第" not in title and "[小烧]" in title       # 无 seq 只标等级
    assert "次推送" not in body and "较上次" not in body


def test_format_outlook_section_includes_burn_level():
    sunset = _outlook_rec("sunset_glow", 60, 55, 19, 46)
    _, body = format_outlook_report(None, sunset)
    assert "质量 55%(小烧)" in body   # 等级随质量括注(简化后口径)


def test_format_pct_report_shows_generation_time():
    from datetime import datetime as _dt
    rec = _pct_rec(seq=9, minutes_to_peak=12,
                   generated_at=_dt(2026, 7, 7, 19, 35, tzinfo=_TZ), prev=None)
    _, body = format_pct_report(rec)
    assert "日落前第9次推送(19:35生成)" in body


def test_format_outlook_report_shows_generation_time():
    from datetime import datetime as _dt
    sunset = _outlook_rec("sunset_glow", 60, 55, 19, 46)
    sunset["generated_at"] = _dt(2026, 7, 6, 20, 4, tzinfo=_TZ)
    _, body = format_outlook_report(None, sunset)
    assert "生成时间 20:04" in body


def test_factor_sheet_flagged_items_rendered():
    """因子过堂:缺失/修正必须出现在推送正文(2026-07-10 缺失≠沉默)。"""
    from datetime import datetime
    rec = {"event": "sunset_glow", "city_name": "北京",
           "probability_pct": 12.0, "quality_pct": 10.0,
           "confidence": "low", "rule_score": 1.5,
           "llm_status": "pending",
           "factor_sheet": [
               {"name": "卫星实况", "status": "满盖修正",
                "note": "线性读数34%为暖顶假象,按92%满盖计"},
               {"name": "气溶胶", "status": "缺失", "note": "按0.85保守系数计"},
               {"name": "降水", "status": "正常", "note": "无"},
           ]}
    _, body = format_pct_report(rec)
    assert "因子过堂:" in body
    assert "卫星实况[满盖修正]" in body and "暖顶假象" in body
    assert "气溶胶[缺失]" in body
    assert "降水[正常]" not in body   # 正常项不占推送篇幅
