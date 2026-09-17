import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app.board import ACTIONS, ANALYSTS, MAX_ROWS, Board


def _t(i, level="N1", decision="auto_route"):
    return {"id": f"t{i}", "text": "x", "true_category": "Access", "category": "Access", "confidence": 0.95,
            "top3": [], "neighbors": [], "risk_flags": [], "decision": decision, "level": level,
            "queue": "Access", "reason": "r", "draft": "d"}


class FakeClock:
    """Injectable clock for ``Board(clock=...)``: frozen until ``advance`` is called."""

    def __init__(self, start=datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)

    @property
    def iso(self):
        return self.now.isoformat(timespec="milliseconds")


# --- the plan's tests ---


def test_add_and_snapshot():
    b = Board(":memory:"); b.add(_t(1)); s = b.snapshot()
    assert len(s["N1"]) == 1 and s["counters"]["total"] == 1 and s["counters"]["ai_correct"] == 1


def test_escalate_moves_to_n3():
    b = Board(":memory:"); b.add(_t(1, "N2", "suggest")); b.action("t1", "escalate")
    assert b.snapshot()["N3"][0]["id"] == "t1"


def test_ai_wrong_moves_n1_to_n2():
    b = Board(":memory:"); b.add(_t(1)); b.action("t1", "ai_wrong"); s = b.snapshot()
    assert s["N1"] == [] and s["N2"][0]["queue"] == "N2-triagem" and s["counters"]["ai_wrong"] == 1


def test_resolve_counts():
    b = Board(":memory:"); b.add(_t(1)); b.action("t1", "resolve")
    assert b.snapshot()["resolved"] == 1


# --- contract details ---


TICKET_KEYS = {"id", "text", "true_category", "category", "confidence", "top3", "neighbors", "risk_flags",
               "decision", "level", "queue", "reason", "draft", "assigned_to", "status", "created_at",
               "resolved_at", "ai_wrong", "level_entered_at", "t_n1", "t_n2", "t_n3", "finished_at"}


def test_add_fills_defaults_and_returns_stored_ticket():
    b = Board(":memory:")
    t = b.add(_t(1))
    assert set(t) == TICKET_KEYS
    assert t["assigned_to"] == "" and t["status"] == "aberto" and t["ai_wrong"] == 0 and t["resolved_at"] is None
    assert t["created_at"].endswith("+00:00") and t["top3"] == [] and t["risk_flags"] == []
    assert t["level_entered_at"] == t["created_at"] and t["finished_at"] is None
    assert (t["t_n1"], t["t_n2"], t["t_n3"]) == (0.0, 0.0, 0.0)
    assert b.get("t1") == t


def test_json_fields_roundtrip():
    b = Board(":memory:")
    t = _t(1); t["top3"] = [{"category": "Access", "p": 0.95}]; t["neighbors"] = [{"id": 3, "similarity": 0.5}]
    t["risk_flags"] = ["refund"]
    s = b.add(t)
    assert s["top3"] == t["top3"] and s["neighbors"] == t["neighbors"] and s["risk_flags"] == ["refund"]


def test_assume_round_robin_and_status():
    b = Board(":memory:")
    for i in range(6):
        b.add(_t(i))
    names = [b.action(f"t{i}", "assume")["assigned_to"] for i in range(6)]
    assert names == ANALYSTS + ANALYSTS[:2]
    assert b.get("t0")["status"] == "em_atendimento"
    # assuming again keeps the analyst
    assert b.action("t0", "assume")["assigned_to"] == "Ana"


def test_resolve_sets_timestamp_and_leaves_columns():
    b = Board(":memory:"); b.add(_t(1)); b.add(_t(2, "N2", "suggest"))
    r = b.action("t1", "resolve")
    assert r["status"] == "resolvido" and r["resolved_at"]
    s = b.snapshot()
    assert s["N1"] == [] and len(s["N2"]) == 1 and s["resolved"] == 1 and s["counters"]["total"] == 2
    assert s["counters"]["n1"] == 1  # level counts include resolved tickets


