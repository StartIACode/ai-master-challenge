# Desenho da solução — Challenge 002 (Redesign de Suporte)

Data: 2026-09-16 · Autor: Hugo Cunha (com Claude Code) · Estado: aprovado em chat, base para a implementação

## 1. Tese

Com os dados fornecidos não se mede onde o suporte perde tempo: o Dataset 1 é sintético e sem sinal. O que se automatiza hoje, com prova, é a **triagem**: um classificador local roteia sozinho a fatia dos tickets em que a precisão medida é ≥ 97% e devolve o resto a uma pessoa. A **resolução assistida por similaridade** (a proposta do Hugo) só funciona depois de um passo de processo: **fechamento de ticket padronizado**, que cria a base de conhecimento. O protótipo mostra os dois: a triagem rodando sobre tickets reais e, em tela ilustrativa, como fica a similaridade depois da padronização.

Regra inegociável em texto e código: **a IA nunca responde ao cliente nem fecha ticket.** Ela classifica, prioriza, roteia e prepara. Humano responde e fecha.

## 2. Fatos que moldam o desenho

| Fato medido | Consequência no desenho |
|---|---|
| Dataset 1 (8.469 linhas, não 30 mil) é gerado por script: placeholder em 100% das descrições, resoluções aleatórias, tempos numa janela de 27 h com 49,3% "resolvidos antes da 1ª resposta", satisfação sem associação com nada (p > 0,14) | Diagnóstico entrega a tabela que o brief pede com o veredito "cabe no ruído"; Dataset 1 vira controle negativo do pipeline e fonte de exemplos do que não automatizar (Refund, Cancellation, Billing) |
| Dataset 2 (47.837 tickets reais de TI, 8 classes) sem campo de resolução | Não existe "como foi resolvido" para recuperar; similaridade recupera tickets parecidos e a fila deles (real), não a tratativa |
| Classificador TF-IDF + regressão logística: 86,7% (5-fold); confiança ≥ 0,90 cobre ~54% com 98,2% de acerto | Gate por confiança é a decisão de negócio central; slider no painel |
| Cosseno ≥ 0,90 cobre ~6% dos tickets; 1-NN acerta 70,7% | Similaridade é evidência para o N2 e desduplicação, não regra de decisão, até existir base padronizada |

## 3. Fluxo operacional: N1-IA → N2 → N3

### 3.1 Entrada (N1-IA)
Todo ticket entra pelo N1-IA, que devolve: classe prevista, confiança `p`, top-3 classes, top-3 tickets históricos parecidos com a classe deles e a similaridade, sinais de risco, decisão do gate, fila de destino, motivo e rascunho por classe (macro; LLM desligado na demo).

### 3.2 Gate de decisão (nesta ordem)
1. **Sinal de risco** no texto (jurídico/Procon, cancelamento, reembolso, assédio/ameaça, saúde, VIP/enterprise, canal social público, reaberto) → **N2, "humano obrigatório"**, sem rascunho.
2. `p ≥ limiar` **e** classe em **AUTO = {Access, Storage, Hardware}** → **auto-roteio**: entra na fila da classe com rascunho pronto; o humano responde em 1 clique, edita ou marca "IA errou". Conta como "tratado pela IA" (triagem automática, não resolução).
3. `p ≥ limiar` **e** classe em **SUGERIR = {Purchase, HR Support, Administrative rights, Internal Project}** → **sugere a fila**; N2 confirma antes de entrar; sem rascunho.
4. `p < limiar` **ou** classe **Miscellaneous** → **N2-triagem** (humano decide a fila). Miscellaneous nunca conta como roteado.

Limiar padrão **0,90**, ajustável no painel entre 0,50 e 0,99.

**O que o limiar significa (esclarecimento pedido pelo Hugo):** o classificador devolve, para cada ticket, uma probabilidade de 0 a 1 de que a classe prevista esteja certa. O limiar é o mínimo de confiança para a IA agir sozinha. Medido no hold-out: em 0,80 a IA roteia sozinha ~66% dos tickets e acerta 96,7% deles; em 0,90 roteia ~54% e acerta 98,2%; em 0,95 roteia ~44% e acerta 99,1%. Subir o limiar = menos tickets automáticos e menos erros. Recomendação: abrir o piloto em 0,90 e afrouxar para 0,80 depois do modo sombra, se a taxa de "IA errou" ficar abaixo do re-roteamento humano atual.

