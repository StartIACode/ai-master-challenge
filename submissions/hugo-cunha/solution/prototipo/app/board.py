"""Board state (N1-IA / N2 / N3 columns) in SQLite from the standard library.

One table, ``tickets``, holds every ticket added by the replay. Each ticket keeps
the gate's original decision (``decision``, ``reason``) and the human's actions on
top of it: who assumed it, whether it was resolved, escalated to N3 or flagged as
"AI was wrong". The AI never resolves or closes anything here: ``resolve`` is a
human action, and there is no code path that sets ``status='resolvido'`` without it.

Ticket dict: ``id, text, true_category, category, confidence, top3, neighbors,
risk_flags, decision, level, queue, reason, draft, assigned_to, status, created_at,
resolved_at, ai_wrong, level_entered_at, t_n1, t_n2, t_n3, finished_at``. ``top3``,
``neighbors`` and ``risk_flags`` are stored as JSON.

Statuses: ``aberto`` -> ``em_atendimento`` (assume) -> ``resolvido`` (resolve).
Analyst names for ``assume`` are a simulated round-robin (the UI labels them so).

Time per level (the TMA, "tempo medio de atendimento", of each column):
- ``level_entered_at``: ISO UTC instant the ticket entered its current level
  (= ``created_at`` on ``add``); it is the clock of the stay in progress;
- ``t_n1``/``t_n2``/``t_n3``: seconds accumulated in COMPLETED stays at each level;
- ``finished_at``: ISO UTC instant a human resolved the ticket (``None`` while open).
A stay closes when the ticket leaves the level (``escalate`` -> N3, ``ai_wrong`` at
N1 -> N2) or when it is resolved; ``assume`` does not change the level, so it never
touches the clock. Levels only move forward (N1 -> N2 -> N3), so a ticket never has a
stay in progress at a level where it already accumulated time. Once resolved a ticket
is frozen: ``resolve`` again is a no-op and ``escalate``/``ai_wrong`` no longer move
it (the ``ai_wrong`` flag is still recorded). Wall-clock time comes from the
injectable ``clock`` (see ``Board``) so tests drive it without sleeping.

Counters in ``snapshot()['counters']``:
- ``total``: tickets on the board (resolved included);
- ``n1``/``n2``/``n3``: tickets currently at that level, any status (so ``n1/total``
  is the share the AI routed alone and nobody overrode);
- ``resolved``: human-resolved tickets;
- ``ai_wrong``: tickets a human flagged as misrouted;
- ``ai_correct``/``ai_evaluated``: predicted class == true class over tickets that
  have a true class (the replay always does);
- ``auto_correct``/``auto_evaluated``: same, restricted to ``auto_route`` tickets;
- ``by_decision``: count per gate decision;
- ``tma``: ``{'N1': {'avg_s', 'n'}, 'N2': {...}, 'N3': {...}, 'open': {'N1', 'N2', 'N3'}}``.
  ``avg_s`` is the mean length in seconds of the completed stays at that level
  (``None`` when ``n == 0``) and ``n`` how many stays went into it: one per ticket
  that left the level or was resolved there. ``open`` is how many unresolved tickets
  sit at each level right now; their running stay is not part of the average. A stay
  that LEFT its level in the same millisecond it entered (0 s; only reachable
  programmatically) is not counted; the final stay (resolution) is always counted.

The store is capped at ``MAX_ROWS``: when exceeded, the oldest resolved tickets are
deleted first, then (only if still above the cap) the oldest of any status.

Schema migration: this is a demo board, so there is no incremental migration. When
``__init__`` finds a ``tickets`` table without ``level_entered_at`` (a file written
before the TMA columns existed) it drops the table and recreates it empty; the replay
repopulates it in one click.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Callable
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
_TIME_COLUMN = {"N1": "t_n1", "N2": "t_n2", "N3": "t_n3"}
_MIGRATION_MARKER = "level_entered_at"  # column whose absence identifies a pre-TMA table
_COLUMNS = (
    "id", "text", "true_category", "category", "confidence", "top3", "neighbors", "risk_flags",
    "decision", "level", "queue", "reason", "draft", "assigned_to", "status", "created_at",
    "resolved_at", "ai_wrong", "level_entered_at", "t_n1", "t_n2", "t_n3", "finished_at",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    seq              INTEGER PRIMARY KEY AUTOINCREMENT,
    id               TEXT NOT NULL UNIQUE,
    text             TEXT NOT NULL,
    true_category    TEXT,
    category         TEXT NOT NULL,
    confidence       REAL NOT NULL,
    top3             TEXT NOT NULL,
    neighbors        TEXT NOT NULL,
    risk_flags       TEXT NOT NULL,
    decision         TEXT NOT NULL,
    level            TEXT NOT NULL,
    queue            TEXT NOT NULL,
    reason           TEXT NOT NULL,
    draft            TEXT,
    assigned_to      TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'aberto',
    created_at       TEXT NOT NULL,
    resolved_at      TEXT,
    ai_wrong         INTEGER NOT NULL DEFAULT 0,
    level_entered_at TEXT NOT NULL,
    t_n1             REAL NOT NULL DEFAULT 0,
    t_n2             REAL NOT NULL DEFAULT 0,
    t_n3             REAL NOT NULL DEFAULT 0,
    finished_at      TEXT
);
CREATE INDEX IF NOT EXISTS ix_tickets_status_level ON tickets (status, level);
"""

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _seconds_between(start: str, end: str) -> float:
    """Length of a stay in seconds (never negative; millisecond precision, like the timestamps)."""
    return round(max((_parse(end) - _parse(start)).total_seconds(), 0.0), 3)


