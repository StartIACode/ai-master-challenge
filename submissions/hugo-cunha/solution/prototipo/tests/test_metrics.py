"""Contract tests for the artifacts written by scripts/train.py.

They read the artifacts (never retrain), so they skip when `make train` has not run.
"""

import gzip
import json
import pathlib

import pytest

from app.policy import AUTO, CLASSES, policy_table

PROTO = pathlib.Path(__file__).resolve().parents[1]
ART = PROTO / "artifacts"
INDEX = PROTO / "models" / "index.pkl"

CONTRACT_KEYS = {
    "generated_at", "config", "n_total", "n_dedup_removed", "n_train", "n_holdout", "accuracy",
    "macro_f1", "ece", "per_class", "confusion", "thresholds", "per_class_at", "similarity",
}
THRESHOLD_KEYS = {
    "t", "coverage", "n_covered", "acc_covered", "n_errors_covered", "acc_rest", "useful_coverage", "useful_acc",
}
HOLDOUT_COLUMNS = ["id", "text", "true_category", "pred_category", "confidence", "top3_json", "nn_ids_json", "nn_sims_json"]
FIGURES = ["confusion.png", "coverage_accuracy.png", "reliability.png", "similarity_curve.png"]


@pytest.fixture(scope="module")
def m():
    p = ART / "metrics.json"
    if not p.exists():
        pytest.skip("run make train first")
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def holdout(m):
    import pandas as pd

    p = ART / "holdout_pred.csv.gz"
    if not p.exists():
        pytest.skip("run make train first")
    return pd.read_csv(p)


@pytest.fixture(scope="module")
def index(m):
    if not INDEX.exists():
        pytest.skip("models/index.pkl is not versioned; run make train first")
    import joblib

    return joblib.load(INDEX)


# --- the plan's tests ---


def test_accuracy_floor(m):
    assert m["accuracy"] >= 0.84 and m["macro_f1"] >= 0.84  # pt-BR corpus floors (EN gave 0.865/0.866)


def test_thresholds_monotonic(m):
    cov = [r["coverage"] for r in m["thresholds"]]
    assert all(a >= b for a, b in zip(cov, cov[1:]))
    row = next(r for r in m["thresholds"] if abs(r["t"] - 0.90) < 1e-9)
    assert row["acc_covered"] >= 0.97 and row["useful_coverage"] >= 0.24


def test_eight_classes(m):
    assert len(m["per_class"]) == 8


# --- contract and consistency ---


def test_contract_keys(m):
    assert CONTRACT_KEYS <= set(m)
    assert set(m["per_class"]) == set(CLASSES)
    assert all({"precision", "recall", "f1", "support"} <= set(v) for v in m["per_class"].values())


def test_counts_are_consistent(m):
    assert m["n_total"] == 47837
    assert m["n_total"] == m["n_dedup_removed"] + m["n_train"] + m["n_holdout"]
    assert abs(m["n_holdout"] / (m["n_train"] + m["n_holdout"]) - 0.2) < 0.001
    assert sum(v["support"] for v in m["per_class"].values()) == m["n_holdout"]
    assert m["confusion"]["labels"] == CLASSES
    matrix = m["confusion"]["matrix"]
    assert len(matrix) == 8 and all(len(r) == 8 for r in matrix)
    assert sum(map(sum, matrix)) == m["n_holdout"]
    diagonal = sum(matrix[i][i] for i in range(8))
    assert abs(diagonal / m["n_holdout"] - m["accuracy"]) < 1e-3


def test_threshold_grid_and_useful_subset(m):
    rows = m["thresholds"]
    assert [r["t"] for r in rows] == [round(0.50 + 0.01 * i, 2) for i in range(50)]
    for r in rows:
        assert THRESHOLD_KEYS <= set(r)
        assert 0 <= r["useful_coverage"] <= r["coverage"] <= 1
        assert abs(r["n_covered"] / m["n_holdout"] - r["coverage"]) < 1e-3
        if r["acc_covered"] is not None:
            assert abs(r["n_covered"] * (1 - r["acc_covered"]) - r["n_errors_covered"]) < 1.5
    # a stricter gate never lowers accuracy of the covered set by much and always covers less
    useful = [r["useful_coverage"] for r in rows]
    assert all(a >= b for a, b in zip(useful, useful[1:]))


