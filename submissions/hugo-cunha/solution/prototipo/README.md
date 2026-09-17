# Protótipo — Triagem N1-IA / N2 / N3

Um processo Python (FastAPI + página única) que roda o classificador de tickets sobre os **47.837 tickets reais** do Dataset 2, traduzidos para pt-BR, e mostra a triagem N1-IA → N2 → N3 funcionando em 4 abas: **Painel** (indicadores do gestor e TMA por nível medido no board), **Board** (filas N1-IA / N2 / N3 com tickets reais), **Novo ticket** (triagem de texto livre) e **Fechamento padronizado** (template obrigatório que alimenta a base de conhecimento).

## Rodar em 2 comandos

Requisitos: Python ≥ 3.12 e [`uv`](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`). Mac ou Linux; ~1,5 GB de RAM livre durante o treino.

```bash
make setup   # uv sync + extrai os CSVs (CC0, versionados em data/) e confere os SHA-256
make run     # treina se models/index.pkl não existir (~75 s) e sobe em http://localhost:8010
```

Outros alvos: `make train` (regenera modelo, `artifacts/metrics.json`, `artifacts/ds1_metrics.json` e figuras), `make test` (113 testes), `make clean`.

**Idioma.** O Dataset 2 é em inglês; a decisão de trabalhar em português levou a uma tradução automática offline única (`scripts/traduzir_ds2.py`, Argos/CTranslate2, ~25 min num Mac), versionada em `data/ds2_pt.csv.gz` com `data/ds2_pt.meta.json`. `train.py` usa o corpus em português quando esse arquivo existe; apague-o para treinar em inglês. Termos de produto (Windows, Outlook, VPN…) são preservados; o texto-fonte já vinha sem pontuação e sem stopwords, então a tradução é telegráfica.

Sem `uv`:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e . pytest httpx
unzip -o data/ds1.zip -d data && unzip -o data/ds2.zip -d data
python scripts/train.py && python scripts/diagnostico_ds1.py
uvicorn app.api:app --port 8010
```

Prova de setup em clone limpo (Mac M-series, 16/09/2026): `git clone` + `make setup` + `make train` + `make test` em **2 min 00 s** (1:59,7 de relógio; 105 testes verdes).

## O que é real e o que é simulado

| Real (medido no hold-out de 9.490 tickets nunca vistos no treino) | Simulado (rotulado na tela) |
|---|---|
| Texto dos cards (tradução pt-BR de tickets reais), classe prevista **e** verdadeira, confiança, top-3, 3 tickets similares com similaridade | Chegada em lotes (replay) |
| Cobertura e acerto por limiar e por classe, matriz de confusão, calibração (`artifacts/metrics.json`) | Hora de chegada e nomes dos responsáveis (rodízio) |
| Contadores do board: tickets recebidos, % tratados pela IA (N1-IA), % delegados ao humano (N2), % escalados (N3), acerto da IA, "IA errou" | Entrada da base de conhecimento gerada pelo formulário de fechamento (validada, não persistida) |
| **TMA por nível** = tempo médio que os cards ficaram em cada coluna do board nesta sessão (selo MEDIDO NO BOARD) | Datasets não têm tempos reais: o TMA medido reflete a operação do board na demonstração |

Regra no código: a IA nunca responde ao cliente nem fecha ticket. `auto_route` só sai para Acesso, Armazenamento e Hardware (chaves `Access`, `Storage`, `Hardware` na API) sem sinal de risco e com confiança ≥ limiar (padrão 0,90; seletor 0,80 / 0,90 / 0,95 no Board). `Resolver` é sempre um clique humano. As classes têm chave em inglês na API e rótulo em português na tela.

## Estrutura

```
app/        normalize.py · policy.py (gate, sinais de risco) · drafts.py · model.py · replay.py · board.py (SQLite) · closure.py · api.py
scripts/    train.py (modelo + métricas + figuras) · diagnostico_ds1.py · traduzir_ds2.py (tradução única, dependência opcional)
artifacts/  metrics.json · ds1_metrics.json · policy.json · holdout_pred.csv.gz · figures/*.png   (versionados; regenerados por make train)
models/     index.pkl (21 MB, não versionado; make train)
web/        index.html · style.css · app.js (sem build, sem CDN de JS; Google Fonts com fallback)
tests/      113 testes (política, normalização, métricas, board com TMA por nível, fechamento, API)
deploy/     vps.sh · g4-triagem.service · zz-g4-triagem.conf (Apache + Let's Encrypt)
data/       ds1.zip · ds2.zip · SHA256SUMS · DATA_LICENSE.md · ds2_pt.csv.gz (+ .meta.json)
```

## API

`GET /api/health` · `POST /api/triage {text, threshold?}` · `POST /api/replay/next {n, threshold?}` · `POST /api/tickets/{id}/action {action}` · `GET /api/board` · `POST /api/reset` · `GET /api/metrics` · `GET /api/ds1` · `GET /api/policy` · `GET /api/examples` · `POST /api/closure` · `GET /api/closure/options` · `GET /api/kb/example?ticket_id=`. Documentação interativa em `/docs`.

## Reproduzir os números dos documentos

Todos os números de `solution/diagnostico.md`, `solution/proposta.md` e do README da submissão vêm de `artifacts/metrics.json` e `artifacts/ds1_metrics.json`. `make train` regenera os dois (seed 42, split 80/20 estratificado, desduplicação por 20 primeiras palavras). Se um número divergir, o seed ou a versão do scikit-learn mudou; `uv.lock` fixa as versões usadas.

## Limitações

- O modelo foi treinado em tickets de TI traduzidos automaticamente para pt-BR a partir de texto pré-processado (sem pontuação/stopwords); texto fora desse domínio deve sair com baixa confiança e ir para N2 (é o comportamento desejado). A tradução é telegráfica e mistura formas pt-PT/pt-BR em alguns termos.
- Estado do board em SQLite local (`board.db`), sem autenticação: é um protótipo de demonstração. `POST /api/reset` zera tudo.
- Sem LLM: os rascunhos são macros por classe.
