"""SQLite 经验库(spec 6)。satellite_frames/photos/users 由 Plan B/C 写入,表先建好。"""
import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT NOT NULL,
  city TEXT NOT NULL,
  event TEXT NOT NULL CHECK(event IN ('sunrise_glow','sunset_glow','cloud_sea')),
  rule_score REAL,
  llm_score REAL,
  actual_score REAL,
  confidence TEXT,
  source TEXT NOT NULL DEFAULT 'auto',
  created_at TEXT DEFAULT (datetime('now')),
  UNIQUE(date, city, event)
);
CREATE TABLE IF NOT EXISTS forecast_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id INTEGER NOT NULL REFERENCES cases(id),
  model TEXT NOT NULL,
  run_time TEXT DEFAULT (datetime('now')),
  payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS satellite_frames (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id INTEGER NOT NULL REFERENCES cases(id),
  ts TEXT NOT NULL,
  channel TEXT NOT NULL,
  path TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS photos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id INTEGER NOT NULL REFERENCES cases(id),
  user_id TEXT,
  score REAL,
  path TEXT,
  note TEXT
);
CREATE TABLE IF NOT EXISTS spots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  city TEXT NOT NULL,
  name TEXT NOT NULL,
  lat REAL, lon REAL, elevation_m REAL,
  UNIQUE(city, name)
);
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  openid TEXT UNIQUE,
  name TEXT
);
CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT NOT NULL,
  city TEXT NOT NULL,
  event TEXT NOT NULL,
  pushed_at TEXT DEFAULT (datetime('now')),
  UNIQUE(date, city, event)
);
CREATE TABLE IF NOT EXISTS case_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id INTEGER NOT NULL REFERENCES cases(id),
  author TEXT NOT NULL CHECK(author IN ('user','llm')),
  text TEXT NOT NULL,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_frames_dedup
  ON satellite_frames(case_id, ts, channel);
"""


def connect(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def upsert_case(conn, date: str, city: str, event: str, *,
                rule_score: float | None, confidence: str | None, source: str) -> int:
    conn.execute(
        """INSERT INTO cases (date, city, event, rule_score, confidence, source)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(date, city, event)
           DO UPDATE SET rule_score=excluded.rule_score, confidence=excluded.confidence""",
        (date, city, event, rule_score, confidence, source),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM cases WHERE date=? AND city=? AND event=?", (date, city, event)
    ).fetchone()
    return row[0]


def set_actual_score(conn, case_id: int, score: float) -> None:
    conn.execute("UPDATE cases SET actual_score=? WHERE id=?", (score, case_id))
    conn.commit()


def add_snapshot(conn, case_id: int, model: str, payload: dict) -> None:
    conn.execute(
        "INSERT INTO forecast_snapshots (case_id, model, payload) VALUES (?, ?, ?)",
        (case_id, model, json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()


def clear_snapshots(conn, case_id: int) -> None:
    """删除某案例全部历史快照(回填幂等:重跑前先清空再重写)。"""
    conn.execute("DELETE FROM forecast_snapshots WHERE case_id=?", (case_id,))
    conn.commit()


def get_snapshots(conn, case_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT model, run_time, payload FROM forecast_snapshots WHERE case_id=?", (case_id,)
    ).fetchall()
    return [{"model": m, "run_time": rt, "payload": json.loads(p)} for m, rt, p in rows]


def scored_cases(conn, city: str) -> list[dict]:
    """已闭环案例(有实际打分),回测用。"""
    rows = conn.execute(
        """SELECT date, event, rule_score, actual_score FROM cases
           WHERE city=? AND actual_score IS NOT NULL AND rule_score IS NOT NULL
           ORDER BY date""",
        (city,),
    ).fetchall()
    return [{"date": d, "event": e, "rule_score": r, "actual_score": a}
            for d, e, r, a in rows]


def add_satellite_frame(conn, case_id: int, ts: str, channel: str, path: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO satellite_frames (case_id, ts, channel, path)"
        " VALUES (?, ?, ?, ?)",
        (case_id, ts, channel, path),
    )
    conn.commit()


def get_frames(conn, case_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT ts, channel, path FROM satellite_frames WHERE case_id=? ORDER BY ts",
        (case_id,),
    ).fetchall()
    return [{"ts": t, "channel": c, "path": p} for t, c, p in rows]


def set_llm_score(conn, case_id: int, score: float) -> None:
    conn.execute("UPDATE cases SET llm_score=? WHERE id=?", (score, case_id))
    conn.commit()


def cases_with_snapshot(conn, city: str, event: str, *, model: str) -> list[dict]:
    """已闭环案例 + 指定模式的最新快照(相似案例检索用,spec 5.5)。"""
    rows = conn.execute(
        """SELECT c.id, c.date, c.actual_score, s.payload
           FROM cases c JOIN forecast_snapshots s ON s.case_id = c.id
           WHERE c.city=? AND c.event=? AND c.actual_score IS NOT NULL AND s.model=?
             AND s.id = (SELECT MAX(id) FROM forecast_snapshots
                         WHERE case_id=c.id AND model=?)
           ORDER BY c.date""",
        (city, event, model, model),
    ).fetchall()
    return [{"case_id": i, "date": d, "actual_score": a, "payload": json.loads(p)}
            for i, d, a, p in rows]


def was_pushed(conn, date: str, city: str, event: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM notifications WHERE date=? AND city=? AND event=?",
        (date, city, event),
    ).fetchone()
    return row is not None


def mark_pushed(conn, date: str, city: str, event: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO notifications (date, city, event) VALUES (?, ?, ?)",
        (date, city, event),
    )
    conn.commit()


def add_case_note(conn, case_id: int, author: str, text: str) -> None:
    conn.execute(
        "INSERT INTO case_notes (case_id, author, text) VALUES (?, ?, ?)",
        (case_id, author, text),
    )
    conn.commit()


def get_case_notes(conn, case_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT author, text, created_at FROM case_notes WHERE case_id=? ORDER BY id",
        (case_id,),
    ).fetchall()
    return [{"author": a, "text": t, "created_at": ct} for a, t, ct in rows]


def case_by_key(conn, date: str, city: str, event: str) -> dict | None:
    row = conn.execute(
        """SELECT id, date, city, event, rule_score, llm_score, actual_score,
                  confidence FROM cases WHERE date=? AND city=? AND event=?""",
        (date, city, event),
    ).fetchone()
    if row is None:
        return None
    keys = ("id", "date", "city", "event", "rule_score", "llm_score",
            "actual_score", "confidence")
    return dict(zip(keys, row))
