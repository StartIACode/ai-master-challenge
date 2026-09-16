"""Standardized ticket-closure template (spec section 4) and the illustrative KB.

Two things live here:

* ``validate_closure(payload)``: the rule "a ticket does not close without the
  template filled in". Returns a list of pt-BR error messages; an empty list means
  the payload is a valid closure. ``build_kb_entry(payload)`` normalizes a valid
  payload into the record that would enter the knowledge base (the prototype does
  not persist it: ``persisted=False``).
* ``SUBCATEGORIES`` / ``ROOT_CAUSE_OPTIONS`` / ``LEVELS``: the dependent lists the
  form offers.
* ``kb_examples(category)``: plausible, hand-written closures per class used by the
  "similarity after standardization" screen. They are **illustrative** (every
  entry carries ``illustrative=True``): the similarity shown next to them is real,
  the closure content is what the base would look like after ~30 days of
  standardized closures. They are also valid against ``validate_closure``.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from app.policy import CLASSES

__all__ = [
    "ILLUSTRATIVE_NOTE",
    "LEVELS",
    "MIN_STEPS_CHARS",
    "OPTIONAL",
    "REQUIRED",
    "ROOT_CAUSE_OPTIONS",
    "SUBCATEGORIES",
    "build_kb_entry",
    "closure_options",
    "kb_examples",
    "validate_closure",
]

REQUIRED = ["category", "subcategory", "root_cause", "resolution_steps", "resolved_by_level",
            "time_spent_min", "reusable", "reopened"]
OPTIONAL = ["ticket_id", "customer_reply", "kb_article", "satisfaction", "affected_system", "tags"]
LEVELS = ["N1-IA", "N2", "N3"]
MIN_STEPS_CHARS = 20

ILLUSTRATIVE_NOTE = (
    "Exemplo ilustrativo: como ficaria após 30 dias de fechamentos padronizados. "
    "A similaridade e as classes são reais; o conteúdo do fechamento não."
)

SUBCATEGORIES: dict[str, list[str]] = {
    "Access": [
        "Novo acesso",
        "Acesso bloqueado ou senha",
        "Permissão em pasta ou sistema",
        "Revogação de acesso",
        "Acesso remoto / VPN",
    ],
    "Administrative rights": [
        "Instalação de software",
        "Elevação temporária de privilégio",
        "Administrador local",
        "Configuração bloqueada por política",
    ],
    "HR Support": [
        "Admissão / novo colaborador",
        "Desligamento",
        "Folha e benefícios",
        "Férias e afastamentos",
        "Dados cadastrais",
    ],
    "Hardware": [
        "Notebook / desktop",
        "Impressora",
        "Periféricos (monitor, teclado, mouse)",
        "Rede e conectividade",
        "Telefonia / celular",
    ],
    "Internal Project": [
        "Recurso para o projeto",
        "Status / acompanhamento",
        "Mudança de escopo",
        "Ambiente de projeto",
    ],
    "Miscellaneous": [
        "Dúvida geral",
        "Pedido fora de catálogo",
        "Encaminhamento a outra área",
        "Informativo / sem ação",
    ],
    "Purchase": [
        "Cotação",
        "Aprovação de compra",
        "Entrega / recebimento",
        "Renovação de licença",
        "Nota fiscal / pagamento",
    ],
    "Storage": [
        "Cota de e-mail",
        "Cota de rede / pasta compartilhada",
        "Cota de nuvem",
        "Backup e restauração",
        "Arquivamento",
    ],
}

ROOT_CAUSE_OPTIONS = [
    "Erro do usuário / desconhecimento",
    "Falta de permissão ou aprovação",
    "Falha de configuração",
    "Defeito de hardware",
    "Falha de software / atualização",
    "Processo não seguido",
    "Capacidade ou cota esgotada",
    "Outro (descrever)",
]

_TRUE = {"true", "1", "sim", "yes", "s", "y"}
_FALSE = {"false", "0", "nao", "não", "no", "n"}


# --------------------------------------------------------------------------- coercion
def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in _TRUE:
            return True
        if v in _FALSE:
            return False
    return None


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace(",", "."))
        except ValueError:
            return None
    return None


def _as_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ("" if value is None else str(value).strip())


def _is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


# --------------------------------------------------------------------------- validation
def validate_closure(payload: dict | None) -> list[str]:
    """Return pt-BR error messages for the closure form; ``[]`` means valid."""
    p = payload or {}
    errors: list[str] = []

    category = _as_text(p.get("category"))
    if _is_missing(p.get("category")):
        errors.append("Categoria é obrigatória.")
    elif category not in CLASSES:
        errors.append("Categoria inválida: escolha uma das 8 classes.")

    subcategory = _as_text(p.get("subcategory"))
    if _is_missing(p.get("subcategory")):
        errors.append("Subcategoria é obrigatória.")
    elif category in SUBCATEGORIES and subcategory not in SUBCATEGORIES[category]:
        errors.append(f"Subcategoria inválida para a categoria {category}.")

    if _is_missing(p.get("root_cause")):
        errors.append("Causa raiz é obrigatória.")

    steps = _as_text(p.get("resolution_steps"))
    if _is_missing(p.get("resolution_steps")):
        errors.append("Ação de resolução (passo a passo) é obrigatória.")
    elif len(steps) < MIN_STEPS_CHARS:
        errors.append(f"Ação de resolução precisa ter pelo menos {MIN_STEPS_CHARS} caracteres.")

    level = _as_text(p.get("resolved_by_level"))
    if _is_missing(p.get("resolved_by_level")):
        errors.append("Nível que resolveu é obrigatório.")
    elif level not in LEVELS:
        errors.append("Nível que resolveu inválido: use N1-IA, N2 ou N3.")

    if _is_missing(p.get("time_spent_min")):
        errors.append("Tempo gasto (min) é obrigatório.")
    else:
        minutes = _as_number(p.get("time_spent_min"))
        if minutes is None or minutes <= 0:
            errors.append("Tempo gasto (min) deve ser um número maior que zero.")

    if _is_missing(p.get("reusable")):
        errors.append("Informe se a resposta é reutilizável como resposta padrão (sim/não).")
    elif _as_bool(p.get("reusable")) is None:
        errors.append("Campo 'reutilizável' inválido: use sim ou não.")

    if _is_missing(p.get("reopened")):
        errors.append("Informe se o ticket foi reaberto (sim/não).")
    elif _as_bool(p.get("reopened")) is None:
        errors.append("Campo 'reaberto' inválido: use sim ou não.")

    if not _is_missing(p.get("satisfaction")):
        s = _as_number(p.get("satisfaction"))
        if s is None or s != int(s) or not 1 <= s <= 5:
            errors.append("Satisfação deve ser um inteiro de 1 a 5.")

    return errors


def build_kb_entry(payload: dict) -> dict:
    """Normalize a **valid** payload into the record that would enter the knowledge base."""
    p = payload or {}
    category = _as_text(p.get("category"))
    steps = _as_text(p.get("resolution_steps"))
    tags = p.get("tags")
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    elif not isinstance(tags, list):
        tags = []
    satisfaction = _as_number(p.get("satisfaction")) if not _is_missing(p.get("satisfaction")) else None
    digest = hashlib.sha1(f"{category}|{_as_text(p.get('subcategory'))}|{steps}".encode("utf-8")).hexdigest()[:8]
    return {
        "id": f"kb-{digest}",
        "ticket_id": _as_text(p.get("ticket_id")) or None,
        "category": category,
        "subcategory": _as_text(p.get("subcategory")),
        "root_cause": _as_text(p.get("root_cause")),
        "resolution_steps": steps,
        "resolved_by_level": _as_text(p.get("resolved_by_level")),
        "time_spent_min": _as_number(p.get("time_spent_min")),
        "customer_reply": _as_text(p.get("customer_reply")) or None,
        "reusable": bool(_as_bool(p.get("reusable"))),
        "reopened": bool(_as_bool(p.get("reopened"))),
        "kb_article": _as_text(p.get("kb_article")) or None,
        "satisfaction": int(satisfaction) if satisfaction is not None else None,
        "affected_system": _as_text(p.get("affected_system")) or None,
        "tags": [str(t) for t in tags],
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "persisted": False,
        "note": "Protótipo: a entrada foi validada, mas não é gravada. Na operação real, o fechamento alimenta a base de conhecimento.",
    }


def closure_options() -> dict:
    """Lists the form needs: categories, dependent subcategories, root-cause shortlist, levels."""
    return {
        "categories": list(CLASSES),
        "subcategories": {c: list(v) for c, v in SUBCATEGORIES.items()},
        "root_causes": list(ROOT_CAUSE_OPTIONS),
        "levels": list(LEVELS),
        "required": list(REQUIRED),
        "optional": list(OPTIONAL),
        "min_steps_chars": MIN_STEPS_CHARS,
    }


# --------------------------------------------------------------------------- illustrative KB
def _closure(category: str, subcategory: str, root_cause: str, steps: list[str], level: str, minutes: int,
             reply: str | None, reusable: bool, kb_article: str | None, reopened: bool = False) -> dict:
    return {
        "category": category,
        "subcategory": subcategory,
        "root_cause": root_cause,
        "resolution_steps": "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1)),
        "resolved_by_level": level,
        "time_spent_min": minutes,
        "customer_reply": reply,
        "reusable": reusable,
        "reopened": reopened,
        "kb_article": kb_article,
        "illustrative": True,
    }


_KB: dict[str, list[dict]] = {
    "Access": [
        _closure(
            "Access", "Novo acesso", "Conta criada fora do grupo de segurança exigido pelo sistema",
            ["Conferir no diretório o grupo exigido pelo sistema", "Validar a aprovação do gestor no chamado",
             "Adicionar a conta ao grupo", "Pedir ao usuário para sair e entrar novamente",
             "Confirmar o acesso com o usuário"],
            "N2", 12,
            "Olá! Seu acesso foi liberado após a aprovação do gestor. Saia e entre novamente para a permissão "
            "ser aplicada. Se ainda não conseguir acessar, responda a este chamado.",
            True, "KB-ACC-014",
        ),
        _closure(
            "Access", "Acesso bloqueado ou senha", "Conta bloqueada por tentativas com a senha antiga salva no celular",
            ["Confirmar a identidade pelo canal padrão", "Desbloquear a conta no diretório",
             "Orientar a atualizar a senha salva no e-mail do celular",
             "Acompanhar por 10 minutos para garantir que não bloqueia de novo"],
            "N2", 8,
            "Olá! Sua conta foi desbloqueada. O bloqueio acontecia porque o celular ainda tentava a senha antiga: "
            "atualize a senha no aplicativo de e-mail do celular para não bloquear de novo.",
            True, "KB-ACC-003",
        ),
        _closure(
            "Access", "Acesso remoto / VPN", "Certificado do cliente de VPN expirado",
            ["Verificar a validade do certificado no cliente de VPN", "Reemitir o certificado pelo portal",
             "Importar o certificado e reconectar", "Testar o acesso à intranet"],
            "N2", 15,
            "Olá! O certificado da sua VPN estava vencido e foi renovado. Reconecte a VPN; se aparecer erro de "
            "certificado, responda a este chamado com a mensagem exibida.",
            True, "KB-ACC-021",
        ),
    ],
    "Administrative rights": [
        _closure(
            "Administrative rights", "Instalação de software", "Software solicitado fora do catálogo homologado",
            ["Confirmar se o software está no catálogo homologado", "Instalar a versão homologada pela central de software",
             "Registrar a exceção negada para o software original"],
            "N2", 20,
            "Olá! O software pedido não está homologado; instalamos a versão equivalente aprovada pela empresa. "
            "Se ela não atender à sua necessidade, descreva o uso para avaliarmos uma exceção.",
            True, "KB-ADM-007",
        ),
        _closure(
            "Administrative rights", "Elevação temporária de privilégio",
            "Ferramenta de desenvolvimento exige privilégio de administrador para depuração",
            ["Validar a justificativa técnica com o gestor", "Conceder elevação temporária de 4 horas pela ferramenta de gestão de privilégios",
             "Registrar a revogação automática", "Auditar as ações no fim do período"],
            "N3", 35, None, False, "KB-ADM-002",
        ),
    ],
    "HR Support": [
        _closure(
            "HR Support", "Admissão / novo colaborador", "Cadastro do novo colaborador não chegou ao TI antes da data de início",
            ["Confirmar com o RH a data de início e o centro de custo", "Criar conta, e-mail e acessos-padrão do cargo",
             "Agendar a entrega do equipamento", "Enviar as orientações de primeiro acesso ao gestor"],
            "N2", 25,
            "Olá! A conta e o e-mail do novo colaborador foram criados e o equipamento está agendado. As "
            "orientações de primeiro acesso seguem em anexo para o gestor.",
            True, "KB-HR-011",
        ),
        _closure(
            "HR Support", "Folha e benefícios", "Dúvida sobre desconto em folha que exigia análise individual do RH",
            ["Verificar que o pedido é de esclarecimento, não incidente de sistema",
             "Encaminhar ao RH com o contexto do colaborador", "Confirmar o retorno do RH ao colaborador em até 2 dias úteis"],
            "N2", 10, None, False, None,
        ),
    ],
    "Hardware": [
        _closure(
            "Hardware", "Notebook / desktop", "Driver de vídeo corrompido após atualização do sistema operacional",
            ["Coletar modelo e número de patrimônio", "Reiniciar em modo de segurança",
             "Reinstalar o driver de vídeo pelo pacote do fabricante", "Reiniciar e validar com o usuário"],
            "N2", 30,
            "Olá! O problema era o driver de vídeo, corrompido pela última atualização. Reinstalamos o driver e o "
            "equipamento voltou ao normal. Se a tela falhar de novo, responda a este chamado.",
            True, "KB-HW-032",
        ),
        _closure(
            "Hardware", "Impressora", "Fila de impressão travada no servidor por documento corrompido",
            ["Identificar a impressora e o servidor de impressão", "Cancelar o documento travado",
             "Reiniciar o serviço de fila de impressão", "Pedir ao usuário para imprimir uma página de teste"],
            "N2", 10,
            "Olá! A fila da impressora estava travada por um documento com erro; a fila foi liberada. Por favor, "
            "imprima uma página de teste e confirme neste chamado.",
            True, "KB-HW-005",
        ),
        _closure(
            "Hardware", "Periféricos (monitor, teclado, mouse)", "Monitor externo sem sinal por cabo com pino danificado",
            ["Testar com outro cabo", "Substituir o cabo", "Registrar a baixa do cabo com defeito",
             "Confirmar a resolução com o usuário"],
            "N2", 12,
            "Olá! O monitor não recebia sinal por causa do cabo, que foi trocado. Se a imagem falhar novamente, "
            "responda a este chamado.",
            True, "KB-HW-018",
        ),
    ],
    "Internal Project": [
        _closure(
            "Internal Project", "Recurso para o projeto", "Ambiente de homologação do projeto sem capacidade para a nova sprint",
            ["Confirmar a demanda com o líder do projeto", "Abrir a solicitação ao PMO com o custo estimado",
             "Provisionar após a aprovação", "Comunicar o time do projeto"],
            "N3", 60, None, False, None,
        ),
        _closure(
            "Internal Project", "Status / acompanhamento", "Pedido de status de entrega que pertence ao PMO, não ao suporte",
            ["Identificar o projeto e o responsável no PMO", "Encaminhar o chamado ao PMO",
             "Informar o solicitante sobre o novo responsável"],
            "N2", 5,
            "Olá! Este pedido é acompanhado pelo PMO, que já recebeu o chamado e responderá por aqui.",
            True, "KB-PRJ-001",
        ),
    ],
    "Miscellaneous": [
        _closure(
            "Miscellaneous", "Dúvida geral", "Pedido genérico sem sistema identificado; precisou de esclarecimento",
            ["Pedir ao solicitante o sistema e o erro exato", "Reclassificar o chamado após a resposta",
             "Seguir o playbook da nova categoria"],
            "N2", 8,
            "Olá! Para ajudarmos, informe o sistema ou equipamento envolvido e a mensagem de erro exata (ou uma "
            "captura de tela). Com isso encaminhamos ao time certo.",
            True, None,
        ),
        _closure(
            "Miscellaneous", "Informativo / sem ação", "Mensagem automática de monitoramento encaminhada por engano ao suporte",
            ["Confirmar que é alerta automático sem incidente", "Ajustar a regra de encaminhamento com o time de monitoramento",
             "Encerrar sem ação para o usuário"],
            "N2", 5, None, False, None,
        ),
    ],
    "Purchase": [
        _closure(
            "Purchase", "Cotação", "Pedido de compra sem centro de custo e sem aprovação do gestor",
            ["Solicitar o centro de custo e a aprovação do gestor", "Obter duas cotações com fornecedores homologados",
             "Registrar o pedido no sistema de compras", "Informar o prazo previsto ao solicitante"],
            "N2", 40,
            "Olá! Para seguir com a compra precisamos do centro de custo e da aprovação do gestor. Assim que "
            "recebermos, fazemos as cotações e informamos o prazo.",
            True, "KB-PUR-004",
        ),
        _closure(
            "Purchase", "Renovação de licença", "Licença expirada por renovação não programada",
            ["Confirmar produto, quantidade e vencimento", "Emitir o pedido de renovação com aprovação do gestor",
             "Aplicar a nova chave", "Registrar lembrete 60 dias antes do próximo vencimento"],
            "N2", 25,
            "Olá! A licença foi renovada e a nova chave já está aplicada. Registramos um lembrete para a "
            "próxima renovação, 60 dias antes do vencimento.",
            True, "KB-PUR-009",
        ),
    ],
    "Storage": [
        _closure(
            "Storage", "Cota de e-mail", "Caixa de e-mail cheia por anexos antigos na pasta Enviados",
            ["Verificar o uso da cota", "Orientar a esvaziar Itens Excluídos e arquivar os Enviados antigos",
             "Ativar o arquivamento automático", "Confirmar o espaço liberado"],
            "N2", 10,
            "Olá! Sua caixa estava cheia por anexos antigos em Enviados. Esvazie Itens Excluídos e arquive os "
            "e-mails antigos; o arquivamento automático foi ativado para evitar que se repita.",
            True, "KB-STO-002",
        ),
        _closure(
            "Storage", "Cota de rede / pasta compartilhada", "Pasta compartilhada da área atingiu a cota por arquivos duplicados",
            ["Gerar relatório de duplicados e arquivos grandes", "Enviar ao gestor da área para limpeza",
             "Aumentar a cota em 20% após aprovação, se ainda necessário"],
            "N2", 20,
            "Olá! A pasta da área atingiu a cota. Enviamos ao gestor um relatório de arquivos duplicados e "
            "grandes; após a limpeza, avaliamos se ainda é preciso aumentar a cota.",
            True, "KB-STO-007",
        ),
        _closure(
            "Storage", "Backup e restauração", "Arquivo excluído por engano em pasta de rede",
            ["Confirmar o caminho e a data aproximada", "Restaurar do snapshot diário", "Validar com o usuário"],
            "N2", 15,
            "Olá! O arquivo foi restaurado do backup diário no mesmo caminho. Confira e confirme neste chamado.",
            True, "KB-STO-011",
        ),
    ],
}


def kb_examples(category: str) -> dict:
    """Illustrative closures for ``category``: ``{category, illustrative, note, examples:[...]}``.

    Every example carries ``illustrative=True``. Raises ``KeyError`` for an unknown class.
    """
    if category not in _KB:
        raise KeyError(category)
    return {
        "category": category,
        "illustrative": True,
        "note": ILLUSTRATIVE_NOTE,
        "examples": [dict(e) for e in _KB[category]],
    }
