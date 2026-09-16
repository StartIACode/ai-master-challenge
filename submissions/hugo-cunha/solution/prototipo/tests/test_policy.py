import pytest

from app.drafts import DRAFTS, draft_for
from app.policy import (
    AUTO,
    CLASSES,
    DEFAULT_THRESHOLD,
    SUGGEST,
    Decision,
    decide,
    policy_table,
    risk_flags,
)


def test_auto_route_only_safe_classes():
    for c in AUTO:
        assert decide(c, 0.95, []).decision == "auto_route"
    for c in SUGGEST:
        assert decide(c, 0.99, []).decision == "suggest"
    assert decide("Miscellaneous", 0.99, []).decision == "human_triage"


def test_low_confidence_goes_to_human():
    assert decide("Access", 0.60, []).decision == "human_triage"
    assert decide("Access", 0.60, []).level == "N2"


def test_risk_overrides_everything():
    d = decide("Access", 0.99, ["refund"])
    assert d.decision == "human_required" and d.level == "N2"


def test_risk_flags_detect_pt_and_en():
    assert "cancel" in risk_flags("quero cancelar minha assinatura")
    assert "legal" in risk_flags("my lawyer will contact procon")
    assert risk_flags("printer not working") == []


def test_threshold_is_respected():
    assert decide("Storage", 0.85, [], threshold=0.80).decision == "auto_route"
    assert decide("Storage", 0.85, [], threshold=0.90).decision == "human_triage"


def test_draft_only_for_auto_route():
    assert draft_for("Access", "auto_route")
    assert draft_for("HR Support", "suggest") is None
    assert draft_for("Access", "human_required") is None


def test_classes_are_eight():
    assert len(CLASSES) == 8 and CLASSES == sorted(CLASSES)


# --- extra coverage beyond the plan ---


def test_class_groups_partition_the_eight_classes():
    assert AUTO.isdisjoint(SUGGEST)
    assert set(CLASSES) == AUTO | SUGGEST | {"Miscellaneous"}
    assert DEFAULT_THRESHOLD == 0.90


def test_every_risk_flag_name_is_detectable():
    samples = {
        "legal": "vou acionar meu advogado e o procon",
        "cancel": "please cancel my subscription",
        "refund": "quero o estorno do valor pago",
        "harassment": "the manager keeps threatening me",
        "health": "houve uma emergência médica no andar",
        "vip": "this is the CEO's laptop",
        "social": "já postei no instagram e no twitter",
        "reopened": "ticket reaberto pela terceira vez",
    }
    for flag, text in samples.items():
        assert flag in risk_flags(text), flag
    assert set(samples) == {"legal", "cancel", "refund", "harassment", "health", "vip", "social", "reopened"}


def test_risk_flags_are_case_insensitive_and_safe_on_empty():
    assert risk_flags("REFUND NOW") == ["refund"]
    assert risk_flags("") == []
    assert risk_flags(None) == []  # type: ignore[arg-type]


def test_suggest_classes_never_auto_route_even_at_max_confidence():
    for c in SUGGEST:
        d = decide(c, 1.0, [], threshold=0.50)
        assert d.decision == "suggest" and d.level == "N2" and d.queue == c


def test_auto_route_lands_on_class_queue_at_n1():
    d = decide("Hardware", 0.93, [])
    assert d.decision == "auto_route" and d.level == "N1" and d.queue == "Hardware"
    assert "0,93" in d.reason and "0,90" in d.reason  # pt-BR decimal comma in user-facing reasons


def test_risk_wins_over_low_confidence_and_miscellaneous():
    assert decide("Miscellaneous", 0.10, ["legal"]).decision == "human_required"
    assert decide("Purchase", 0.10, ["cancel", "refund"]).queue == "N2-humano-obrigatorio"


def test_confidence_exactly_at_threshold_counts_as_covered():
    assert decide("Access", 0.90, []).decision == "auto_route"


def test_unknown_category_and_none_inputs_go_to_human():
    d = decide("Nonexistent", 0.99, [])
    assert d.decision == "human_triage" and d.level == "N2"
    assert decide("Access", 0.99, None).decision == "auto_route"  # type: ignore[arg-type]
    assert decide("Access", 0.99, [], threshold=None).decision == "auto_route"  # type: ignore[arg-type]


def test_decision_to_dict_has_contract_keys():
    d = decide("Storage", 0.95, [])
    assert isinstance(d, Decision)
    assert set(d.to_dict()) == {"decision", "level", "queue", "reason"}


def test_policy_table_covers_all_classes_in_order():
    rows = policy_table()
    assert [r["category"] for r in rows] == CLASSES
    assert all(set(r) == {"category", "action", "reason"} for r in rows)
    by_cat = {r["category"]: r["action"] for r in rows}
    assert all(by_cat[c] == "auto-roteio com rascunho" for c in AUTO)
    assert all(by_cat[c] == "sugerir fila" for c in SUGGEST)
    assert by_cat["Miscellaneous"] == "sempre humano"


def test_drafts_exist_only_for_auto_classes_and_are_short():
    assert set(DRAFTS) == set(AUTO)
    for c in AUTO:
        text = draft_for(c, "auto_route")
        assert text is not None
        lines = [ln for ln in text.strip().splitlines() if ln.strip()]
        assert 3 <= len(lines) <= 6, c
    for c in SUGGEST | {"Miscellaneous"}:
        assert draft_for(c, "auto_route") is None


@pytest.mark.parametrize("decision", ["suggest", "human_triage", "human_required", "", None])
def test_draft_is_none_for_any_non_auto_decision(decision):
    for c in AUTO:
        assert draft_for(c, decision) is None
