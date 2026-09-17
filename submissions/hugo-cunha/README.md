# Submissão — Hugo Cunha — Challenge 002

## Sobre mim

- **Nome:** Hugo Cunha
- **LinkedIn:** LINKEDIN_PLACEHOLDER
- **Challenge escolhido:** 002 — Redesign de Suporte (Operações / CX)

---

## Executive Summary

Antes de propor, auditei os dois datasets por código: o Dataset 1 tem 8.469 tickets (não ~30 mil), é gerado por script e não permite medir tempo nem satisfação (49% dos tickets "resolvidos" antes da primeira resposta; nenhuma variável associada à nota). O Dataset 2 tem 47.837 tickets reais de TI e é onde a automação se prova: um classificador local roteia sozinho **26,5% dos tickets com 98,2% de acerto** no limiar 0,90 (cobertura bruta 53,9%), devolvendo o resto a uma pessoa. A proposta é uma triagem **N1-IA → N2 → N3** em que a IA classifica, prioriza, roteia e prepara, e **nunca responde ao cliente nem fecha ticket**, mais um **template de fechamento obrigatório** que cria a base de conhecimento que hoje não existe em nenhum dos datasets. Está rodando: protótipo com board, painel de indicadores, slider de limiar e replay de tickets reais, em `solution/prototipo/` (um comando) e em URL pública.

---

## Solução

### Abordagem

1. **Auditar antes de analisar.** Download direto do Kaggle com SHA-256, profilagem, testes de associação. O achado sobre o Dataset 1 mudou a estratégia: a tabela que o brief pede está entregue, com o veredito "cabe no ruído", e o dataset virou controle negativo do pipeline.
2. **Avaliar o desafio por várias cabeças.** Painel de agentes (avaliador do G4, gerente de operações, arquiteto, cientista cético, comunicação) mais críticos hostis, para prever o que o baseline de IA diria e o que separaria a entrega dele.
3. **Minha proposta como hipótese.** Desenhei N1-IA → N2 → N3 com painel de filas; a IA testou cada parte contra os dados. O que não sobreviveu (responder com a "tratativa do ticket 90% parecido", TMA "real", dados fake) foi trocado, e a lacuna virou processo: fechamento padronizado + retro-padronização da base.
4. **Contratos antes de código.** Especificação e plano com contratos de API fixos; agentes construindo em paralelo; revisor independente por etapa; todo número dos documentos vem de um único `make train`.

Documentos: [`docs/2026-09-16-desenho-solucao.md`](docs/2026-09-16-desenho-solucao.md) (spec) · [`docs/2026-09-16-plano-implementacao.md`](docs/2026-09-16-plano-implementacao.md) (plano).

### Resultados / Findings

**1. Diagnóstico** ([`solution/diagnostico.md`](solution/diagnostico.md))

| O que o brief pede | O que os dados sustentam |
|---|---|
| Gargalos por canal, prioridade e tipo | Diferenças de CSAT entre 2,93 e 3,08 e de "tempo" entre −0,56 h e +0,39 h: cabem no ruído (p > 0,14 em 13 de 14 testes). |
| O que impacta satisfação | Nenhuma variável; a nota é um sorteio uniforme de 1 a 5 (média 2,99, desvio 1,41). |
| Quanto desperdiçamos | Não mensurável nestes arquivos: os campos de tempo são carimbos numa janela de 27 h. O que exportar do helpdesk para medir em duas semanas está no diagnóstico. |
| Onde a IA acerta e erra (Dataset 2) | 86,5% de acurácia no hold-out de 9.490 tickets; Hardware absorve confusões; Administrative rights é a classe menos reconhecida (recall 0,68). |

**2. Proposta de automação** ([`solution/proposta.md`](solution/proposta.md))

- Gate por confiança com limiar ajustável: 0,80 → 32,9% de cobertura útil com 96,2% de acerto; **0,90 → 26,5% com 98,2%**; 0,95 → 20,9% com 98,8%.
- Política por classe: Access, Storage e Hardware auto-roteiam com rascunho; Purchase, HR Support, Administrative rights e Internal Project só recebem sugestão; Miscellaneous, baixa confiança e qualquer sinal de risco vão sempre a uma pessoa.
- **O que NÃO automatizar:** responder ao cliente, fechar ticket, conceder acesso ou privilégio, HR Support, Purchase, Refund/Cancellation/Billing, o terço de baixa confiança (33,8% dos tickets acertam só 66,6%).
- **Template de fechamento obrigatório + retro-padronização** (decisão humana): sem ele não há base de conhecimento; com ele a similaridade passa a valer uma tratativa.
- Custo de API: dezenas de dólares por mês para 2.500 tickets/mês; GPU própria custaria R$ 13 a 17 mil por ano. O custo real é hora de N2. ROI paramétrico com 3 cenários, premissas rotuladas.

**3. Protótipo funcional** ([`solution/prototipo/`](solution/prototipo/))

- Um processo Python (FastAPI + página única). Sem chave de API, sem Docker, sem build.
- Replay dos 9.490 tickets reais do hold-out pelo pipeline; cada card mostra classe prevista **e** verdadeira (os erros aparecem na tela). Contadores de % N1-IA, % N2, % N3 e "IA errou" são reais; chegada, responsáveis e custo-hora são simulados e rotulados.
- Abas: Painel · Board N1-IA/N2/N3 · Ponto de operação (slider de limiar + calculadora com selo SIMULAÇÃO) · Política por classe · Novo ticket · Fechamento padronizado · Similaridade após padronização (exemplo ilustrativo).
- 104 testes automatizados; `make train` regenera modelo, métricas e figuras em ~75 s.