### 3.3 Por que cada classe está onde está
| Classe (volume) | Ação | Motivo |
|---|---|---|
| Access (7.125) | auto-roteio com rascunho | repetitivo, alta precisão; rotear ≠ conceder acesso (concessão continua humana) |
| Storage (2.777) | auto-roteio com rascunho | melhor precisão entre as classes auto-roteáveis; aumento de cota é decisão do N2 |
| Hardware (13.617) | auto-roteio com rascunho | troubleshooting padronizável; é a classe que absorve confusões (precision 0,81): primeira a ter kill switch |
| Purchase (2.464) | sugerir | dinheiro e aprovação |
| HR Support (10.915) | sugerir, nunca rascunho | pessoas; maior tentação de automatizar, exemplo central do que não automatizar |
| Administrative rights (1.760) | sugerir | elevação de privilégio = segurança; modelo erra 31% da classe (recall 0,69) |
| Internal Project (2.119) | sugerir | não é suporte; vai ao PMO |
| Miscellaneous (7.060) | sempre humano | "não sei" por definição |
| Dataset 1: Refund, Cancellation, Billing | sempre humano | momento de retenção, dinheiro, requisito de atendimento humano |

### 3.4 N2 e N3
- **N2**: analista com playbook e permissões limitadas; resolve de bate-pronto sem acionar outras áreas. Escala ao N3 por clique quando: precisa de permissão que não tem; sem playbook após 2 tentativas; incidente multi-cliente; risco legal/financeiro; 2ª reabertura.
- **N3**: especialista; envolve outras áreas; devolve playbook obrigatório, que vira macro do N2. É assim que a cobertura da IA cresce sem retreinar modelo.
- **Fases de adoção**: (1) modo sombra 2–4 semanas, IA só sugere; (2) liberação por classe com ≥ 95% de aceitação em 200 sugestões e reabertura ≤ N2; (3) resposta automática só nas classes liberadas, ainda com fechamento humano.

## 4. Template de fechamento de ticket (proposta do Hugo)

Problema que resolve: nenhum dos datasets tem "como foi resolvido" de forma utilizável, e é isso que a operação real também costuma não ter. Sem fechamento padronizado não há base de conhecimento, e sem base não há similaridade útil.

Regra: **o ticket não fecha na ferramenta atual sem o template preenchido.** O formulário do protótipo é ilustrativo; na prática os campos são configurados na ferramenta que a operação já usa.

| Campo | Obrigatório | Tipo |
|---|---|---|
| Categoria | sim | lista (8 classes) |
| Subcategoria | sim | lista dependente da categoria |
| Causa raiz | sim | lista curta + texto |
| Ação de resolução (passo a passo) | sim | texto ≥ 20 caracteres |
| Nível que resolveu | sim | N1-IA / N2 / N3 |
| Tempo gasto (min) | sim | número |
| Resposta enviada ao cliente | se houve resposta | texto |
| Reutilizável como resposta padrão? | sim | sim/não |
| Artigo de base de conhecimento vinculado | não | link/ID |
| Reaberto? | sim | sim/não |
| Satisfação | não | 1–5 |
| Produto/sistema afetado, tags | não | texto |

**Retro-padronização da base atual**: um LLM lê os fechamentos legados em texto livre e preenche o template; uma amostra é revisada por humanos antes de entrar na base. Custo estimado para 30.000 tickets com Haiku 4.5: dezenas de dólares (premissa de ~1.000 tokens por ticket). Só a partir daí a "similaridade ≥ 90% com tratativa" faz sentido.

## 5. Similaridade: hoje e depois da padronização

- **Hoje (real no protótipo)**: para cada ticket, os 3 históricos mais parecidos (cosseno sobre TF-IDF do conjunto de treino) com a classe deles. Serve de evidência ao N2 e para agrupar alertas repetidos.
- **Depois da padronização (tela ilustrativa)**: o mesmo ticket com os 3 similares, cada um mostrando o template de fechamento preenchido (categoria, causa raiz, ação, resposta reutilizável). Botão "Aplicar tratativa sugerida" habilitado só com similaridade ≥ 0,90 **e** classe em AUTO **e** entrada marcada "reutilizável". Todo conteúdo de fechamento nessa tela leva o selo **"exemplo ilustrativo: como ficaria após 30 dias de fechamentos padronizados"**. A similaridade mostrada é real; a tratativa é ilustrativa.

## 6. Protótipo