class Board:
    """Thread-safe SQLite store for the demo board.

    ``clock`` is a zero-argument callable returning the current UTC ``datetime``
    (default ``datetime.now(timezone.utc)``); a naive datetime is taken as UTC. Every
    timestamp the board writes comes from it.
    """

    def __init__(self, db_path: str | Path = ":memory:", max_rows: int = MAX_ROWS, clock: Clock | None = None):
        self.db_path = str(db_path)
        self.max_rows = int(max_rows)
        self._clock: Clock = clock or _utc_now
        self._lock = threading.Lock()
        self._rr = 0  # round-robin cursor for `assume`
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._drop_pre_tma_table()
        self._conn.executescript(_SCHEMA)

    # ------------------------------------------------------------------ helpers
    def _drop_pre_tma_table(self) -> None:
        """Demo-board migration: a ``tickets`` table without the TMA columns is dropped (module docstring)."""
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(tickets)")}
        if columns and _MIGRATION_MARKER not in columns:
            self._conn.execute("DROP TABLE tickets")

    def _now(self) -> str:
        dt = self._clock()
        dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
        return dt.isoformat(timespec="milliseconds")

    @staticmethod
    def _to_row(t: dict, now: str) -> dict:
        created_at = str(t.get("created_at") or now)
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
            "created_at": created_at,
            "resolved_at": t.get("resolved_at"),
            "ai_wrong": 1 if t.get("ai_wrong") else 0,
            # An arrival (or re-arrival) starts the clock of its level from scratch.
            "level_entered_at": created_at,
            "t_n1": 0.0,
            "t_n2": 0.0,
            "t_n3": 0.0,
            "finished_at": None,
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
        for k in _TIME_COLUMN.values():
            t[k] = float(t[k])
        return t

    def _get(self, ticket_id: str) -> sqlite3.Row:
        r = self._conn.execute("SELECT * FROM tickets WHERE id = ?", (str(ticket_id),)).fetchone()
        if r is None:
            raise KeyError(ticket_id)
        return r

    @staticmethod
    def _close_stay(r: sqlite3.Row, now: str) -> dict:
        """Column update that adds the stay in progress to the accumulator of the current level."""
        col = _TIME_COLUMN[r["level"]]
        return {col: float(r[col]) + _seconds_between(r["level_entered_at"], now)}

    @classmethod
    def _move(cls, r: sqlite3.Row, now: str, level: str, queue: str) -> dict:
        """Close the stay at the current level and open one at ``level``."""
        return {**cls._close_stay(r, now), "level": level, "queue": queue, "level_entered_at": now}

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
        row = self._to_row(ticket, self._now())
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
            now = self._now()
            resolved = r["status"] == "resolvido"
            updates: dict = {}
            if action == "assume":
                if not r["assigned_to"]:
                    updates["assigned_to"] = ANALYSTS[self._rr % len(ANALYSTS)]
                    self._rr += 1
                if not resolved:
                    updates["status"] = "em_atendimento"
            elif action == "resolve":
                if not resolved:
                    updates.update(self._close_stay(r, now))
                    updates.update(status="resolvido", resolved_at=now, finished_at=now)
            elif action == "escalate":
                if not resolved and r["level"] != "N3":
                    updates.update(self._move(r, now, "N3", QUEUE_N3))
            elif action == "ai_wrong":
                updates["ai_wrong"] = 1
                if not resolved and r["level"] == "N1":
                    updates.update(self._move(r, now, "N2", QUEUE_N2_TRIAGE))
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
                "tma": {},
            }
            for d, n in c.execute("SELECT decision, COUNT(*) FROM tickets GROUP BY decision"):
                counters["by_decision"][d] = int(n)
            for level, col in _TIME_COLUMN.items():
                # A completed stay at `level`: the ticket left it (accumulated time; levels never
                # go back, so an open stay never has time there) or was resolved while at it.
                n, total = c.execute(
                    f"SELECT COUNT(*), COALESCE(SUM({col}), 0) FROM tickets "
                    f"WHERE {col} > 0 OR (level = ? AND finished_at IS NOT NULL)",
                    (level,),
                ).fetchone()
                counters["tma"][level] = {"avg_s": round(float(total) / n, 3) if n else None, "n": int(n)}
            counters["tma"]["open"] = {
                level: one("SELECT COUNT(*) FROM tickets WHERE status != 'resolvido' AND level = ?", level) for level in LEVELS
            }
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
