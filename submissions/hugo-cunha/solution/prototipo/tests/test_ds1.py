import json
import pathlib

import pytest

ART = pathlib.Path(__file__).resolve().parents[1] / "artifacts"

CONTRACT_KEYS = {
    "n_rows", "placeholder_share", "first_sentence_distinct", "resolution_unique",
    "resolution_avg_words", "example_com_share", "time_window_hours",
    "share_negative_resolution", "status_counts", "naive_table", "association_tests",
    "negative_control", "verdict",
}


@pytest.fixture(scope="module")
def m():
    p = ART / "ds1_metrics.json"
    if not p.exists():
        pytest.skip("run make train first")
    return json.loads(p.read_text(encoding="utf-8"))


def test_ds1_metrics_exist_and_are_noise(m):
    assert m["n_rows"] == 8469 and m["placeholder_share"] > 0.99
    assert 0.45 < m["share_negative_resolution"] < 0.55
    assert all(t["p_value"] > 0.05 for t in m["association_tests"] if t["variable"] != "frt_hour")
    assert m["negative_control"]["accuracy"] < 0.30


def test_ds1_contract_keys(m):
    assert CONTRACT_KEYS <= set(m)
    assert m["first_sentence_distinct"] == 16
    assert m["resolution_unique"] == 2769
    assert 26 < m["time_window_hours"] < 28
    assert sum(m["status_counts"].values()) == m["n_rows"]
    assert {r["dimension"] for r in m["naive_table"]} == {"Ticket Channel", "Ticket Priority", "Ticket Type"}
    assert {"dimension", "value", "n", "csat_mean", "naive_hours_mean"} <= set(m["naive_table"][0])
    assert sum(r["n"] for r in m["naive_table"] if r["dimension"] == "Ticket Type") == m["n_rows"]
    assert {"variable", "test", "p_value"} <= set(m["association_tests"][0])
    assert abs(m["negative_control"]["majority_share"] - 1752 / 8469) < 1e-3
    assert m["verdict"].startswith("As diferenças")


def test_ds1_figure_exists():
    p = ART / "figures" / "ds1_time_window.png"
    if not (ART / "ds1_metrics.json").exists():
        pytest.skip("run make train first")
    assert p.exists() and p.stat().st_size > 10_000