```bash
cd submissions/hugo-cunha/solution/prototipo && make setup && make run
```

Abra http://localhost:8010. Detalhes e fallback sem `uv` em [`solution/prototipo/README.md`](solution/prototipo/README.md). Screenshots em [`process-log/screenshots/`](process-log/screenshots/). URL pública: **https://g4-triagem.187-77-249-237.sslip.io** (VPS do candidato, Apache + Let's Encrypt; sem autenticação, dados reais do hold-out; o botão Reiniciar zera o board)

### Recomendações

1. **Semana 1: exportar o log de auditoria do helpdesk** (transições de status com hora, reatribuições, categoria inicial e final, nível que resolveu) e cronometrar 2 semanas de trabalho ativo com 5 agentes. Sem isso, "tempo perdido" é premissa.
2. **Semana 1: tornar o template de fechamento obrigatório** na ferramenta atual e iniciar a retro-padronização do histórico com IA (amostra revisada por pessoas).
3. **Semanas 2–5: modo sombra da triagem N1-IA** em limiar 0,90, só sugerindo; medir aceitação e reabertura por classe e o re-roteamento humano atual como baseline; kappa de 200 tickets entre 2 triadores.
4. **Liberação por classe** (Access, Storage, Hardware primeiro) com ≥ 95% de aceitação em 200 sugestões e kill switch por classe; afrouxar para 0,80 só depois.
5. **Resposta sugerida por similaridade** apenas quando houver 30 dias de fechamentos padronizados; o humano continua enviando.

### Limitações

- Dataset 1 não mede tempo nem satisfação; Dataset 2 não tem resolução, é de TI e em inglês: a transferência do gate para a operação do G4 é premissa e o modelo é descartável (retreinar no histórico real).
- TMA por nível não existe no protótipo: está rotulado "não mensurável nos datasets".
- Acurácia humana da triagem não foi medida; se as pessoas acertam ~88%, o ganho é de consistência e log, não de acurácia.
- LLM desligado na demo (rascunhos por macro); sem drift, retreino ou feedback loop demonstrados.
- Tudo construído em uma sessão; horas reais por etapa no process log.

---

## Process Log — Como usei IA

> Narrativa completa, linha do tempo com horas reais, erros da IA e decisões humanas em [`process-log/PROCESS_LOG.md`](process-log/PROCESS_LOG.md). Prompts literais em [`process-log/prompts.md`](process-log/prompts.md) e [`process-log/evidencias.pdf`](process-log/evidencias.pdf).

### Ferramentas usadas

| Ferramenta | Para que usou |
|------------|--------------|
| Claude Code (Claude Fable 5.1), sessão única no desktop | Tudo: leitura do brief, download e profilagem dos dados, painéis de avaliação, especificação, plano, código, testes, documentos, PR e deploy |
| Workflows multiagente do Claude Code | Avaliação por lentes + críticos hostis (16 agentes), reconciliação da minha proposta com os dados (7 agentes), construção por tarefa com revisores (12 agentes) |
| Navegador interno do Claude Code | Identidade visual do site da G4, verificação do protótipo |
| scikit-learn, FastAPI, pytest | Modelo, API e 104 testes |

### Workflow

1. Auditar os dados por código antes de qualquer proposta (P01).
2. Avaliar o desafio por 5 lentes e 3 críticos; ler a síntese e decidir.
3. Apresentar minha proposta (P02) e submetê-la ao mesmo crivo; manter o que sobrevive, trocar o que conflita com os dados.
4. Decidir stack, conta, tom e escopo (P03) e adicionar o template de fechamento.
5. Especificação e plano com contratos; construção em ondas paralelas; revisor por etapa; commit por etapa fechada.
6. Prova de setup em clone limpo, README, PR, deploy público.

### Onde a IA errou e como corrigi

Nove ocorrências registradas com o par prompt → saída na seção 4 do process log. As três que mais importam: aceitar o brief sem conferir (corrigido pela profilagem); a regra "similaridade ≥ 90% responde com a tratativa" da minha própria proposta, que os dados derrubaram (cobre 5,1% e não há resolução para recuperar); e o `git add -f` que arrastou 8.841 arquivos do ambiente virtual.

### O que eu adicionei que a IA sozinha não faria

A arquitetura N1-IA → N2 → N3 com o N2 definido operacionalmente; o template de fechamento obrigatório e a retro-padronização como resposta à falta de base de conhecimento; a escolha de API em vez de modelo próprio com a conta feita; as decisões de escopo (um runtime, LLM desligado, VPS por último) e a regra de que a IA nunca responde nem fecha.

---

## Evidências

- [x] Chat export: prompts literais com data/hora em `process-log/prompts.md` e `process-log/evidencias.pdf`
- [x] Screenshots do protótipo em `process-log/screenshots/`
- [x] Git history: commits por etapa no branch `submission/hugo-cunha`
- [x] Outro: sínteses dos painéis multiagente resumidas no process log; artefatos reproduzíveis (`make train`)

---

_Submissão enviada em: 16/09/2026_