### 6.1 Telas (página única, responsiva, paleta G4 sem logo)
1. **Painel**: contadores reais do replay (% N1-IA auto-roteado, % N2, % N3 por escalação humana, acerto da IA no replay, overrides "IA errou"), card "TMA real: não mensurável nos datasets", card "mesmo pipeline no Dataset 1: ~19% vs 86,7% no Dataset 2".
2. **Board** N1-IA / N2 / N3 (1 coluna abaixo de 768 px): card com texto real, classe prevista + p, classe verdadeira, top-3 similares, decisão e motivo, rascunho, responsável (SIMULADO), botões Assumir / Resolver / Escalar N3 / IA errou. Replay em lotes de 10 tickets reais do hold-out, toggle automático a cada 3 s, reiniciar.
3. **Ponto de operação**: slider de limiar recalculando no cliente cobertura bruta, cobertura útil, acerto e tickets/mês; calculadora de horas e R$ com selo SIMULAÇÃO e premissas editáveis.
4. **Política por classe**: tabela real (volume, cobertura no limiar, acerto, ação, motivo).
5. **Novo ticket**: caixa de texto + 3 exemplos reais; aviso de domínio (modelo treinado em tickets de TI em inglês, texto normalizado).
6. **Fechamento padronizado**: formulário ilustrativo (seção 4) com validação de obrigatórios.
7. **Similaridade após padronização**: tela ilustrativa (seção 5).

### 6.2 Real vs simulado
- REAL: texto dos cards, classes prevista/verdadeira, p, similares, métricas, cobertura por limiar e por classe, matriz de confusão, overrides.
- SIMULADO e rotulado: chegada (replay), nomes de responsáveis (round-robin), minutos de triagem × custo-hora, SLAs, conteúdo dos fechamentos na tela ilustrativa.

### 6.3 Contratos de API (FastAPI, JSON)
- `GET /api/health` → `{status, model_loaded, n_train, n_holdout, version}`
- `POST /api/triage` `{text, threshold?}` → `{category, confidence, top3:[{category,p}], neighbors:[{id, excerpt, category, similarity}], risk_flags:[], decision: auto_route|suggest|human_triage|human_required, level: N1|N2, queue, reason, draft}`
- `POST /api/replay/next` `{n=10, threshold?}` → `{tickets:[Ticket]}` (hold-out em ordem aleatória com seed; `Ticket` = triage + `{id, true_category, assigned_to, level, status, created_at}`)
- `POST /api/tickets/{id}/action` `{action: assume|resolve|escalate|ai_wrong}` → `Ticket`
- `GET /api/board` → `{N1:[...], N2:[...], N3:[...], resolved:int, counters:{...}}`
- `GET /api/metrics` → conteúdo de `artifacts/metrics.json` (inclui curvas por limiar para o slider)
- `GET /api/policy` → tabela de política
- `POST /api/reset` → zera o board
- `POST /api/closure` `{ticket_id, ...campos}` → valida obrigatórios; `{ok, errors[], kb_entry}`
- `GET /api/kb/example?ticket_id=` → similares com fechamento ilustrativo

Estado do board em SQLite (stdlib), tabela única, limite de 2.000 linhas, reset público.

## 7. Modelo e experimentos (fonte única de números: `artifacts/metrics.json`)
- Dados: Dataset 2; desduplicação por chave das 20 primeiras palavras; split estratificado 80/20, seed 42, índices salvos.
- Modelo: TF-IDF (1,2), min_df=2, sublinear, ≤ 300k features, float32 + regressão logística (C=5, max_iter 2000). Similaridade: cosseno sobre a matriz TF-IDF de treino.
- Artefatos: `metrics.json` (acurácia, macro-F1, por classe, cobertura/acerto por limiar global e por classe, cobertura útil pós-política, ECE), `holdout_pred.csv.gz`, figuras (matriz de confusão, cobertura × acerto, calibração), `models/index.pkl` (não versionado; regenerado por `make train`).
- Controle negativo: mesmo pipeline no Dataset 1 (descrição → tipo) deve ficar na chance (~20%).
- Testes (pytest): política nunca auto-roteia classes de SUGERIR/Miscellaneous nem tickets com risco; `/api/triage` devolve classe válida e p em [0,1]; acurácia do hold-out ≥ 0,85 e cobertura útil em 0,90 ≥ 0,25.

