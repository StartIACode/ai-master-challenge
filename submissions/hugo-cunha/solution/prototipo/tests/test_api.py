"""API contract (Task 7). Uses an in-memory board so the demo's board.db is untouched."""

import os
import pathlib

import pytest
from fastapi.testclient import TestClient

PROTO = pathlib.Path(__file__).resolve().parents[1]
TRIAGE_KEYS = {"category", "confidence", "top3", "neighbors", "risk_flags", "decision", "level", "queue", "reason", "draft"}
TICKET_KEYS = TRIAGE_KEYS | {"id", "text", "true_category", "assigned_to", "status", "created_at", "resolved_at", "ai_wrong"}


@pytest.fixture(scope="module")
def client():
    if not (PROTO / "models" / "index.pkl").exists():
        pytest.skip("run make train first")
    previous = os.environ.get("G4_BOARD_DB")
    os.environ["G4_BOARD_DB"] = ":memory:"
    from app.api import app

    try:
        with TestClient(app) as c:
            yield c
    finally:
        if previous is None:
            os.environ.pop("G4_BOARD_DB", None)
        else:
            os.environ["G4_BOARD_DB"] = previous


# --- the plan's tests ---


def test_health(client):
    r = client.get("/api/health"); assert r.status_code == 200 and r.json()["model_loaded"] is True


def test_triage_contract(client):
    r = client.post("/api/triage", json={"text": "quero cancelar e pedir reembolso"}); j = r.json()
    assert j["decision"] == "human_required" and j["draft"] is None and "refund" in j["risk_flags"]


def test_replay_adds_to_board(client):
    client.post("/api/reset")
    r = client.post("/api/replay/next", json={"n": 10}); assert len(r.json()["tickets"]) == 10
    s = client.get("/api/board").json(); assert s["counters"]["total"] == 10
    t = r.json()["tickets"][0]; a = client.post(f"/api/tickets/{t['id']}/action", json={"action": "resolve"})
    assert a.status_code == 200 and client.get("/api/board").json()["resolved"] == 1


def test_no_auto_route_for_suggest_classes(client):
    client.post("/api/reset"); ts = client.post("/api/replay/next", json={"n": 200}).json()["tickets"]
    for t in ts:
        if t["decision"] == "auto_route": assert t["category"] in {"Access", "Storage", "Hardware"} and not t["risk_flags"]


def test_closure_validation(client):
    r = client.post("/api/closure", json={}); assert r.json()["ok"] is False and r.json()["errors"]


# --- contract details ---


def test_health_keys(client):
    j = client.get("/api/health").json()
    assert set(j) == {"status", "model_loaded", "n_train", "n_holdout", "version", "llm_enabled"}
    assert j["status"] == "ok" and j["llm_enabled"] is False and j["version"] == "0.1.0"
    assert j["n_train"] > 30_000 and j["n_holdout"] > 9_000


def test_triage_keys_and_auto_route_with_draft(client):
    j = client.post("/api/triage", json={"text": "my mailbox is full and I cannot receive emails", "threshold": 0.5}).json()
    assert set(j) == TRIAGE_KEYS
    assert j["category"] == "Storage" and j["decision"] == "auto_route" and j["level"] == "N1" and j["draft"]
    assert len(j["top3"]) == 3 and len(j["neighbors"]) == 3 and j["risk_flags"] == []


def test_triage_threshold_changes_decision(client):
    text = "my mailbox is full and I cannot receive emails"
    low = client.post("/api/triage", json={"text": text, "threshold": 0.5}).json()
    high = client.post("/api/triage", json={"text": text, "threshold": 0.99}).json()
    assert low["category"] == high["category"]
    if high["confidence"] < 0.99:
        assert high["decision"] == "human_triage" and high["draft"] is None


def test_triage_validation(client):
    assert client.post("/api/triage", json={"text": "   "}).status_code == 422
    assert client.post("/api/triage", json={"text": "x", "threshold": 0.3}).status_code == 422
    assert client.post("/api/triage", json={"text": "x", "threshold": 1.0}).status_code == 422
    assert client.post("/api/triage", json={}).status_code == 422


def test_replay_ticket_shape_position_and_wrap_free_ids(client):
    client.post("/api/reset")
    j = client.post("/api/replay/next", json={"n": 5, "threshold": 0.8}).json()
    assert set(j) == {"tickets", "position", "total"} and j["position"] == 5 and j["total"] > 9_000
    for t in j["tickets"]:
        assert set(t) == TICKET_KEYS and t["id"].startswith("h") and t["status"] == "aberto"
        assert t["true_category"] and t["category"] and 0 <= t["confidence"] <= 1
        assert len(t["neighbors"]) == 3 and all(n["excerpt"] and n["category"] for n in t["neighbors"])
        if t["decision"] == "auto_route":
            assert t["draft"] and t["level"] == "N1" and t["confidence"] >= 0.8
        else:
            assert t["draft"] is None and t["level"] == "N2"
    again = client.post("/api/replay/next", json={"n": 5}).json()
    assert {t["id"] for t in again["tickets"]}.isdisjoint({t["id"] for t in j["tickets"]}) and again["position"] == 10


