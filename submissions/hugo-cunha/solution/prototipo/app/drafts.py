"""Per-class reply drafts (macros) for auto-routed tickets.

There is no LLM in the prototype: each draft is a fixed pt-BR macro that a
human analyst reviews, edits and sends. A draft exists only for the classes in
``policy.AUTO`` and is only returned when the gate decision is ``auto_route``.
The drafts acknowledge the ticket and ask for what the analyst needs next; they
never promise a resolution, an approval or a deadline.
"""

from __future__ import annotations

__all__ = ["DRAFTS", "draft_for"]

DRAFTS: dict[str, str] = {
    "Access": (
        "Olá! Recebemos sua solicitação de acesso e ela já está na fila da equipe responsável.\n"
        "Para agilizar a análise, confirme por favor:\n"
        "- o sistema ou recurso ao qual precisa de acesso;\n"
        "- o nome do gestor aprovador e se a aprovação já foi dada;\n"
        "- a partir de quando o acesso é necessário.\n"
        "A concessão depende dessa aprovação e é feita por um analista, que retornará neste chamado."
    ),
    "Storage": (
        "Olá! Sua solicitação sobre espaço de armazenamento já está na fila da equipe responsável.\n"
        "Enquanto analisamos, algumas ações costumam liberar espaço rapidamente:\n"
        "- esvaziar a lixeira e a pasta de itens excluídos do e-mail;\n"
        "- remover arquivos temporários e duplicados;\n"
        "- mover arquivos grandes e antigos para a área compartilhada ou para o arquivo morto.\n"
        "Se ainda precisar de mais cota, informe o volume estimado e a justificativa; o aumento é avaliado por um analista."
    ),
    "Hardware": (
        "Olá! Recebemos seu chamado sobre o equipamento e ele já está na fila da equipe de suporte.\n"
        "Para acelerar o diagnóstico, informe por favor:\n"
        "- modelo do equipamento e número de patrimônio (etiqueta);\n"
        "- se o problema persiste após reiniciar o equipamento;\n"
        "- data e resultado da última atualização instalada.\n"
        "Com essas informações um analista dará continuidade ao atendimento."
    ),
}


def draft_for(category: str, decision: str | None) -> str | None:
    """Return the macro for ``category`` only when ``decision == "auto_route"``.

    Any other decision (suggest, human_triage, human_required) yields ``None``:
    a human writes the reply from scratch.
    """
    if decision != "auto_route":
        return None
    return DRAFTS.get(category)
