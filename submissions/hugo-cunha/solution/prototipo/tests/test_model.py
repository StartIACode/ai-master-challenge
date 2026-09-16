"""Runtime model contract (Task 6). Skips when models/index.pkl is absent (not versioned)."""

import json
import pathlib

import pytest

from app.model import EXCERPT_CHARS, TriageModel, excerpt
from app.policy import CLASSES

PROTO = pathlib.Path(__file__).resolve().parents[1]
INDEX = PROTO / "models" / "index.pkl"
HOLDOUT = PROTO / "artifacts" / "holdout_pred.csv.gz"


@pytest.fixture(scope="module")
def model():
    if not INDEX.exists():
        pytest.skip("run make train first")
    return TriageModel.load(str(INDEX))


# --- the plan's test ---


def test_predict_shape(model):
    r = model.predict("printer not working after windows update")
    assert r["category"] in model.classes and 0 <= r["confidence"] <= 1 and len(r["neighbors"]) == 3


# --- contract details ---


def test_load_exposes_metadata(model):
    assert model.classes == CLASSES
    assert model.n_train > 30_000 and model.n_features > 100_000
    assert isinstance(model.trained_at, str) and model.config["seed"] == 42


def test_predict_keys_and_ordering(model):
    r = model.predict("please grant access to the shared finance folder for the new hire")
    assert set(r) == {"category", "confidence", "top3", "neighbors"}
    assert len(r["top3"]) == 3 and all(set(t) == {"category", "p"} for t in r["top3"])
    ps = [t["p"] for t in r["top3"]]
    assert ps == sorted(ps, reverse=True) and sum(ps) <= 1.0 + 1e-6
    assert r["top3"][0]["category"] == r["category"] and abs(r["top3"][0]["p"] - r["confidence"]) < 1e-9
    assert all(set(n) == {"id", "excerpt", "category", "similarity"} for n in r["neighbors"])
    sims = [n["similarity"] for n in r["neighbors"]]
    assert sims == sorted(sims, reverse=True) and all(0 <= s <= 1 for s in sims)
    assert all(n["category"] in CLASSES and len(n["excerpt"]) <= EXCERPT_CHARS for n in r["neighbors"])
    train_ids = {int(i) for i in model.train_ids}
    assert all(n["id"] in train_ids for n in r["neighbors"])


def test_predict_normalizes_input(model):
    a = model.predict("PRINTER, not working!!! After Windows update.")
    b = model.predict("printer not working after windows update")
    assert a["category"] == b["category"] and a["confidence"] == b["confidence"]
    assert [n["id"] for n in a["neighbors"]] == [n["id"] for n in b["neighbors"]]


def test_k_controls_neighbor_count(model):
    assert len(model.predict("laptop screen flickering", k=5)["neighbors"]) == 5
    assert model.predict("laptop screen flickering", k=0)["neighbors"] == []


def test_out_of_vocabulary_text_is_safe(model):
    r = model.predict("xyzzy qwerty plugh")
    assert r["category"] in CLASSES and 0 <= r["confidence"] <= 1 and r["neighbors"] == []
    r2 = model.predict("")
    assert r2["category"] in CLASSES and r2["neighbors"] == []


def test_neighbors_by_ids_matches_holdout_precomputation(model):
    if not HOLDOUT.exists():
        pytest.skip("run make train first")
    import gzip
    import csv

    with gzip.open(HOLDOUT, "rt", encoding="utf-8", newline="") as fh:
        row = next(csv.DictReader(fh))
    ids = json.loads(row["nn_ids_json"])
    sims = json.loads(row["nn_sims_json"])
    nbs = model.neighbors_by_ids(ids, sims)
    assert [n["id"] for n in nbs] == ids
    assert [n["similarity"] for n in nbs] == [round(s, 4) for s in sims]
    assert all(n["category"] in CLASSES and n["excerpt"] for n in nbs)
    # ids are CSV row ids, not positions: the label must come from the row with that id
    pos = {int(i): p for p, i in enumerate(model.train_ids)}
    assert nbs[0]["category"] == model.train_labels[pos[ids[0]]]


def test_neighbors_by_ids_unknown_id_keeps_length(model):
    nbs = model.neighbors_by_ids([-1, int(model.train_ids[0])], [0.5, 0.4])
    assert len(nbs) == 2
    assert nbs[0] == {"id": -1, "excerpt": "", "category": None, "similarity": 0.5}
    assert nbs[1]["category"] in CLASSES


def test_excerpt_limit():
    assert excerpt("a" * 500).endswith("…") and len(excerpt("a" * 500)) <= EXCERPT_CHARS
    assert excerpt("  short   text ") == "short text"


def test_load_missing_path_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        TriageModel.load(str(tmp_path / "nope.pkl"))