def test_replay_is_deterministic_after_reset(client):
    client.post("/api/reset"); a = [t["id"] for t in client.post("/api/replay/next", json={"n": 10}).json()["tickets"]]
    client.post("/api/reset"); b = [t["id"] for t in client.post("/api/replay/next", json={"n": 10}).json()["tickets"]]
    assert a == b
    assert client.post("/api/replay/next", json={"n": 0}).status_code == 422
    assert client.post("/api/replay/next", json={"n": 10, "threshold": 0.2}).status_code == 422


def test_replay_threshold_is_applied(client):
    client.post("/api/reset")
    strict = client.post("/api/replay/next", json={"n": 100, "threshold": 0.99}).json()["tickets"]
    for t in strict:
        if t["decision"] in ("auto_route", "suggest"):
            assert t["confidence"] >= 0.99


def test_actions_and_errors(client):
    client.post("/api/reset")
    t = client.post("/api/replay/next", json={"n": 1}).json()["tickets"][0]
    a = client.post(f"/api/tickets/{t['id']}/action", json={"action": "assume"}).json()
    assert a["assigned_to"] == "Ana" and a["status"] == "em_atendimento"
    e = client.post(f"/api/tickets/{t['id']}/action", json={"action": "escalate"}).json()
    assert e["level"] == "N3" and e["queue"] == "N3-especialista"
    assert client.get("/api/board").json()["N3"][0]["id"] == t["id"]
    assert client.post("/api/tickets/nope/action", json={"action": "resolve"}).status_code == 404
    assert client.post(f"/api/tickets/{t['id']}/action", json={"action": "close"}).status_code == 400


def test_board_and_reset(client):
    client.post("/api/reset")
    s = client.get("/api/board").json()
    assert set(s) == {"N1", "N2", "N3", "resolved", "counters"} and s["counters"]["total"] == 0
    assert set(s["counters"]) >= {"total", "n1", "n2", "n3", "resolved", "ai_wrong", "ai_correct", "ai_evaluated", "by_decision"}
    client.post("/api/replay/next", json={"n": 30})
    s = client.get("/api/board").json()
    assert s["counters"]["total"] == 30 and len(s["N1"]) + len(s["N2"]) + len(s["N3"]) == 30
    assert sum(s["counters"]["by_decision"].values()) == 30
    assert client.get("/api/board", params={"limit": 2}).json()["N2"].__len__() <= 2
    assert client.post("/api/reset").json() == {"ok": True}
    assert client.get("/api/board").json()["counters"]["total"] == 0


def test_artifact_endpoints(client):
    m = client.get("/api/metrics").json()
    assert m["accuracy"] >= 0.85 and len(m["thresholds"]) == 50
    p = client.get("/api/policy").json()
    assert len(p) == 8 and {"category", "action", "reason"} <= set(p[0])
    d = client.get("/api/ds1")
    if d.status_code == 200:
        assert d.json()["n_rows"] == 8469


def test_examples_are_three_fixed_real_tickets(client):
    j = client.get("/api/examples").json()
    assert len(j["examples"]) == 3
    assert all(set(e) == {"id", "text", "true_category"} and e["id"].startswith("h") for e in j["examples"])
    assert j == client.get("/api/examples").json()


def test_closure_valid_payload_returns_kb_entry(client):
    ok = {"category": "Access", "subcategory": "Novo acesso", "root_cause": "Conta fora do grupo",
          "resolution_steps": "Adicionado ao grupo AD apos aprovacao do gestor", "resolved_by_level": "N2",
          "time_spent_min": 12, "reusable": True, "reopened": False}
    j = client.post("/api/closure", json=ok).json()
    assert j["ok"] is True and j["errors"] == [] and j["kb_entry"]["category"] == "Access"
    assert j["kb_entry"]["persisted"] is False
    o = client.get("/api/closure/options").json()
    assert "Novo acesso" in o["subcategories"]["Access"]


def test_kb_example_contract(client):
    first = client.get("/api/examples").json()["examples"][0]
    j = client.get("/api/kb/example", params={"ticket_id": first["id"]}).json()
    assert set(j) == {"ticket", "similar", "illustrative", "note"} and j["illustrative"] is True
    assert set(j["ticket"]) == {"id", "text", "category"} and j["ticket"]["id"] == first["id"]
    assert len(j["similar"]) == 3
    for s in j["similar"]:
        assert set(s) == {"id", "excerpt", "category", "similarity", "closure"}
        assert s["closure"]["illustrative"] is True and s["closure"]["category"] == s["category"]
    assert client.get("/api/kb/example").json()["ticket"]["id"] == first["id"]  # default = first example
    assert client.get("/api/kb/example", params={"ticket_id": "h999999999"}).status_code == 404
    assert client.get("/api/kb/example", params={"ticket_id": "abc"}).status_code == 404


def test_root_and_static(client):
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert client.get("/static/does-not-exist.js").status_code == 404