## 8. Diagnóstico do Dataset 1 (`scripts/diagnostico_ds1.py` → `artifacts/ds1_metrics.json`)
Tabela por canal × prioridade × tipo (n, satisfação média, "tempo" ingênuo) seguida das evidências: 49,3% de tempo negativo, janela de 27 h, placeholder em 100%, 16 primeiras frases, testes de associação p > 0,14, controle negativo. Tom: um parágrafo, uma tabela, um anexo. Sem manchete.

## 9. Custo de API e ROI paramétrico
- Classificação e similaridade: locais, R$ 0.
- LLM só no rascunho (cenário A): ~US$ 3/mês com Haiku 4.5 para 2.500 tickets/mês; Sonnet ~2×, Opus ~5×. Servidor GPU próprio: R$ 13,6–17,1 mil/ano só de hardware. Conclusão: o custo de IA é ruído; o custo real é hora de N2.
- ROI: `horas poupadas = V·c·m_t + V·(1−c)·(m_t − m_s) − V·c·e·m_e`, com `c` e `e` medidos no replay e `V`, `m_t`, `m_s`, `m_e`, custo-hora como premissas nomeadas (calculadora com 3 cenários).

## 10. Stack, pastas, setup, deploy
- Um processo Python 3.13: FastAPI + uvicorn servindo API e `web/index.html` (HTML/CSS/JS sem build). sklearn, pandas, numpy, joblib, scipy; sqlite3 da stdlib. Gerência por `uv`. Sem PHP, Docker, React, SDK de LLM.
- Pastas: `solution/prototipo/{app,scripts,web,data,artifacts,models,tests,deploy}`, `solution/diagnostico.md`, `solution/proposta.md`, `process-log/`, `docs/`.
- Setup do avaliador: `make setup && make run` (uv sync, unzip dos CSVs CC0 versionados com SHA-256, treino automático se faltar o modelo, sobe em :8010). Fallback sem uv documentado. Provado em clone limpo em `/tmp` antes do PR.
- Git: o `.gitignore` do repositório do G4 ignora `submissions/`; todo commit usa `git add -f`; `make check-tracked` confere.
- VPS (último passo): treinar no Mac, subir `index.pkl` + artefatos por scp para `/opt/g4-triagem`; systemd `MemoryMax=512M`, 1 worker em 127.0.0.1:8010; vhost `zz-g4-triagem.conf` com proxy e `certbot certonly --webroot` em `g4-triagem.187-77-249-237.sslip.io`; conferir `apache2ctl -S`.

## 11. Process log e evidências
- `process-log/prompts.md`: todos os prompts do Hugo, literais, com data/hora e o que a IA fez.
- `process-log/PROCESS_LOG.md`: tabela cronológica, ferramentas, onde a IA errou (com o par prompt → saída), o que o humano adicionou (template de fechamento, N1/N2/N3, escolha da conta e da stack), iterações, tempo por fase.
- `process-log/evidencias.pdf`: PDF gerado a partir dos prompts e dos registros; screenshots do protótipo.

## 12. Limitações e cortes
- Dataset 1 sem tempo/satisfação reais; Dataset 2 sem resolução, em inglês e pré-processado; classes de TI ≠ suporte ao cliente: a transferência do gate para a operação do G4 é premissa.
- Cortado: React/Vite, PHP, LLM ao vivo, embeddings, integração Jira/Trello, drag-and-drop, TMA numérico "real", cenários de custo além de 3, logo oficial da G4.

## 13. Plano de execução
| Fase | Entregáveis | Pronto quando |
|---|---|---|
| F0 setup | fork, branch, esqueleto, dados com hash, pyproject/uv.lock, Makefile | `git ls-files submissions/hugo-cunha` > 0 no fork |
| F1 modelo | `train.py`, `diagnostico_ds1.py`, artefatos e figuras | `make train` < 2 min; testes de métricas verdes |
| F2 API + política | `app/*`, SQLite, replay, closure, kb/example, testes | `make test` verde; `/api/health` ok |
| F3 página | `web/index.html` com as 7 telas, responsiva, paleta G4 | navegável no browser em 375 px e 1280 px; sem erro de console |
| F4 prova de setup | clone limpo em /tmp, `make setup && make run` cronometrado | < 10 min, sem editar nada |
| F5 documentos | `diagnostico.md`, `proposta.md`, README no template, process log, PDF | README ≤ 5 páginas; cada número tem origem |
| F6 PR | push no fork, PR `[Submission] Hugo Cunha — Challenge 002` | "Files changed" só em `submissions/hugo-cunha/` |
| F7 VPS | `deploy/vps.sh`, vhost, HTTPS | URL pública respondendo; link no README |
