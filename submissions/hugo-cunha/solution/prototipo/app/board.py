"""Board state (N1-IA / N2 / N3 columns) in SQLite from the standard library.

One table, ``tickets``, holds every ticket added by the replay. Each ticket keeps
the gate's original decision (``decision``, ``reason``) and the human's actions on
top of it: who assumed it, whether it was resolved, escalated to N3 or flagged as
"AI was wrong". The AI never resolves or closes anything here: ``resolve`` is a
human action, and there is no code path that sets ``status='resolvido'`` without it.

Ticket dict: ``id, text, true_category, category, confidence, top3, neighbors,
risk_flags, decision, level, queue, reason, draft, assigned_to, status, created_at,
resolved_at, ai_wrong``. ``top3``, ``neighbors`` and ``risk_flags`` are stored as JSON.

Statuses: ``aberto`` -> ``em_atendimento`` (assume) -> ``resolvido`` (resolve).
Analyst names for ``assume`` are a simulated round-robin (the UI labels them so).

Counters in ``snapshot()['counters']``:
- ``total``: tickets on the board (resolved included);
- ``n1``/``n2``/``n3``: tickets currently at that level, any status (so ``n1/total``
  is the share the AI routed alone and nobody overrode);
- ``resolved``: human-resolved tickets;
- ``ai_wrong``: tickets a human flagged as misrouted;
- ``ai_correct``/``ai_evaluated``: predicted class == true class over tickets that
  have a true class (the replay always does);
- ``auto_correct``/``auto_evaluated``: same, restricted to ``auto_route`` tickets;
- ``by_decision``: count per gate decision.

The store is capped at ``MAX_ROWS``: when exceeded, the oldest resolved tickets are
deleted first, then (only if still above the cap) the oldest of any status.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

__all__ = ["ACTIONS", "ANALYSTS", "Board", "DECISIONS", "MAX_ROWS", "STATUSES"]

MAX_ROWS = 2000
ANALYSTS = ["Ana", "Bruno", "Carla", "Diego"]  # SIMULATED round-robin
ACTIONS = ("assume", "resolve", "escalate", "ai_wrong")
DECISIONS = ("auto_route", "suggest", "human_triage", "human_required")
STATUSES = ("aberto", "em_atendimento", "resolvido")
LEVELS = ("N1", "N2", "N3")
QUEUE_N3 = "N3-especialista"
QUEUE_N2_TRIAGE = "N2-triagem"

_JSON_FIELDS = ("top3", "neighbors", "risk_flags")
_COLUMNS = (
    "id", "text", "true_category", "category", "confidence", "top3", "neighbors", "risk_flags",
    "decision", "level", "queue", "reason", "draft", "assigned_to", "status", "created_at",
    "resolved_at", "ai_wrong",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    seq           INTEGER PRIMARY KEY AUTOINCREMENT,
    id            TEXT NOT NULL UNIQUE,
    text          TEXT NOT NULL,
    true_category TEXT,
    category      TEXT NOT NULL,
    confidence    REAL NOT NULL,
    top3          TEXT NOT NULL,
    neighbors     TEXT NOT NULL,
    risk_flags    TEXT NOT NULL,
    decision      TEXT NOT NULL,
    level         TEXT NOT NULL,
    queue         TEXT NOT NULL,
    reason        TEXT NOT NULL,
    draft         TEXT,
    assigned_to   TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'aberto',
    created_at    TEXT NOT NULL,
    resolved_at   TEXT,
    ai_wrong      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_tickets_status_level ON tickets (status, level);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Board:
    """Thread-safe SQLite store for the demo board."""

    def __init__(self, db_path: str | Path = ":memory:", max_rows: int = MAX_ROWS):
        self.db_path = str(db_path)
        self.max_rows = int(max_rows)
        self._lock = threading.Lock()
        self._rr = 0  # round-robin cursor for `assume`
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_SCHEMA)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _to_row(t: dict) -> dict:
        row = {
            "id": str(t["id"]),
            "text": str(t.get("text") or ""),
            "true_category": t.get("true_category"),
            "category": str(t["category"]),
            "confidence": float(t.get("confidence") or 0.0),
            "top3": json.dumps(t.get("top3") or [], ensure_ascii=False),
            "neighbors": json.dumps(t.get("neighbors") or [], ensure_ascii=False),
            "risk_flags": json.dumps(list(t.get("risk_flags") or []), ensure_ascii=False),
            "decision": str(t.get("decision") or "human_triage"),
            "level": str(t.get("level") or "N2"),
            "queue": str(t.get("queue") or QUEUE_N2_TRIAGE),
            "reason": str(t.get("reason") or ""),
            "draft": t.get("draft"),
            "assigned_to": str(t.get("assigned_to") or ""),
            "status": str(t.get("status") or "aberto"),
            "created_at": str(t.get("created_at") or _now()),
            "resolved_at": t.get("resolved_at"),
            "ai_wrong": 1 if t.get("ai_wrong") else 0,
        }
        if row["status"] not in STATUSES:
            raise ValueError(f"invalid status {row['status']!r}")
        if row["level"] not in LEVELS:
            raise ValueError(f"invalid level {row['level']!r}")
        return row

    @staticmethod
    def _from_row(r: sqlite3.Row) -> dict:
        t = {k: r[k] for k in _COLUMNS}
        for k in _JSON_FIELDS:
            t[k] = json.loads(t[k]) if t[k] else []
        t["confidence"] = float(t["confidence"])
        t["ai_wrong"] = int(t["ai_wrong"])
        return t

    def _get(self, ticket_id: str) -> sqlite3.Row:
        r = self._conn.execute("SELECT * FROM tickets WHERE id = ?", (str(ticket_id),)).fetchone()
        if r is None:
            raise KeyError(ticket_id)
        return r

    def _enforce_limit(self) -> None:
        n = self._conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        excess = n - self.max_rows
        if excess <= 0:
            return
        self._conn.execute(
            "DELETE FROM tickets WHERE seq IN (SELECT seq FROM tickets WHERE status = 'resolvido' ORDER BY seq LIMIT ?)",
            (excess,),
        )
        n = self._conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        excess = n - self.max_rows
        if excess > 0:
            self._conn.execute("DELETE FROM tickets WHERE seq IN (SELECT seq FROM tickets ORDER BY seq LIMIT ?)", (excess,))

    # ------------------------------------------------------------------ API
    def add(self, ticket: dict) -> dict:
        """Insert (or re-insert, replacing) a ticket and return the stored dict."""
        row = self._to_row(ticket)
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                # A re-arriving id (replay wrapped around) is treated as a new arrival.
                self._conn.execute("DELETE FROM tickets WHERE id = ?", (row["id"],))
                self._conn.execute(f"INSERT INTO tickets ({cols}) VALUES ({marks})", tuple(row.values()))
                self._enforce_limit()
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
            return self._from_row(self._get(row["id"]))

    def get(self, ticket_id: str) -> dict:
        """Ticket by id; raises ``KeyError`` when absent."""
        with self._lock:
            return self._from_row(self._get(ticket_id))

    def action(self, ticket_id: str, action: str) -> dict:
        """Apply a human action and return the updated ticket.

        Raises ``KeyError`` for an unknown ticket and ``ValueError`` for an unknown action.
        """
        if action not in ACTIONS:
            raise ValueError(f"invalid action {action!r}; expected one of {ACTIONS}")
        with self._lock:
            r = self._get(ticket_id)
            updates: dict = {}
            if action == "assume":
                if not r["assigned_to"]:
                    updates["assigned_to"] = ANALYSTS[self._rr % len(ANALYSTS)]
                    self._rr += 1
                if r["status"] != "resolvido":
                    updates["status"] = "em_atendimento"
            elif action == "resolve":
                updates["status"] = "resolvido"
                updates["resolved_at"] = _now()
            elif action == "escalate":
                updates["level"] = "N3"
                updates["queue"] = QUEUE_N3
            elif action == "ai_wrong":
                updates["ai_wrong"] = 1
                if r["level"] == "N1":
                    updates["level"] = "N2"
                    updates["queue"] = QUEUE_N2_TRIAGE
            if updates:
                sets = ", ".join(f"{k} = ?" for k in updates)
                self._conn.execute(f"UPDATE tickets SET {sets} WHERE id = ?", (*updates.values(), str(ticket_id)))
            return self._from_row(self._get(ticket_id))

    def snapshot(self, limit_per_level: int = 200) -> dict:
        """Open tickets per level (newest first, at most ``limit_per_level`` each) plus counters."""
        with self._lock:
            c = self._conn
            columns = {}
            for level in LEVELS:
                rows = c.execute(
                    "SELECT * FROM tickets WHERE status != 'resolvido' AND level = ? ORDER BY seq DESC LIMIT ?",
                    (level, int(limit_per_level)),
                ).fetchall()
                columns[level] = [self._from_row(r) for r in rows]
            one = lambda sql, *args: int(c.execute(sql, args).fetchone()[0])  # noqa: E731
            counters = {
                "total": one("SELECT COUNT(*) FROM tickets"),
                "n1": one("SELECT COUNT(*) FROM tickets WHERE level = 'N1'"),
                "n2": one("SELECT COUNT(*) FROM tickets WHERE level = 'N2'"),
                "n3": one("SELECT COUNT(*) FROM tickets WHERE level = 'N3'"),
                "resolved": one("SELECT COUNT(*) FROM tickets WHERE status = 'resolvido'"),
                "ai_wrong": one("SELECT COUNT(*) FROM tickets WHERE ai_wrong = 1"),
                "ai_correct": one("SELECT COUNT(*) FROM tickets WHERE true_category IS NOT NULL AND true_category = category"),
                "ai_evaluated": one("SELECT COUNT(*) FROM tickets WHERE true_category IS NOT NULL"),
                "auto_correct": one(
                    "SELECT COUNT(*) FROM tickets WHERE decision = 'auto_route' AND true_category IS NOT NULL AND true_category = category"
                ),
                "auto_evaluated": one("SELECT COUNT(*) FROM tickets WHERE decision = 'auto_route' AND true_category IS NOT NULL"),
                "by_decision": {d: 0 for d in DECISIONS},
            }
            for d, n in c.execute("SELECT decision, COUNT(*) FROM tickets GROUP BY decision"):
                counters["by_decision"][d] = int(n)
            return {
                "N1": columns["N1"],
                "N2": columns["N2"],
                "N3": columns["N3"],
                "resolved": counters["resolved"],
                "counters": counters,
            }

    def reset(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM tickets")
            self._rr = 0

    def close(self) -> None:
        with self._lock:
            self._conn.close()
