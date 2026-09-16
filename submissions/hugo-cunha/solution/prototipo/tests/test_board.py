import pytest

from app.board import ACTIONS, ANALYSTS, MAX_ROWS, Board


def _t(i, level="N1", decision="auto_route"):
    return {"id": f"t{i}", "text": "x", "true_category": "Access", "category": "Access", "confidence": 0.95,
            "top3": [], "neighbors": [], "risk_flags": [], "decision": decision, "level": level,
            "queue": "Access", "reason": "r", "draft": "d"}


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
               "resolved_at", "ai_wrong"}


def test_add_fills_defaults_and_returns_stored_ticket():
    b = Board(":memory:")
    t = b.add(_t(1))
    assert set(t) == TICKET_KEYS
    assert t["assigned_to"] == "" and t["status"] == "aberto" and t["ai_wrong"] == 0 and t["resolved_at"] is None
    assert t["created_at"].endswith("+00:00") and t["top3"] == [] and t["risk_flags"] == []
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
