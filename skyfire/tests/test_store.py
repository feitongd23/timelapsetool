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


def _conn():
    c = store.connect(":memory:")
    store.init_db(c)
    return c


def test_prediction_roundtrip_and_latest():
    c = _conn()
    store.add_prediction(c, "2026-07-06", "beijing", "sunset_glow", "c1",
                         probability_pct=60, quality_pct=55, confidence="medium",
                         rule_score=4.2, sat_cloud_pct=None, trend=None,
                         llm_status="pending", reasoning=None, risks=None)
    store.add_prediction(c, "2026-07-06", "beijing", "sunset_glow", "c2",
                         probability_pct=72, quality_pct=64, confidence="high",
                         rule_score=5.0, sat_cloud_pct=48.0, trend="now=48%→burn=52%",
                         llm_status="done", reasoning="通道通", risks="低云")
    latest = store.latest_prediction(c, "2026-07-06", "beijing", "sunset_glow")
    assert latest["checkpoint"] == "c2" and latest["probability_pct"] == 72
    traj = store.predictions_for(c, "2026-07-06", "beijing", "sunset_glow")
    assert [p["checkpoint"] for p in traj] == ["c1", "c2"]


def test_checkpoint_idempotent_but_gated_repeatable():
    c = _conn()
    kw = dict(probability_pct=50, quality_pct=50, confidence="low",
              rule_score=3.0, sat_cloud_pct=None, trend=None,
              llm_status="pending", reasoning=None, risks=None)
    store.add_prediction(c, "2026-07-06", "beijing", "sunset_glow", "c1", **kw)
    assert store.has_checkpoint(c, "2026-07-06", "beijing", "sunset_glow", "c1")
    import pytest, sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        store.add_prediction(c, "2026-07-06", "beijing", "sunset_glow", "c1", **kw)
    # gated 可多次
    store.add_prediction(c, "2026-07-06", "beijing", "sunset_glow", "gated", **kw)
    store.add_prediction(c, "2026-07-06", "beijing", "sunset_glow", "gated", **kw)
    assert len(store.predictions_for(c, "2026-07-06", "beijing", "sunset_glow")) == 3


def test_write_failure_leaves_no_open_transaction():
    """写入抛 IntegrityError 后必须回滚——残留写事务会让长驻进程一直持锁。"""
    import pytest, sqlite3
    c = _conn()
    kw = dict(probability_pct=50, quality_pct=50, confidence="low",
              rule_score=3.0, sat_cloud_pct=None, trend=None,
              llm_status="pending", reasoning=None, risks=None)
    store.add_prediction(c, "2026-07-06", "beijing", "sunset_glow", "c1", **kw)
    with pytest.raises(sqlite3.IntegrityError):  # 唯一索引 idx_pred_checkpoint 冲突
        store.add_prediction(c, "2026-07-06", "beijing", "sunset_glow", "c1", **kw)
    assert not c.in_transaction
    with pytest.raises(sqlite3.IntegrityError):  # 外键指向不存在的案例
        store.add_snapshot(c, 999, "gfs_seamless", {"cloud_high": 1})
    assert not c.in_transaction
    with pytest.raises(sqlite3.IntegrityError):  # CHECK(author) 不合法
        store.add_case_note(c, 999, "robot", "x")
    assert not c.in_transaction
    with pytest.raises(sqlite3.IntegrityError):  # CHECK(event) 不合法
        store.upsert_case(c, "2026-07-06", "beijing", "typhoon",
                          rule_score=None, confidence=None, source="auto")
    assert not c.in_transaction


def test_pending_and_unnoted_queries():
    c = _conn()
    kw = dict(probability_pct=50, quality_pct=50, confidence="low",
              rule_score=3.0, sat_cloud_pct=None, trend=None,
              llm_status="pending", reasoning=None, risks=None)
    store.add_prediction(c, "2026-07-06", "beijing", "sunset_glow", "c1", **kw)
    assert len(store.pending_predictions(c)) == 1
    cid = store.upsert_case(c, "2026-07-01", "beijing", "sunset_glow",
                            rule_score=1.0, confidence="low", source="feedback")
    store.set_actual_score(c, cid, 8.0)
    assert [x["id"] for x in store.closed_cases_without_llm_note(c)] == [cid]
    store.add_case_note(c, cid, "llm", "复盘")
    assert store.closed_cases_without_llm_note(c) == []


