# Protótipo — Triagem N1-IA / N2 / N3

Um processo Python (FastAPI + página única) que roda o classificador de tickets sobre os **47.837 tickets reais** do Dataset 2 e mostra a triagem N1-IA → N2 → N3 funcionando: board de filas, indicadores, ponto de operação (limiar), política por classe, ticket novo, template de fechamento e a prévia da similaridade após a padronização.

## Rodar em 2 comandos

Requisitos: Python ≥ 3.12 e [`uv`](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`). Mac ou Linux; ~1,5 GB de RAM livre durante o treino.

```bash
make setup   # uv sync + extrai os CSVs (CC0, versionados em data/) e confere os SHA-256
make run     # treina se models/index.pkl não existir (~75 s) e sobe em http://localhost:8010
```

Outros alvos: `make train` (regenera modelo, `artifacts/metrics.json`, `artifacts/ds1_metrics.json` e figuras), `make test` (105 testes), `make clean`.

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
| Texto dos cards, classe prevista **e** verdadeira, confiança, top-3, 3 tickets similares com similaridade | Hora de chegada (replay em lotes), nomes dos responsáveis (rodízio) |
| Cobertura e acerto por limiar e por classe, matriz de confusão, calibração | Minutos de triagem e custo-hora da calculadora (campos editáveis, selo SIMULAÇÃO) |
| Contadores do board: % N1-IA, % N2, % N3, acertos, "IA errou" | Conteúdo dos fechamentos na aba Similaridade (selo EXEMPLO ILUSTRATIVO) |
| Diagnóstico do Dataset 1 (`artifacts/ds1_metrics.json`) | TMA por nível: não existe; card "não mensurável nos datasets" |

Regra no código: a IA nunca responde ao cliente nem fecha ticket. `auto_route` só sai para Access, Storage e Hardware sem sinal de risco e com confiança ≥ limiar (padrão 0,90). `Resolver` é sempre um clique humano.

## Estrutura

```
app/        normalize.py · policy.py (gate, sinais de risco) · drafts.py · model.py · replay.py · board.py (SQLite) · closure.py · api.py
scripts/    train.py (modelo + métricas + figuras) · diagnostico_ds1.py
artifacts/  metrics.json · ds1_metrics.json · policy.json · holdout_pred.csv.gz · figures/*.png   (versionados; regenerados por make train)
models/     index.pkl (21 MB, não versionado; make train)
web/        index.html · style.css · app.js (sem build, sem CDN de JS; Google Fonts com fallback)
tests/      105 testes (política, normalização, métricas, board, fechamento, API)
deploy/     vps.sh · g4-triagem.service · zz-g4-triagem.conf (Apache + Let's Encrypt)
data/       ds1.zip · ds2.zip · SHA256SUMS · DATA_LICENSE.md
```

## API

`GET /api/health` · `POST /api/triage {text, threshold?}` · `POST /api/replay/next {n, threshold?}` · `POST /api/tickets/{id}/action {action}` · `GET /api/board` · `POST /api/reset` · `GET /api/metrics` · `GET /api/ds1` · `GET /api/policy` · `GET /api/examples` · `POST /api/closure` · `GET /api/closure/options` · `GET /api/kb/example?ticket_id=`. Documentação interativa em `/docs`.

## Reproduzir os números dos documentos

Todos os números de `solution/diagnostico.md`, `solution/proposta.md` e do README da submissão vêm de `artifacts/metrics.json` e `artifacts/ds1_metrics.json`. `make train` regenera os dois (seed 42, split 80/20 estratificado, desduplicação por 20 primeiras palavras). Se um número divergir, o seed ou a versão do scikit-learn mudou; `uv.lock` fixa as versões usadas.

## Limitações

- O modelo foi treinado em tickets de TI em inglês, pré-processados; texto fora desse domínio deve sair com baixa confiança e ir para N2 (é o comportamento desejado).
- Estado do board em SQLite local (`board.db`), sem autenticação: é um protótipo de demonstração. `POST /api/reset` zera tudo.
- Sem LLM: os rascunhos são macros por classe.
