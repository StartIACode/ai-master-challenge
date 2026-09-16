"""Replay of the hold-out predictions written by ``scripts/train.py``.

``HoldoutReplay`` reads ``artifacts/holdout_pred.csv.gz`` (9,490 real tickets with
their true class, the model's prediction, confidence, top-3 and precomputed
nearest neighbors) and serves them in a seeded random order, wrapping around at
the end. Nothing is recomputed here: the replay is the ground truth the board and
the counters are measured against.

Row dict (JSON columns already parsed):
``{id:int, text:str, true_category:str, pred_category:str, confidence:float,
top3:[{category, p}], nn_ids:[int], nn_sims:[float]}``.

The file is read with the standard library (gzip + csv) on purpose: the API process
runs under ``MemoryMax=512M`` on the VPS and pandas would cost tens of MB of RSS.
"""

from __future__ import annotations

import csv
import gzip
import json
import threading
from pathlib import Path

import numpy as np

__all__ = ["COLUMNS", "HoldoutReplay"]

COLUMNS = ["id", "text", "true_category", "pred_category", "confidence", "top3_json", "nn_ids_json", "nn_sims_json"]


def _parse_row(raw: dict) -> dict:
    return {
        "id": int(raw["id"]),
        "text": raw["text"] or "",
        "true_category": raw["true_category"],
        "pred_category": raw["pred_category"],
        "confidence": float(raw["confidence"]),
        "top3": json.loads(raw["top3_json"]),
        "nn_ids": [int(v) for v in json.loads(raw["nn_ids_json"])],
        "nn_sims": [float(v) for v in json.loads(raw["nn_sims_json"])],
    }


class HoldoutReplay:
    """Seeded, wrapping iterator over the hold-out predictions."""

    def __init__(self, csv_path: str | Path, seed: int = 42):
        self.csv_path = Path(csv_path)
        self.seed = int(seed)
        self._rows: list[dict] = self._read(self.csv_path)
        self._by_id: dict[int, dict] = {r["id"]: r for r in self._rows}
        self._order = self._permutation(self.seed)
        self._position = 0
        self._lock = threading.Lock()

    @staticmethod
    def _read(path: Path) -> list[dict]:
        if not path.exists():
            raise FileNotFoundError(f"{path} not found: run `make train` first")
        with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
            if missing:
                raise ValueError(f"{path.name} is missing columns {missing}")
            return [_parse_row(raw) for raw in reader]

    def _permutation(self, seed: int) -> np.ndarray:
        return np.random.default_rng(seed).permutation(len(self._rows))

    # ------------------------------------------------------------------ state
    @property
    def total(self) -> int:
        return len(self._rows)

    @property
    def position(self) -> int:
        """Index (in the shuffled order) of the next ticket to be served."""
        return self._position

    def reset(self) -> None:
        with self._lock:
            self._position = 0

    # ------------------------------------------------------------------ access
    def next(self, n: int) -> list[dict]:
        """Return the next ``n`` rows (copies) in the seeded order, wrapping around.

        ``n`` is capped at ``total`` so one batch never repeats a ticket.
        """
        n = max(0, min(int(n), self.total))
        with self._lock:
            out = []
            for _ in range(n):
                out.append(dict(self._rows[self._order[self._position]]))
                self._position = (self._position + 1) % self.total
            return out

    def get(self, ticket_id: int) -> dict | None:
        """Row by hold-out id (0-based row of the original CSV) or ``None``."""
        row = self._by_id.get(int(ticket_id))
        return dict(row) if row is not None else None

    def sample(self, n: int, seed: int) -> list[dict]:
        """First ``n`` rows of the order produced by another ``seed``; does not touch the cursor."""
        n = max(0, min(int(n), self.total))
        order = self._permutation(int(seed))
        return [dict(self._rows[order[i]]) for i in range(n)]