def test_escalate_from_n1_and_ai_wrong_from_n2_keep_decision():
    b = Board(":memory:"); b.add(_t(1)); b.add(_t(2, "N2", "suggest"))
    e = b.action("t1", "escalate")
    assert e["level"] == "N3" and e["queue"] == "N3-especialista" and e["decision"] == "auto_route"
    w = b.action("t2", "ai_wrong")
    assert w["level"] == "N2" and w["queue"] == "Access" and w["ai_wrong"] == 1  # only N1 moves to N2-triagem


def test_counters():
    b = Board(":memory:")
    b.add(_t(1)); b.add(_t(2, "N2", "suggest")); b.add(_t(3, "N2", "human_triage")); b.add(_t(4, "N2", "human_required"))
    wrong = _t(5); wrong["category"] = "Hardware"  # predicted Hardware, true Access
    b.add(wrong)
    b.action("t2", "escalate"); b.action("t1", "resolve"); b.action("t5", "ai_wrong")
    c = b.snapshot()["counters"]
    assert c["total"] == 5 and c["n1"] == 1 and c["n2"] == 3 and c["n3"] == 1 and c["resolved"] == 1
    assert c["ai_wrong"] == 1 and c["ai_evaluated"] == 5 and c["ai_correct"] == 4
    assert c["auto_evaluated"] == 2 and c["auto_correct"] == 1
    assert c["by_decision"] == {"auto_route": 2, "suggest": 1, "human_triage": 1, "human_required": 1}


def test_snapshot_is_newest_first_and_limited():
    b = Board(":memory:")
    for i in range(5):
        b.add(_t(i))
    s = b.snapshot(limit_per_level=3)
    assert [t["id"] for t in s["N1"]] == ["t4", "t3", "t2"] and s["counters"]["total"] == 5


def test_readd_same_id_replaces_and_becomes_newest():
    b = Board(":memory:"); b.add(_t(1)); b.add(_t(2)); b.action("t1", "resolve")
    b.add(_t(1))
    s = b.snapshot()
    assert [t["id"] for t in s["N1"]] == ["t1", "t2"] and s["resolved"] == 0 and s["counters"]["total"] == 2


def test_unknown_ticket_and_action():
    b = Board(":memory:"); b.add(_t(1))
    with pytest.raises(KeyError):
        b.action("nope", "resolve")
    with pytest.raises(ValueError):
        b.action("t1", "close")
    assert set(ACTIONS) == {"assume", "resolve", "escalate", "ai_wrong"}


def test_row_limit_drops_oldest_resolved_first():
    b = Board(":memory:", max_rows=50)
    for i in range(50):
        b.add(_t(i))
    b.action("t0", "resolve"); b.action("t7", "resolve")
    b.add(_t(50)); b.add(_t(51))
    s = b.snapshot()
    assert s["counters"]["total"] == 50 and s["resolved"] == 0
    ids = {t["id"] for t in s["N1"]}
    assert "t50" in ids and "t51" in ids and "t0" not in ids and "t7" not in ids
    b.add(_t(52))  # nothing resolved left: the oldest open one goes
    ids = {t["id"] for t in b.snapshot()["N1"]}
    assert "t1" not in ids and "t52" in ids and len(ids) == 50
    assert MAX_ROWS == 2000


def test_reset_clears_everything():
    b = Board(":memory:"); b.add(_t(1)); b.action("t1", "assume"); b.reset()
    s = b.snapshot()
    assert s["counters"]["total"] == 0 and s["N1"] == [] and s["resolved"] == 0
    b.add(_t(2))
    assert b.action("t2", "assume")["assigned_to"] == ANALYSTS[0]


def test_file_database_persists(tmp_path):
    path = tmp_path / "board.db"
    b = Board(path); b.add(_t(1)); b.action("t1", "assume"); b.close()
    b2 = Board(path)
    assert b2.get("t1")["assigned_to"] == "Ana" and b2.snapshot()["counters"]["total"] == 1
    b2.close()


# --- time per level (TMA) ---


EMPTY_LEVEL = {"avg_s": None, "n": 0}


