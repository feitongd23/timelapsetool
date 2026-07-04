from skyfire import store
from skyfire.analyze import build_case_card


def _mk_case(conn):
    cid = store.upsert_case(conn, "2026-05-06", "beijing", "sunset_glow",
                            rule_score=2.0, confidence="low", source="cold_start")
    store.set_actual_score(conn, cid, 10.0)
    store.add_snapshot(conn, cid, "gfs_seamless", {
        "hour": "2026-05-06T19:00", "cloud_high": 100, "cloud_mid": 17,
        "cloud_low": 0, "rh_2m": 40, "precipitation": 0, "aod": 0.3,
        "channel": [{"km": 200, "low": 10, "total": 30}], "azimuth": 295.6})
    return cid


def test_case_notes_roundtrip():
    conn = store.connect(":memory:")
    store.init_db(conn)
    cid = _mk_case(conn)
    store.add_case_note(conn, cid, "llm", "通道通畅+高云破口 → 大烧")
    store.add_case_note(conn, cid, "user", "实际是雨后初晴,西侧裂开")
    notes = store.get_case_notes(conn, cid)
    assert [n["author"] for n in notes] == ["llm", "user"]
    assert "雨后初晴" in notes[1]["text"]


def test_case_by_key():
    conn = store.connect(":memory:")
    store.init_db(conn)
    cid = _mk_case(conn)
    case = store.case_by_key(conn, "2026-05-06", "beijing", "sunset_glow")
    assert case["id"] == cid and case["actual_score"] == 10.0
    assert store.case_by_key(conn, "1999-01-01", "beijing", "sunset_glow") is None


def test_build_case_card_contains_domain_sections():
    conn = store.connect(":memory:")
    store.init_db(conn)
    cid = _mk_case(conn)
    case = store.case_by_key(conn, "2026-05-06", "beijing", "sunset_glow")
    card = build_case_card(case, store.get_snapshots(conn, cid),
                           store.get_frames(conn, cid),
                           store.get_case_notes(conn, cid))
    assert "2026-05-06" in card and "实际 10.0" in card
    for section in ("通道", "云幕", "大气", "卫星形态", "结论"):
        assert section in card
    assert "200km low=10" in card        # 通道剖面进卡片
