from app.closure import (
    LEVELS,
    MIN_STEPS_CHARS,
    REQUIRED,
    SUBCATEGORIES,
    build_kb_entry,
    closure_options,
    kb_examples,
    validate_closure,
)
from app.policy import CLASSES

OK = {"category": "Access", "subcategory": "Novo acesso", "root_cause": "Conta fora do grupo",
      "resolution_steps": "Adicionado ao grupo AD apos aprovacao do gestor", "resolved_by_level": "N2",
      "time_spent_min": 12, "reusable": True, "reopened": False}


# --- the plan's tests ---


def test_missing_required_lists_errors():
    errs = validate_closure({})
    assert len(errs) >= len(REQUIRED)


def test_valid_payload():
    assert validate_closure(OK) == []


# --- contract details ---


def test_required_and_levels():
    assert REQUIRED == ["category", "subcategory", "root_cause", "resolution_steps", "resolved_by_level",
                        "time_spent_min", "reusable", "reopened"]
    assert LEVELS == ["N1-IA", "N2", "N3"] and MIN_STEPS_CHARS == 20


def test_errors_are_pt_br_and_one_per_missing_field():
    errs = validate_closure(None)
    assert len(errs) == len(REQUIRED)
    assert all(isinstance(e, str) and e.endswith(".") for e in errs)
    assert any("Categoria" in e for e in errs) and any("reaberto" in e for e in errs)


def test_each_rule():
    def bad(**over):
        return validate_closure({**OK, **over})

    assert bad(category="Billing") == ["Categoria inválida: escolha uma das 8 classes."]
    assert bad(subcategory="Impressora") == ["Subcategoria inválida para a categoria Access."]
    assert bad(resolution_steps="curto demais") == [f"Ação de resolução precisa ter pelo menos {MIN_STEPS_CHARS} caracteres."]
    assert bad(resolved_by_level="N4") == ["Nível que resolveu inválido: use N1-IA, N2 ou N3."]
    assert bad(time_spent_min=0) == ["Tempo gasto (min) deve ser um número maior que zero."]
    assert bad(time_spent_min="abc") == ["Tempo gasto (min) deve ser um número maior que zero."]
    assert bad(reusable="talvez") == ["Campo 'reutilizável' inválido: use sim ou não."]
    assert bad(reopened=None) == ["Informe se o ticket foi reaberto (sim/não)."]
    assert bad(satisfaction=7) == ["Satisfação deve ser um inteiro de 1 a 5."]
    assert bad(satisfaction=4) == []


def test_accepts_form_style_values():
    form = {**OK, "time_spent_min": "12,5", "reusable": "sim", "reopened": "não", "satisfaction": "5"}
    assert validate_closure(form) == []
    e = build_kb_entry(form)
    assert e["time_spent_min"] == 12.5 and e["reusable"] is True and e["reopened"] is False and e["satisfaction"] == 5


def test_subcategory_check_needs_valid_category():
    errs = validate_closure({**OK, "category": "Nope", "subcategory": "whatever"})
    assert errs == ["Categoria inválida: escolha uma das 8 classes."]


def test_subcategories_three_to_five_per_class():
    assert set(SUBCATEGORIES) == set(CLASSES)
    for c, subs in SUBCATEGORIES.items():
        assert 3 <= len(subs) <= 5, c
        assert len(set(subs)) == len(subs) and all(isinstance(s, str) and s for s in subs)


def test_kb_examples_are_illustrative_and_valid():
    for c in CLASSES:
        kb = kb_examples(c)
        assert kb["category"] == c and kb["illustrative"] is True and "ilustrativo" in kb["note"]
        assert len(kb["examples"]) >= 2
        for e in kb["examples"]:
            assert e["illustrative"] is True and e["category"] == c
            assert validate_closure(e) == [], (c, validate_closure(e))
            assert {"root_cause", "resolution_steps", "customer_reply", "reusable"} <= set(e)
            assert (e["customer_reply"] is not None) == bool(e["reusable"])


def test_kb_examples_unknown_category():
    import pytest

    with pytest.raises(KeyError):
        kb_examples("Billing")


def test_build_kb_entry_is_not_persisted():
    e = build_kb_entry({**OK, "tags": "vpn, acesso", "ticket_id": "h12"})
    assert e["persisted"] is False and e["id"].startswith("kb-") and e["ticket_id"] == "h12"
    assert e["tags"] == ["vpn", "acesso"] and e["customer_reply"] is None and e["created_at"]


def test_closure_options_shape():
    o = closure_options()
    assert o["categories"] == CLASSES and o["subcategories"] == SUBCATEGORIES and o["levels"] == LEVELS
    assert o["required"] == REQUIRED and len(o["root_causes"]) >= 5
