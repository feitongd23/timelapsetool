import json

from skyfire import store


def _db(tmp_path):
    conn = store.connect(tmp_path / "test.db")
    store.init_db(conn)
    return conn


def test_upsert_case_is_idempotent(tmp_path):
    conn = _db(tmp_path)
    id1 = store.upsert_case(conn, "2026-07-03", "beijing", "sunset_glow",
                            rule_score=7.5, confidence="high", source="auto")
    id2 = store.upsert_case(conn, "2026-07-03", "beijing", "sunset_glow",
                            rule_score=8.0, confidence="medium", source="auto")
    assert id1 == id2  # 同城同日同事件不重复建案例
    row = conn.execute("SELECT rule_score, confidence FROM cases WHERE id=?", (id1,)).fetchone()
    assert row == (8.0, "medium")  # 更新为最新预测


def test_snapshot_roundtrip(tmp_path):
    conn = _db(tmp_path)
    cid = store.upsert_case(conn, "2026-07-03", "beijing", "sunset_glow",
                            rule_score=7.5, confidence="high", source="auto")
    store.add_snapshot(conn, cid, "gfs_seamless", {"cloud_high": 48})
    snaps = store.get_snapshots(conn, cid)
    assert snaps[0]["model"] == "gfs_seamless"
    assert snaps[0]["payload"]["cloud_high"] == 48


def test_actual_score_and_scored_cases(tmp_path):
    conn = _db(tmp_path)
    cid = store.upsert_case(conn, "2026-07-01", "beijing", "sunset_glow",
                            rule_score=8.0, confidence="high", source="cold_start")
    store.upsert_case(conn, "2026-07-02", "beijing", "sunset_glow",
                      rule_score=3.0, confidence="high", source="auto")  # 未打分
    store.set_actual_score(conn, cid, 9.0)
    scored = store.scored_cases(conn, "beijing")
    assert len(scored) == 1
    assert scored[0]["rule_score"] == 8.0 and scored[0]["actual_score"] == 9.0


def test_upsert_preserves_actual_score_on_reupsert(tmp_path):
    conn = _db(tmp_path)
    cid = store.upsert_case(conn, "2026-07-01", "beijing", "sunset_glow",
                            rule_score=8.0, confidence="high", source="auto")
    store.set_actual_score(conn, cid, 9.5)
    store.upsert_case(conn, "2026-07-01", "beijing", "sunset_glow",
                      rule_score=6.0, confidence="low", source="auto")
    row = conn.execute("SELECT actual_score FROM cases WHERE id=?", (cid,)).fetchone()
    assert row[0] == 9.5


def test_satellite_frames_roundtrip(tmp_path):
    conn = _db(tmp_path)
    cid = store.upsert_case(conn, "2026-07-04", "beijing", "sunset_glow",
                            rule_score=7.0, confidence="high", source="auto")
    store.add_satellite_frame(conn, cid, "2026-07-04T10:10:00+00:00", "infrared",
                              "data/frames/x.png")
    frames = store.get_frames(conn, cid)
    assert frames == [{"ts": "2026-07-04T10:10:00+00:00", "channel": "infrared",
                       "path": "data/frames/x.png"}]


def test_set_llm_score(tmp_path):
    conn = _db(tmp_path)
    cid = store.upsert_case(conn, "2026-07-04", "beijing", "sunset_glow",
                            rule_score=7.0, confidence="high", source="auto")
    store.set_llm_score(conn, cid, 6.5)
    row = conn.execute("SELECT llm_score FROM cases WHERE id=?", (cid,)).fetchone()
    assert row[0] == 6.5


def test_cases_with_snapshot_for_rag(tmp_path):
    conn = _db(tmp_path)
    cid = store.upsert_case(conn, "2026-07-01", "beijing", "sunset_glow",
                            rule_score=8.0, confidence="high", source="cold_start")
    store.set_actual_score(conn, cid, 9.0)
    store.add_snapshot(conn, cid, "gfs_seamless", {"cloud_high": 48, "cloud_mid": 10})
    rows = store.cases_with_snapshot(conn, "beijing", "sunset_glow", model="gfs_seamless")
    assert len(rows) == 1
    assert rows[0]["actual_score"] == 9.0
    assert rows[0]["payload"]["cloud_high"] == 48
    # 未打分案例不参与检索
    cid2 = store.upsert_case(conn, "2026-07-02", "beijing", "sunset_glow",
                             rule_score=3.0, confidence="high", source="auto")
    store.add_snapshot(conn, cid2, "gfs_seamless", {"cloud_high": 5})
    assert len(store.cases_with_snapshot(conn, "beijing", "sunset_glow",
                                         model="gfs_seamless")) == 1


def test_notifications_dedup(tmp_path):
    conn = _db(tmp_path)
    assert store.was_pushed(conn, "2026-07-04", "beijing", "sunset_glow") is False
    store.mark_pushed(conn, "2026-07-04", "beijing", "sunset_glow")
    assert store.was_pushed(conn, "2026-07-04", "beijing", "sunset_glow") is True
    # 不同日期/城市/天象互不影响
    assert store.was_pushed(conn, "2026-07-05", "beijing", "sunset_glow") is False
    assert store.was_pushed(conn, "2026-07-04", "shanghai", "sunset_glow") is False
    # 重复 mark 幂等(不抛异常)
    store.mark_pushed(conn, "2026-07-04", "beijing", "sunset_glow")
    assert store.was_pushed(conn, "2026-07-04", "beijing", "sunset_glow") is True