_OLD_PREDICTIONS_SCHEMA = """
CREATE TABLE predictions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT NOT NULL, city TEXT NOT NULL, event TEXT NOT NULL,
  checkpoint TEXT NOT NULL CHECK(checkpoint IN ('c1','c2','c3','gated','manual')),
  probability_pct REAL NOT NULL, quality_pct REAL NOT NULL,
  confidence TEXT, rule_score REAL, sat_cloud_pct REAL, trend TEXT,
  llm_status TEXT NOT NULL DEFAULT 'pending'
    CHECK(llm_status IN ('done','pending','skipped')),
  reasoning TEXT, risks TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX idx_pred_checkpoint
  ON predictions(date, city, event, checkpoint)
  WHERE checkpoint IN ('c1','c2','c3');
"""


def test_predictions_migration_from_old_schema(tmp_path):
    import sqlite3
    db = tmp_path / "old.db"
    raw = sqlite3.connect(db)
    raw.executescript(_OLD_PREDICTIONS_SCHEMA)
    raw.execute(
        """INSERT INTO predictions (date, city, event, checkpoint,
             probability_pct, quality_pct, llm_status)
           VALUES ('2026-07-05','beijing','sunset_glow','c1',50,50,'done')""")
    raw.commit(); raw.close()

    conn = store.connect(db)
    store.init_db(conn)          # 触发迁移
    # 老数据保留
    rows = store.predictions_for(conn, "2026-07-05", "beijing", "sunset_glow")
    assert len(rows) == 1 and rows[0]["checkpoint"] == "c1"
    # outlook 可写入,per_model_json 落库读回
    store.add_prediction(conn, "2026-07-06", "beijing", "sunset_glow", "outlook",
                         probability_pct=60, quality_pct=55, confidence="high",
                         rule_score=5.5, sat_cloud_pct=None, trend=None,
                         llm_status="pending", reasoning=None, risks=None,
                         per_model_json='{"gfs_seamless": {"prob": 60}}')
    row = store.latest_prediction(conn, "2026-07-06", "beijing", "sunset_glow")
    assert row["checkpoint"] == "outlook"
    assert row["per_model_json"] == '{"gfs_seamless": {"prob": 60}}'
    # 幂等:重复 init_db 不报错不丢数据
    store.init_db(conn)
    assert len(store.predictions_for(conn, "2026-07-05", "beijing",
                                     "sunset_glow")) == 1


def test_outlook_unique_per_day(tmp_path):
    import sqlite3
    import pytest
    conn = store.connect(tmp_path / "t.db")
    store.init_db(conn)
    kw = dict(probability_pct=60, quality_pct=55, confidence="high",
              rule_score=5.5, sat_cloud_pct=None, trend=None,
              llm_status="pending", reasoning=None, risks=None)
    store.add_prediction(conn, "2026-07-06", "beijing", "sunset_glow", "outlook", **kw)
    with pytest.raises(sqlite3.IntegrityError):
        store.add_prediction(conn, "2026-07-06", "beijing", "sunset_glow", "outlook", **kw)


def test_migrate_predictions_noop_without_table(tmp_path):
    import sqlite3
    conn = sqlite3.connect(tmp_path / "empty.db")
    store._migrate_predictions(conn)   # 表不存在:干净 no-op 不抛错


def test_migrate_predictions_rejects_stranded_old_table(tmp_path):
    import sqlite3
    import pytest
    conn = store.connect(tmp_path / "t.db")
    store.init_db(conn)
    conn.execute("CREATE TABLE predictions_old (id INTEGER)")
    conn.commit()
    with pytest.raises(RuntimeError, match="predictions_old"):
        store._migrate_predictions(conn)


def test_recent_predictions_orders_desc_and_limits(tmp_path):
    conn = store.connect(tmp_path / "t.db")
    store.init_db(conn)
    kw = dict(probability_pct=50, quality_pct=50, confidence="high",
              rule_score=5.0, sat_cloud_pct=None, trend=None,
              llm_status="pending", reasoning=None, risks=None)
    for cp in ("c1", "c2", "c3"):
        store.add_prediction(conn, "2026-07-06", "beijing", "sunset_glow",
                             cp, **kw)
    rows = store.recent_predictions(conn, "beijing", limit=2)
    assert [r["checkpoint"] for r in rows] == ["c3", "c2"]   # 最新在前


def test_user_token_roundtrip(tmp_path):
    conn = store.connect(tmp_path / "t.db")
    store.init_db(conn)
    store.set_user_token(conn, "openid-1", "hash-a")
    store.set_user_token(conn, "openid-1", "hash-b")   # 重登覆盖
    assert store.user_by_token(conn, "hash-a") is None
    u = store.user_by_token(conn, "hash-b")
    assert u["openid"] == "openid-1"
    assert store.user_by_token(conn, "nope") is None