def test_tma_n1_resolved_after_90s():
    clock = FakeClock(); b = Board(":memory:", clock=clock)
    t = b.add(_t(1))
    assert t["created_at"] == clock.iso == t["level_entered_at"]
    clock.advance(90)
    r = b.action("t1", "resolve")
    assert r["t_n1"] == 90.0 and r["t_n2"] == 0.0 and r["t_n3"] == 0.0
    assert r["finished_at"] == r["resolved_at"] == clock.iso
    tma = b.snapshot()["counters"]["tma"]
    assert set(tma) == {"N1", "N2", "N3", "open"}
    assert tma["N1"] == {"avg_s": 90.0, "n": 1} and tma["N2"] == EMPTY_LEVEL and tma["N3"] == EMPTY_LEVEL
    assert tma["open"] == {"N1": 0, "N2": 0, "N3": 0}


def test_tma_n2_escalated_then_resolved_in_n3():
    clock = FakeClock(); b = Board(":memory:", clock=clock)
    b.add(_t(1, "N2", "suggest"))
    clock.advance(30)
    e = b.action("t1", "escalate")
    assert e["level"] == "N3" and e["t_n2"] == 30.0 and e["t_n3"] == 0.0 and e["level_entered_at"] == clock.iso
    assert e["finished_at"] is None
    tma = b.snapshot()["counters"]["tma"]
    assert tma["N2"] == {"avg_s": 30.0, "n": 1} and tma["N3"] == EMPTY_LEVEL and tma["open"]["N3"] == 1
    clock.advance(120)
    r = b.action("t1", "resolve")
    assert r["t_n2"] == 30.0 and r["t_n3"] == 120.0 and r["finished_at"] == clock.iso
    tma = b.snapshot()["counters"]["tma"]
    assert tma["N1"] == EMPTY_LEVEL and tma["N2"] == {"avg_s": 30.0, "n": 1} and tma["N3"] == {"avg_s": 120.0, "n": 1}
    assert tma["open"] == {"N1": 0, "N2": 0, "N3": 0}


def test_ai_wrong_in_n1_closes_n1_and_opens_a_new_stay_in_n2():
    clock = FakeClock(); b = Board(":memory:", clock=clock)
    b.add(_t(1))
    clock.advance(10)
    w = b.action("t1", "ai_wrong")
    assert w["level"] == "N2" and w["queue"] == "N2-triagem" and w["ai_wrong"] == 1
    assert w["t_n1"] == 10.0 and w["t_n2"] == 0.0 and w["level_entered_at"] == clock.iso and w["finished_at"] is None
    tma = b.snapshot()["counters"]["tma"]
    assert tma["N1"] == {"avg_s": 10.0, "n": 1} and tma["N2"] == EMPTY_LEVEL
    assert tma["open"] == {"N1": 0, "N2": 1, "N3": 0}
    clock.advance(25)
    r = b.action("t1", "resolve")
    assert r["t_n1"] == 10.0 and r["t_n2"] == 25.0
    assert b.snapshot()["counters"]["tma"]["N2"] == {"avg_s": 25.0, "n": 1}


def test_tma_is_the_mean_over_completed_stays_only():
    clock = FakeClock(); b = Board(":memory:", clock=clock)
    b.add(_t(1)); b.add(_t(2)); b.add(_t(3))  # t3 stays open: not in the average
    clock.advance(60); b.action("t1", "resolve")
    clock.advance(60); b.action("t2", "resolve")  # 120 s
    tma = b.snapshot()["counters"]["tma"]
    assert tma["N1"] == {"avg_s": 90.0, "n": 2} and tma["open"]["N1"] == 1
    clock.advance(0.5); b.action("t3", "assume")  # assume keeps the level: the clock keeps running
    assert b.get("t3")["t_n1"] == 0.0 and b.snapshot()["counters"]["tma"]["N1"]["n"] == 2
    clock.advance(0.5)
    assert b.action("t3", "resolve")["t_n1"] == 121.0
    assert b.snapshot()["counters"]["tma"]["N1"] == {"avg_s": 100.333, "n": 3}


