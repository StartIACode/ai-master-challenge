"""Decision policy of the N1-IA gate.

Order of the gate (see docs/2026-09-16-desenho-solucao.md, section 3.2):

1. any risk flag in the text        -> ``human_required`` (N2, no draft)
2. confidence >= threshold and class in AUTO    -> ``auto_route`` (N1, class queue, draft)
3. confidence >= threshold and class in SUGGEST -> ``suggest`` (N2 confirms the queue)
4. confidence < threshold or Miscellaneous      -> ``human_triage`` (N2 decides)

Invariant enforced here and covered by tests: ``decide()`` never returns
``auto_route`` for a class outside ``AUTO`` nor when any risk flag is present.
The AI never answers the customer nor closes a ticket; it only routes.

Reasons and actions are user-facing strings, hence in pt-BR.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

__all__ = [
    "AUTO",
    "CLASSES",
    "DEFAULT_THRESHOLD",
    "Decision",
    "REASONS",
    "RISK_PATTERNS",
    "SUGGEST",
    "decide",
    "policy_table",
    "risk_flags",
]

CLASSES: list[str] = sorted(
    [
        "Access",
        "Administrative rights",
        "HR Support",
        "Hardware",
        "Internal Project",
        "Miscellaneous",
        "Purchase",
        "Storage",
    ]
)

AUTO: frozenset[str] = frozenset({"Access", "Storage", "Hardware"})
SUGGEST: frozenset[str] = frozenset({"Purchase", "HR Support", "Administrative rights", "Internal Project"})
DEFAULT_THRESHOLD: float = 0.90

# Risk signals that force a human regardless of confidence. EN + PT.
# Deliberately conservative: a false positive costs one human triage; a false
# negative would let the AI route a refund/legal/harassment case on its own.
RISK_PATTERNS: dict[str, str] = {
    "legal": r"\b(lawsuit|legal action|lawyer|attorney|procon|court|jur[ií]dic\w*|advogad\w*|processo judicial)\b",
    "cancel": r"\b(cancel\w*)\b",
    "refund": r"\b(refund\w*|reembols\w*|estorno|chargeback)\b",
    "harassment": r"\b(harass\w*|threat\w*|abus\w*|ass[eé]dio|amea[çc]\w*)\b",
    "health": r"\b(hospital|medical emergency|death|died|morte|faleceu|emerg[êe]ncia m[ée]dica)\b",
    "vip": r"\b(vip|enterprise account|ceo|diretor executivo)\b",
    "social": r"\b(twitter|facebook|instagram|linkedin|social media|redes? socia(?:l|is))\b",
    "reopened": r"\b(reopen\w*|reabert\w*)\b",
}
_COMPILED: dict[str, re.Pattern[str]] = {k: re.compile(v, re.IGNORECASE) for k, v in RISK_PATTERNS.items()}

REASONS: dict[str, str] = {
    "Access": "pedido repetitivo e de alta precisão; rotear não concede acesso",
    "Storage": "melhor precisão entre as classes; aumento de cota é decisão do N2",
    "Hardware": "troubleshooting padronizável; classe que absorve confusões, primeira a ter kill switch",
    "Purchase": "envolve dinheiro e aprovação: N2 confirma a fila",
    "HR Support": "envolve pessoas: nunca rascunho automático",
    "Administrative rights": "elevação de privilégio é segurança e o modelo erra 31% da classe",
    "Internal Project": "não é suporte; vai ao PMO com confirmação",
    "Miscellaneous": "classe 'não sei' por definição: sempre humano",
}

QUEUE_HUMAN_REQUIRED = "N2-humano-obrigatorio"
QUEUE_HUMAN_TRIAGE = "N2-triagem"


def _fmt(x: float) -> str:
    """pt-BR display of a probability: comma decimal; 0.995+ shows as '0,99+' instead of a misleading '1,00'."""
    if x >= 0.995:
        return "0,99+"
    return f"{x:.2f}".replace(".", ",")


@dataclass
class Decision:
    """Outcome of the gate for one ticket."""

    decision: str  # auto_route | suggest | human_triage | human_required
    level: str  # N1 | N2
    queue: str
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def risk_flags(text: str | None) -> list[str]:
    """Return the names of the risk patterns found in ``text`` (raw, not normalized).

    Order follows ``RISK_PATTERNS`` insertion order, so output is deterministic.
    """
    t = text or ""
    return [name for name, rx in _COMPILED.items() if rx.search(t)]


def decide(
    category: str,
    confidence: float,
    flags: list[str] | None,
    threshold: float | None = DEFAULT_THRESHOLD,
) -> Decision:
    """Apply the gate. See module docstring for the order of the rules."""
    if threshold is None:
        threshold = DEFAULT_THRESHOLD
    flags = list(flags or [])

    if flags:
        return Decision("human_required", "N2", QUEUE_HUMAN_REQUIRED, "sinal de risco: " + ", ".join(flags))

    if category not in REASONS:
        return Decision("human_triage", "N2", QUEUE_HUMAN_TRIAGE, f"classe desconhecida: {category!r}")

    if category == "Miscellaneous":
        return Decision("human_triage", "N2", QUEUE_HUMAN_TRIAGE, "classe Miscellaneous: " + REASONS[category])

    if confidence < threshold:
        return Decision(
            "human_triage",
            "N2",
            QUEUE_HUMAN_TRIAGE,
            f"confiança {_fmt(confidence)} abaixo do limiar {_fmt(threshold)}",
        )

    if category in AUTO:
        return Decision(
            "auto_route",
            "N1",
            category,
            f"confiança {_fmt(confidence)} ≥ {_fmt(threshold)} e classe auto-roteável: {REASONS[category]}",
        )

    # category in SUGGEST
    return Decision(
        "suggest",
        "N2",
        category,
        f"confiança {_fmt(confidence)} ≥ {_fmt(threshold)}, mas {REASONS[category]}",
    )


def policy_table() -> list[dict]:
    """One row per class, in ``CLASSES`` order: ``{category, action, reason}``."""
    rows: list[dict] = []
    for c in CLASSES:
        if c in AUTO:
            action = "auto-roteio com rascunho"
        elif c in SUGGEST:
            action = "sugerir fila"
        else:
            action = "sempre humano"
        rows.append({"category": c, "action": action, "reason": REASONS[c]})
    return rows
