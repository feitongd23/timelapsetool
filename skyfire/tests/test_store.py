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
