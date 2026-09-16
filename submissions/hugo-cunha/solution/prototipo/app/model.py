"""Runtime wrapper around the artifacts trained by ``scripts/train.py``.

``TriageModel`` loads ``models/index.pkl`` once and answers two questions for the API:

* ``predict(text)``: class, confidence, top-3 classes and the ``k`` most similar
  training tickets (cosine over TF-IDF) for free text typed by a user. The text
  goes through ``app.normalize`` first: the training corpus is already
  pre-processed (lowercase, no punctuation) and free text is not.
* ``neighbors_by_ids(ids, sims)``: turns the neighbor ids stored in
  ``artifacts/holdout_pred.csv.gz`` into the same neighbor dicts the API returns
  for free text, so the replay shows excerpts and classes without recomputing.
  Those ids are values of ``train_ids`` (0-based rows of the original CSV), not
  positions in ``X_train``; the mapping is built once at load time.

The pickle is produced on the maintainer's machine by the project's own script and
loaded only from the project's ``models/`` directory (gitignored). Never load a
pickle from an untrusted source: it can execute arbitrary code.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
from scipy import sparse

from app.normalize import normalize

__all__ = ["EXCERPT_CHARS", "TriageModel", "excerpt"]

EXCERPT_CHARS = 160
DEFAULT_INDEX_PATH = "models/index.pkl"
REQUIRED_KEYS = frozenset(
    {"vectorizer", "clf", "X_train", "train_ids", "train_texts", "train_labels", "classes"}
)


def excerpt(text: str, limit: int = EXCERPT_CHARS) -> str:
    """First ``limit`` characters of ``text``; an ellipsis marks a cut (total length <= ``limit``)."""
    t = " ".join((text or "").split())
    if len(t) <= limit:
        return t
    return t[: limit - 1].rstrip() + "…"


class TriageModel:
    """Classifier + nearest-neighbor index loaded from ``index.pkl``."""

    def __init__(self, index: dict, path: str | None = None):
        missing = sorted(REQUIRED_KEYS - set(index))
        if missing:
            raise ValueError(f"index.pkl is missing keys: {missing}")
        self.path = path
        self.vectorizer = index["vectorizer"]
        self.clf = index["clf"]
        X = index["X_train"]
        if not sparse.isspmatrix_csr(X) or X.dtype != np.float32:
            X = sparse.csr_matrix(X, dtype=np.float32)
        self.X_train: sparse.csr_matrix = X
        self.train_ids = np.asarray(index["train_ids"], dtype=np.int64)
        self.train_texts: list[str] = [str(t) for t in index["train_texts"]]
        self.train_labels = np.asarray(index["train_labels"]).astype(str)
        self.classes: list[str] = [str(c) for c in index["classes"]]
        self.config: dict = dict(index.get("config") or {})
        self.trained_at: str | None = index.get("trained_at")

        n = self.X_train.shape[0]
        if not (n == len(self.train_ids) == len(self.train_texts) == len(self.train_labels)):
            raise ValueError("index.pkl: X_train, train_ids, train_texts and train_labels disagree in length")
        if [str(c) for c in self.clf.classes_] != self.classes:
            raise ValueError("index.pkl: classifier classes differ from the stored class list")
        # nn_ids in holdout_pred.csv.gz are CSV row ids, not matrix positions.
        self._pos_by_id: dict[int, int] = {int(i): p for p, i in enumerate(self.train_ids)}

    # ------------------------------------------------------------------ loading
    @classmethod
    def load(cls, path: str | Path = DEFAULT_INDEX_PATH) -> "TriageModel":
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"{p} not found: run `make train` first")
        return cls(joblib.load(p), str(p))

    # ------------------------------------------------------------------ properties
    @property
    def n_train(self) -> int:
        return int(self.X_train.shape[0])

    @property
    def n_features(self) -> int:
        return int(self.X_train.shape[1])

    # ------------------------------------------------------------------ inference
    def predict(self, text: str, k: int = 3) -> dict:
        """Classify free text and return its ``k`` nearest training tickets.

        Returns ``{category, confidence, top3:[{category, p}], neighbors:[{id, excerpt,
        category, similarity}]}``. ``confidence`` and ``p`` are rounded to 6 decimals
        (same rounding as the training artifacts). Text that normalizes to nothing the
        vocabulary knows yields a valid class (the classifier's prior) and no neighbors.
        """
        clean = normalize(text)
        x = self.vectorizer.transform([clean])
        proba = np.asarray(self.clf.predict_proba(x)[0], dtype=np.float64)
        order = np.argsort(-proba, kind="stable")[:3]
        top3 = [{"category": self.classes[j], "p": round(float(proba[j]), 6)} for j in order]
        neighbors = self._neighbors_for_vector(x, k) if x.nnz else []
        return {
            "category": self.classes[order[0]],
            "confidence": round(float(proba[order[0]]), 6),
            "top3": top3,
            "neighbors": neighbors,
        }

    def _neighbors_for_vector(self, x: sparse.csr_matrix, k: int) -> list[dict]:
        k = max(0, min(int(k), self.n_train))
        if k == 0:
            return []
        # TF-IDF rows are L2-normalized, so the dot product is the cosine similarity.
        sims = self.X_train @ x.toarray().ravel().astype(np.float32)
        sims = np.asarray(sims, dtype=np.float32).ravel()
        if k < sims.size:
            idx = np.argpartition(sims, sims.size - k)[-k:]
        else:
            idx = np.arange(sims.size)
        idx = idx[np.argsort(-sims[idx], kind="stable")]
        return [self._neighbor(int(pos), float(sims[pos])) for pos in idx]

    def neighbors_by_ids(self, ids, sims) -> list[dict]:
        """Neighbor dicts for precomputed ``(id, similarity)`` pairs from the hold-out CSV.

        An id absent from the index (only possible if the pickle and the CSV come from
        different training runs) keeps its id and similarity with an empty excerpt and
        ``category=None``, so the list length is preserved.
        """
        out = []
        for tid, sim in zip(ids, sims):
            pos = self._pos_by_id.get(int(tid))
            if pos is None:
                out.append({"id": int(tid), "excerpt": "", "category": None, "similarity": self._sim(sim)})
            else:
                out.append(self._neighbor(pos, float(sim)))
        return out

    def _neighbor(self, pos: int, sim: float) -> dict:
        return {
            "id": int(self.train_ids[pos]),
            "excerpt": excerpt(self.train_texts[pos]),
            "category": str(self.train_labels[pos]),
            "similarity": self._sim(sim),
        }

    @staticmethod
    def _sim(sim) -> float:
        return round(float(min(1.0, max(0.0, float(sim)))), 4)