def test_per_class_at_policy_thresholds(m):
    assert set(m["per_class_at"]) == {"0.80", "0.90", "0.95"}
    for table in m["per_class_at"].values():
        assert set(table) == set(CLASSES)
        for row in table.values():
            assert {"coverage", "acc", "n"} <= set(row)
            assert 0 <= row["coverage"] <= 1 and row["n"] >= 0
    # useful coverage at 0.90 must equal the AUTO classes' share, minus risk-flagged tickets
    auto_n = sum(m["per_class_at"]["0.90"][c]["n"] for c in AUTO)
    row90 = next(r for r in m["thresholds"] if abs(r["t"] - 0.90) < 1e-9)
    assert row90["useful_coverage"] <= auto_n / m["n_holdout"] + 1e-6


def test_similarity_block(m):
    sim = m["similarity"]
    assert 0.6 <= sim["nn_accuracy"] <= 1.0
    assert [b["min_sim"] for b in sim["bins"]] == [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99]
    cov = [b["coverage"] for b in sim["bins"]]
    assert all(a >= b for a, b in zip(cov, cov[1:]))
    assert all({"min_sim", "coverage", "nn_agreement"} <= set(b) for b in sim["bins"])


def test_ece_is_small(m):
    assert 0 <= m["ece"] <= 0.10


def test_holdout_csv_contract(m, holdout):
    assert list(holdout.columns) == HOLDOUT_COLUMNS
    assert len(holdout) == m["n_holdout"]
    assert holdout["id"].is_unique
    assert holdout["confidence"].between(0, 1).all()
    assert set(holdout["true_category"]) <= set(CLASSES) and set(holdout["pred_category"]) <= set(CLASSES)
    assert abs((holdout["true_category"] == holdout["pred_category"]).mean() - m["accuracy"]) < 1e-3
    first = holdout.iloc[0]
    top3 = json.loads(first["top3_json"])
    assert len(top3) == 3 and top3[0]["category"] == first["pred_category"]
    assert abs(top3[0]["p"] - first["confidence"]) < 1e-6
    assert all(set(t) == {"category", "p"} for t in top3)
    assert len(json.loads(first["nn_ids_json"])) == 3 and len(json.loads(first["nn_sims_json"])) == 3
    sims = json.loads(first["nn_sims_json"])
    assert sims == sorted(sims, reverse=True) and all(0 <= s <= 1 for s in sims)
    with gzip.open(ART / "holdout_pred.csv.gz", "rt", encoding="utf-8") as fh:
        assert fh.readline().rstrip("\n") == ",".join(HOLDOUT_COLUMNS)


def test_policy_json_matches_policy_table():
    p = ART / "policy.json"
    if not p.exists():
        pytest.skip("run make train first")
    assert json.loads(p.read_text(encoding="utf-8")) == policy_table()


def test_figures_exist(m):
    for name in FIGURES:
        f = ART / "figures" / name
        assert f.exists() and f.stat().st_size > 10_000, name


def test_index_pickle_contract(m, index, holdout):
    import numpy as np

    assert set(index) >= {"vectorizer", "clf", "X_train", "train_ids", "train_texts", "train_labels", "classes",
                          "config", "trained_at"}
    assert index["classes"] == CLASSES and list(index["clf"].classes_) == CLASSES
    n = m["n_train"]
    assert index["X_train"].shape[0] == n == len(index["train_ids"]) == len(index["train_texts"]) == len(index["train_labels"])
    assert index["X_train"].dtype == np.float32
    train_ids = set(int(i) for i in index["train_ids"])
    assert train_ids.isdisjoint(set(holdout["id"].astype(int)))
    nn_ids = {int(i) for row in holdout["nn_ids_json"].head(200) for i in json.loads(row)}
    assert nn_ids <= train_ids