def test_resolved_ticket_is_frozen_and_repeated_escalate_does_not_double_count():
    clock = FakeClock(); b = Board(":memory:", clock=clock)
    b.add(_t(1, "N2", "suggest"))
    clock.advance(30); first = b.action("t1", "escalate")
    clock.advance(5); again = b.action("t1", "escalate")  # already at N3: nothing to close, no new stay
    assert again == first and again["t_n3"] == 0.0
    clock.advance(15); r1 = b.action("t1", "resolve")
    clock.advance(100); r2 = b.action("t1", "resolve")  # idempotent
    assert r2 == r1 and r2["t_n3"] == 20.0 and r2["finished_at"] == r2["resolved_at"]
    w = b.action("t1", "ai_wrong")  # the flag is recorded, the closed ticket does not move
    assert w["ai_wrong"] == 1 and w["level"] == "N3" and w["t_n3"] == 20.0 and w["level_entered_at"] == r1["level_entered_at"]
    b.add(_t(2)); clock.advance(7); b.action("t2", "resolve"); b.action("t2", "escalate")
    assert b.get("t2")["level"] == "N1" and b.get("t2")["t_n1"] == 7.0
    tma = b.snapshot()["counters"]["tma"]
    assert tma["N1"] == {"avg_s": 7.0, "n": 1} and tma["N2"] == {"avg_s": 30.0, "n": 1} and tma["N3"] == {"avg_s": 20.0, "n": 1}


def test_default_clock_is_utc_now():
    before = datetime.now(timezone.utc)
    t = Board(":memory:").add(_t(1))
    entered = datetime.fromisoformat(t["level_entered_at"])
    assert entered.tzinfo is not None and abs((entered - before).total_seconds()) < 5


def test_readd_restarts_the_level_clock():
    clock = FakeClock(); b = Board(":memory:", clock=clock)
    b.add(_t(1)); clock.advance(40); b.action("t1", "resolve"); clock.advance(3)
    t = b.add(_t(1))  # replay wrapped around: a new arrival
    assert t["level_entered_at"] == clock.iso and t["t_n1"] == 0.0 and t["finished_at"] is None
    assert b.snapshot()["counters"]["tma"]["N1"] == EMPTY_LEVEL


_OLD_SCHEMA = """
CREATE TABLE tickets (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE, text TEXT NOT NULL, true_category TEXT,
    category TEXT NOT NULL, confidence REAL NOT NULL, top3 TEXT NOT NULL, neighbors TEXT NOT NULL,
    risk_flags TEXT NOT NULL, decision TEXT NOT NULL, level TEXT NOT NULL, queue TEXT NOT NULL,
    reason TEXT NOT NULL, draft TEXT, assigned_to TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'aberto',
    created_at TEXT NOT NULL, resolved_at TEXT, ai_wrong INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX ix_tickets_status_level ON tickets (status, level);
INSERT INTO tickets (id, text, category, confidence, top3, neighbors, risk_flags, decision, level, queue, reason, created_at)
VALUES ('old1', 'x', 'Access', 0.9, '[]', '[]', '[]', 'auto_route', 'N1', 'Access', 'r', '2026-01-01T00:00:00.000+00:00');
"""

TMA_COLUMNS = {"level_entered_at", "t_n1", "t_n2", "t_n3", "finished_at"}


def _columns(path):
    conn = sqlite3.connect(path)
    try:
        return {row[1] for row in conn.execute("PRAGMA table_info(tickets)")}
    finally:
        conn.close()


def test_pre_tma_database_is_recreated(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path); conn.executescript(_OLD_SCHEMA); conn.close()
    assert not (TMA_COLUMNS & _columns(path))
    b = Board(path)  # must not raise
    assert b.snapshot()["counters"]["total"] == 0  # demo board: the old rows are gone
    t = b.add(_t(1)); assert TMA_COLUMNS <= set(t)
    b.close()
    assert TMA_COLUMNS <= _columns(path)
    b2 = Board(path)  # a board that already has the columns keeps its rows
    assert b2.snapshot()["counters"]["total"] == 1 and b2.get("t1")["level_entered_at"] == t["level_entered_at"]
    b2.close()
