# Plano de implementação — Triagem N1-IA / N2 / N3 (Challenge 002)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar em `submissions/hugo-cunha/` um protótipo funcional de triagem de tickets (classificador local + gate de confiança + board N1-IA/N2/N3 + template de fechamento) rodando sobre os 47.837 tickets reais do Dataset 2, mais diagnóstico, proposta, process log e PR.

**Architecture:** Um processo Python (FastAPI + uvicorn) serve a API JSON e uma página única estática. O modelo (TF-IDF + regressão logística + vizinhos por cosseno) é treinado por script e carregado de `models/index.pkl`. O estado do board fica em SQLite (stdlib). Todo número exibido vem de `artifacts/metrics.json` e `artifacts/ds1_metrics.json`, gerados por scripts reproduzíveis.

**Tech Stack:** Python 3.13, uv, scikit-learn, pandas, numpy, scipy, joblib, matplotlib, FastAPI, uvicorn, httpx (testes), pytest; HTML/CSS/JS vanilla.

**Spec:** `submissions/hugo-cunha/docs/2026-09-16-desenho-solucao.md`

## Global Constraints

- Só criar/modificar arquivos dentro de `submissions/hugo-cunha/` (regra do PR do G4).
- O `.gitignore` do repositório ignora `submissions/`: **todo commit usa `git add -f`**.
- Pasta de dados chama-se `data/` (o `.gitignore` do G4 também ignora `datasets/`).
- A IA nunca responde ao cliente nem fecha ticket: nenhuma rota fecha ticket sem ação humana; `decide()` nunca devolve `auto_route` para classe fora de `AUTO` nem com sinal de risco.
- Limiar padrão do gate: `0.90`. `AUTO = {"Access","Storage","Hardware"}`; `SUGGEST = {"Purchase","HR Support","Administrative rights","Internal Project"}`; `Miscellaneous` sempre humano.
- Seed global `42`. Split 80/20 estratificado. Desduplicação por chave = 20 primeiras palavras.
- Nenhuma dependência de LLM, Docker, Node, React ou PHP. Sem chave de API.
- Textos de UI em pt-BR; código, commits e API em inglês.
- Paleta: navy `#001F35`, maua `#031A26`, gold `#B9915B`, silver `#F5F4F3`, gray `#9CA3AF`. Fontes: Manrope (corpo), Libre Baskerville itálica (títulos). Sem logo da G4. Rodapé: "Protótipo de candidatura — não afiliado à G4".
- Root do protótipo: `submissions/hugo-cunha/solution/prototipo/` (abaixo, `PROTO`). Comandos rodam a partir de `PROTO`.
- Commits com mensagem em inglês, prefixo convencional (`feat:`, `test:`, `docs:`), terminando com `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

---

## Estrutura de arquivos

```
submissions/hugo-cunha/
├── README.md                         (T11) template do G4 preenchido
├── docs/                             spec + este plano
├── solution/
│   ├── diagnostico.md                (T10)
│   ├── proposta.md                   (T10)
│   └── prototipo/
│       ├── pyproject.toml, uv.lock, .python-version, Makefile, .gitignore, README.md   (T1, T9)
│       ├── data/ds1.zip, data/ds2.zip, data/DATA_LICENSE.md                          (T1)
│       ├── app/__init__.py
│       ├── app/normalize.py          (T2) normalize(text) -> str
│       ├── app/policy.py             (T3) AUTO, SUGGEST, risk_flags(), decide()
│       ├── app/drafts.py             (T3) draft_for(category, decision) -> str|None
│       ├── app/model.py              (T6) TriageModel
│       ├── app/replay.py             (T6) HoldoutReplay
│       ├── app/board.py              (T6) Board (SQLite)
│       ├── app/closure.py            (T6) validate_closure(), kb_examples()
│       ├── app/api.py                (T7) FastAPI app
│       ├── scripts/train.py          (T4) → models/index.pkl, artifacts/*
│       ├── scripts/diagnostico_ds1.py(T5) → artifacts/ds1_metrics.json + figura
│       ├── artifacts/                (T4, T5) versionados: metrics.json, policy.json, holdout_pred.csv.gz, ds1_metrics.json, figures/*.png
│       ├── models/                   gitignored (index.pkl)
│       ├── web/index.html, web/style.css, web/app.js   (T8)
│       ├── tests/                    (T2–T7)
│       └── deploy/vps.sh, deploy/g4-triagem.service, deploy/zz-g4-triagem.conf   (T13)
└── process-log/prompts.md, PROCESS_LOG.md, evidencias.pdf, screenshots/            (T11)
```

---

### Task 1: Esqueleto, dados, ambiente e primeiro commit

**Files:**
- Create: `PROTO/pyproject.toml`, `PROTO/.python-version`, `PROTO/Makefile`, `PROTO/.gitignore`, `PROTO/app/__init__.py`, `PROTO/data/ds1.zip`, `PROTO/data/ds2.zip`, `PROTO/data/DATA_LICENSE.md`, `PROTO/artifacts/.gitkeep`, `PROTO/tests/__init__.py`

**Interfaces:**
- Produces: layout de pastas; `make setup|data|train|run|test|check-tracked`; `uv.lock` versionado.

- [ ] **Step 1: pyproject.toml**

```toml
[project]
name = "g4-triagem"
version = "0.1.0"
description = "Prototipo de triagem N1-IA / N2 / N3 - G4 AI Master Challenge 002"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "scikit-learn>=1.5",
  "pandas>=2.2",
  "numpy>=1.26",
  "scipy>=1.13",
  "joblib>=1.4",
  "matplotlib>=3.9",
]
[dependency-groups]
dev = ["pytest>=8", "httpx>=0.27"]
[tool.pytest.ini_options]
testpaths = ["tests"]
```

`.python-version` = `3.13`.

- [ ] **Step 2: Makefile** (tabs, não espaços)

```make
.PHONY: setup data train run test replay check-tracked clean
PY=uv run python
setup:
	uv sync --group dev
	$(MAKE) data
data:
	@test -f data/customer_support_tickets.csv || unzip -o -q data/ds1.zip -d data
	@test -f data/all_tickets_processed_improved_v3.csv || unzip -o -q data/ds2.zip -d data
	@shasum -a 256 -c data/SHA256SUMS
train: data
	$(PY) scripts/train.py
	$(PY) scripts/diagnostico_ds1.py
run: data
	@test -f models/index.pkl || $(PY) scripts/train.py
	uv run uvicorn app.api:app --host 0.0.0.0 --port 8010
test:
	uv run pytest -q
check-tracked:
	@n=$$(git ls-files . | wc -l | tr -d ' '); echo "tracked files: $$n"; test $$n -gt 0
clean:
	rm -rf models/*.pkl data/*.csv
```

- [ ] **Step 3: dados** — copiar `~/Desktop/G4/data/raw/ds1.zip` e `ds2.zip` para `PROTO/data/`; gerar `data/SHA256SUMS` com os CSVs extraídos (`shasum -a 256 customer_support_tickets.csv all_tickets_processed_improved_v3.csv > SHA256SUMS`, caminhos relativos a `data/`); `DATA_LICENSE.md` com: fonte Kaggle (URLs), licença CC0, data de download 2026-09-16, linhas 8.469 e 47.837, os dois SHA-256.

- [ ] **Step 4: .gitignore do protótipo**: `models/`, `data/*.csv`, `.venv/`, `__pycache__/`, `*.db`, `.pytest_cache/`.

- [ ] **Step 5: `uv sync --group dev`** gera `uv.lock`; `uv run python -c "import sklearn, fastapi; print('ok')"`.

- [ ] **Step 6: Commit** (`git add -f submissions/hugo-cunha`; mensagem `chore: scaffold submission, data (CC0) and environment`); conferir `git ls-files submissions/hugo-cunha | wc -l` > 0.

---

### Task 2: Normalização de texto

**Files:**
- Create: `PROTO/app/normalize.py`, `PROTO/tests/test_normalize.py`

**Interfaces:**
- Produces: `normalize(text: str) -> str` — minúsculas, remove e-mails/URLs/números longos, pontuação, stopwords (lista curta EN+PT embutida), colapsa espaços. Idempotente: `normalize(normalize(x)) == normalize(x)`.

- [ ] **Step 1: teste**

```python
from app.normalize import normalize
def test_lowercase_and_punct():
    assert normalize("Hello, WORLD! Printer 2 is DOWN.") == "hello world printer down"
def test_removes_email_url_numbers():
    out = normalize("contact joao@x.com http://a.b 123456 ticket")
    assert "joao" not in out and "http" not in out and "123456" not in out
def test_idempotent():
    s = "The VPN is not connecting, please help!!"
    assert normalize(normalize(s)) == normalize(s)
def test_keeps_domain_words():
    assert "vpn" in normalize("The VPN is not connecting")
```

- [ ] **Step 2: rodar** `uv run pytest tests/test_normalize.py -v` → FAIL (módulo inexistente).
- [ ] **Step 3: implementar**

```python
import re
STOP = set("""a an the and or of to in on at for with is are was were be been being i you he she it we they
me my your our their this that these those please hi hello dear thanks thank regards kind best team
o a os as um uma de do da dos das e ou em no na nos nas por para com sem que se eu você ele ela nós eles
oi olá obrigado obrigada atenciosamente prezado prezada""".split())
_EMAIL = re.compile(r"\S+@\S+")
_URL = re.compile(r"https?://\S+|www\.\S+")
_NUM = re.compile(r"\b\d{3,}\b")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
def normalize(text: str) -> str:
    t = (text or "").lower()
    t = _EMAIL.sub(" ", t); t = _URL.sub(" ", t); t = _NUM.sub(" ", t)
    t = _PUNCT.sub(" ", t).replace("_", " ")
    toks = [w for w in t.split() if w not in STOP and not w.isdigit()]
    return " ".join(toks)
```

- [ ] **Step 4: rodar** → PASS. **Step 5: Commit** `feat: text normalization shared by training and API`.

---

### Task 3: Política de decisão e rascunhos

**Files:**
- Create: `PROTO/app/policy.py`, `PROTO/app/drafts.py`, `PROTO/tests/test_policy.py`

**Interfaces:**
- Produces:
  - `AUTO: frozenset[str]`, `SUGGEST: frozenset[str]`, `CLASSES: list[str]` (8 classes, ordem alfabética), `DEFAULT_THRESHOLD = 0.90`
  - `risk_flags(text: str) -> list[str]` — nomes em `{"legal","cancel","refund","harassment","health","vip","social","reopened"}`
  - `Decision` (dataclass): `decision: str` (`auto_route|suggest|human_triage|human_required`), `level: str` (`N1|N2`), `queue: str`, `reason: str`
  - `decide(category: str, confidence: float, flags: list[str], threshold: float = DEFAULT_THRESHOLD) -> Decision`
  - `policy_table() -> list[dict]` — por classe: `{category, action, reason}`
  - `drafts.draft_for(category: str, decision: str) -> str | None` — texto pt-BR só quando `decision == "auto_route"`.

- [ ] **Step 1: testes**

```python
import pytest
from app.policy import decide, risk_flags, AUTO, SUGGEST, CLASSES
from app.drafts import draft_for
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
```

- [ ] **Step 2: rodar** → FAIL. **Step 3: implementar `policy.py`**

```python
import re
from dataclasses import dataclass, asdict
CLASSES = sorted(["Access","Administrative rights","HR Support","Hardware","Internal Project","Miscellaneous","Purchase","Storage"])
AUTO = frozenset({"Access","Storage","Hardware"})
SUGGEST = frozenset({"Purchase","HR Support","Administrative rights","Internal Project"})
DEFAULT_THRESHOLD = 0.90
RISK_PATTERNS = {
  "legal": r"\b(lawsuit|legal action|lawyer|attorney|procon|court|jur[ií]dic\w*|advogad\w*|processo judicial)\b",
  "cancel": r"\b(cancel\w*)\b",
  "refund": r"\b(refund\w*|reembols\w*|estorno|chargeback)\b",
  "harassment": r"\b(harass\w*|threat\w*|abus\w*|ass[eé]dio|amea[çc]\w*)\b",
  "health": r"\b(hospital|medical emergency|death|died|morte|faleceu|emerg[êe]ncia m[ée]dica)\b",
  "vip": r"\b(vip|enterprise account|ceo|diretor executivo)\b",
  "social": r"\b(twitter|facebook|instagram|linkedin|social media|rede social)\b",
  "reopened": r"\b(reopen\w*|reabert\w*)\b",
}
_COMPILED = {k: re.compile(v, re.IGNORECASE) for k, v in RISK_PATTERNS.items()}
REASONS = {
  "Access": "pedido repetitivo e de alta precisão; rotear não concede acesso",
  "Storage": "melhor precisão entre as classes; aumento de cota é decisão do N2",
  "Hardware": "troubleshooting padronizável; classe que absorve confusões, primeira a ter kill switch",
  "Purchase": "envolve dinheiro e aprovação: N2 confirma a fila",
  "HR Support": "envolve pessoas: nunca rascunho automático",
  "Administrative rights": "elevação de privilégio é segurança e o modelo erra 31% da classe",
  "Internal Project": "não é suporte; vai ao PMO com confirmação",
  "Miscellaneous": "classe 'não sei' por definição: sempre humano",
}
@dataclass
class Decision:
    decision: str; level: str; queue: str; reason: str
    def to_dict(self): return asdict(self)
def risk_flags(text: str) -> list[str]:
    t = text or ""
    return [k for k, rx in _COMPILED.items() if rx.search(t)]
def decide(category, confidence, flags, threshold=DEFAULT_THRESHOLD) -> Decision:
    if flags:
        return Decision("human_required", "N2", "N2-humano-obrigatorio", "sinal de risco: " + ", ".join(flags))
    if category == "Miscellaneous" or confidence < threshold:
        why = "classe Miscellaneous" if category == "Miscellaneous" else f"confiança {confidence:.2f} abaixo do limiar {threshold:.2f}"
        return Decision("human_triage", "N2", "N2-triagem", why)
    if category in AUTO:
        return Decision("auto_route", "N1", category, f"confiança {confidence:.2f} ≥ {threshold:.2f} e classe auto-roteável: {REASONS[category]}")
    return Decision("suggest", "N2", category, f"confiança {confidence:.2f} ≥ {threshold:.2f}, mas {REASONS[category]}")
def policy_table() -> list[dict]:
    rows = []
    for c in CLASSES:
        action = "auto-roteio com rascunho" if c in AUTO else ("sugerir fila" if c in SUGGEST else "sempre humano")
        rows.append({"category": c, "action": action, "reason": REASONS[c]})
    return rows
```

`drafts.py`: dicionário `DRAFTS` com um texto pt-BR por classe de `AUTO` (Access: confirmar sistema, gestor aprovador e prazo; Storage: passos para liberar espaço e como pedir cota; Hardware: coleta de modelo/patrimônio, reinício, status da última atualização). `draft_for` devolve `DRAFTS.get(category)` se `decision == "auto_route"`, senão `None`.

- [ ] **Step 4: rodar** → PASS. **Step 5: Commit** `feat: decision policy, risk flags and per-class drafts`.

---

### Task 4: Treino, hold-out, métricas e artefatos (Dataset 2)

**Files:**
- Create: `PROTO/scripts/train.py`, `PROTO/tests/test_metrics.py`
- Produces: `models/index.pkl`, `artifacts/metrics.json`, `artifacts/policy.json`, `artifacts/holdout_pred.csv.gz`, `artifacts/figures/{confusion.png,coverage_accuracy.png,reliability.png,similarity_curve.png}`.

**Interfaces:**
- `index.pkl` = dict: `{"vectorizer": TfidfVectorizer, "clf": LogisticRegression, "X_train": csr float32, "train_ids": np.ndarray[int], "train_texts": list[str], "train_labels": np.ndarray[str], "classes": list[str], "config": dict, "trained_at": iso str}`
- `holdout_pred.csv.gz` colunas: `id, text, true_category, pred_category, confidence, top3_json, nn_ids_json, nn_sims_json`
- `metrics.json` chaves: `generated_at, config, n_total, n_dedup_removed, n_train, n_holdout, accuracy, macro_f1, ece, per_class{cls:{precision,recall,f1,support}}, confusion{labels,matrix}, thresholds[{t,coverage,n_covered,acc_covered,n_errors_covered,acc_rest,useful_coverage,useful_acc}] (t de 0.50 a 0.99 passo 0.01), per_class_at{"0.80"|"0.90"|"0.95":{cls:{coverage,acc,n}}}, similarity{nn_accuracy, bins[{min_sim,coverage,nn_agreement}]}, cv5{accuracy,macro_f1} (opcional, só se < 90 s)`

- [ ] **Step 1: teste (lê artefatos; roda depois do treino)**

```python
import json, pathlib, pytest
ART = pathlib.Path(__file__).resolve().parents[1] / "artifacts"
@pytest.fixture(scope="module")
def m():
    p = ART / "metrics.json"
    if not p.exists(): pytest.skip("run make train first")
    return json.loads(p.read_text())
def test_accuracy_floor(m): assert m["accuracy"] >= 0.85 and m["macro_f1"] >= 0.84
def test_thresholds_monotonic(m):
    cov = [r["coverage"] for r in m["thresholds"]]
    assert all(a >= b for a, b in zip(cov, cov[1:]))
    row = next(r for r in m["thresholds"] if abs(r["t"] - 0.90) < 1e-9)
    assert row["acc_covered"] >= 0.97 and row["useful_coverage"] >= 0.25
def test_eight_classes(m): assert len(m["per_class"]) == 8
```

- [ ] **Step 2: implementar `train.py`** (pontos obrigatórios):
  1. Ler `data/all_tickets_processed_improved_v3.csv`; `key = " ".join(Document.split()[:20])`; `drop_duplicates(subset=key)`; registrar `n_dedup_removed`.
  2. `train_test_split(test_size=0.2, stratify=y, random_state=42)`; salvar ids.
  3. `TfidfVectorizer(ngram_range=(1,2), min_df=2, sublinear_tf=True, max_features=300000, dtype=np.float32)`; `LogisticRegression(C=5, max_iter=2000, n_jobs=1)`.
  4. Predições no hold-out: `proba`, `pred`, `confidence = proba.max(1)`, `top3`.
  5. Vizinhos: `X_train` normalizado L2 (TF-IDF já é L2); `sims = X_holdout @ X_train.T` em blocos de 2.000 linhas; top-3 por linha (`argpartition`); guardar ids e sims. Curva de similaridade: para bins `[0.3,0.4,...,0.9,0.95,0.99]`: cobertura (fração com sim1 ≥ bin) e concordância (label do 1-NN == verdadeiro); `nn_accuracy` global.
  6. Métricas: `accuracy_score`, `f1_score(average="macro")`, `classification_report(output_dict=True)`, `confusion_matrix(labels=CLASSES)`; ECE com 10 bins.
  7. Thresholds: para `t` em `np.round(np.arange(0.50, 1.00, 0.01), 2)`: `covered = confidence >= t`; `useful = covered & isin(pred, AUTO) & ~has_risk` onde `has_risk = [bool(risk_flags(txt)) for txt in text]` (importar `app.policy`); registrar contagens e acurácias (acurácia = pred == true).
  8. `per_class_at` para 0.80/0.90/0.95: por classe prevista: cobertura e acurácia dentro da classe.
  9. Figuras com matplotlib (Agg): matriz de confusão normalizada por linha; curva cobertura × acurácia (duas séries: bruta e útil); diagrama de confiabilidade; curva de similaridade.
  10. Salvar `policy.json` = `policy_table()`; salvar pickle com `joblib.dump(..., compress=3)`; imprimir resumo.
  11. `sys.path.insert(0, PROTO)` no topo para importar `app`.

- [ ] **Step 3: rodar** `uv run python scripts/train.py` (< 2 min) e `uv run pytest tests/test_metrics.py -v` → PASS. Anotar acurácia e cobertura útil em 0,90 no commit.
- [ ] **Step 4: Commit** `feat: train pipeline, holdout replay data and metrics artifacts` (artefatos versionados; `models/` não).

---

### Task 5: Diagnóstico do Dataset 1

**Files:**
- Create: `PROTO/scripts/diagnostico_ds1.py`, `PROTO/tests/test_ds1.py`
- Produces: `artifacts/ds1_metrics.json`, `artifacts/figures/ds1_time_window.png`

**Interfaces:** `ds1_metrics.json` chaves: `n_rows, placeholder_share, first_sentence_distinct, resolution_unique, resolution_avg_words, example_com_share, time_window_hours, share_negative_resolution, status_counts, naive_table[{dimension, value, n, csat_mean, naive_hours_mean}], association_tests[{variable, test, p_value}], negative_control{accuracy, majority_share}, verdict` (string pt-BR).

- [ ] **Step 1: teste**

```python
import json, pathlib, pytest
ART = pathlib.Path(__file__).resolve().parents[1] / "artifacts"
def test_ds1_metrics_exist_and_are_noise():
    p = ART / "ds1_metrics.json"
    if not p.exists(): pytest.skip("run make train first")
    m = json.loads(p.read_text())
    assert m["n_rows"] == 8469 and m["placeholder_share"] > 0.99
    assert 0.45 < m["share_negative_resolution"] < 0.55
    assert all(t["p_value"] > 0.05 for t in m["association_tests"] if t["variable"] != "frt_hour")
    assert m["negative_control"]["accuracy"] < 0.30
```

- [ ] **Step 2: implementar** — reproduzir as medições de `notas/fatos-datasets.md`: placeholder, 16 primeiras frases, resoluções únicas, e-mails example.com, janela de tempo (max−min de FRT/TTR em horas), share de `TTR < FRT`, `status_counts`, tabela ingênua por `Ticket Channel`, `Ticket Priority`, `Ticket Type` (n, média de CSAT nos fechados, "horas" ingênuas = média de `(TTR−FRT)` em horas), testes Kruskal e qui-quadrado (scipy) de CSAT vs canal/prioridade/tipo/gênero/produto/assunto e Spearman de idade e hora da FRT; controle negativo = 5-fold `cross_val_score` de TF-IDF+LogReg em `Ticket Description → Ticket Type` (esperado ≈ 0,20; majoritária = 1752/8469); figura: histograma de `(TTR−FRT)` em horas com linha em zero. `verdict` = "As diferenças entre canais, prioridades e tipos cabem no ruído; tempo de resolução não é mensurável neste arquivo."
- [ ] **Step 3: rodar e testar** → PASS. **Step 4: Commit** `feat: dataset 1 diagnostic script with naive table and noise evidence`.

---

### Task 6: Modelo em runtime, replay, board e fechamento

**Files:**
- Create: `PROTO/app/model.py`, `PROTO/app/replay.py`, `PROTO/app/board.py`, `PROTO/app/closure.py`, `PROTO/tests/test_model.py`, `PROTO/tests/test_board.py`, `PROTO/tests/test_closure.py`

**Interfaces:**
- `TriageModel.load(path="models/index.pkl") -> TriageModel`; `.predict(text: str, k: int = 3) -> dict` = `{category, confidence, top3:[{category,p}], neighbors:[{id, excerpt(≤160 chars), category, similarity}]}` (aplica `normalize` no texto; usa `vectorizer.transform`, `clf.predict_proba`, `X_train @ x.T`); `.neighbors_by_ids(ids, sims) -> list[dict]`; `.n_train`; `.classes`.
- `HoldoutReplay(csv_path, seed=42)`: `.next(n) -> list[dict]` (linhas de `holdout_pred` em ordem embaralhada com seed; volta ao início no fim); `.reset()`; `.total`; `.position`.
- `Board(db_path=":memory:" ou arquivo)`: `.add(ticket: dict) -> dict`; `.action(ticket_id: str, action: str) -> dict` (`assume`: `assigned_to` = próximo de `["Ana","Bruno","Carla","Diego"]` se vazio, status `em_atendimento`; `resolve`: status `resolvido`, `resolved_at`; `escalate`: `level="N3"`, `queue="N3-especialista"`; `ai_wrong`: `ai_wrong=1`, se `level=="N1"` move para `N2-triagem`); `.snapshot() -> {N1:[...], N2:[...], N3:[...], resolved:int, counters:{total, n1, n2, n3, resolved, ai_wrong, ai_correct, ai_evaluated, by_decision:{...}}}`; `.reset()`; limite 2.000 linhas (apaga os mais antigos resolvidos). Ticket dict: `id, text, true_category, category, confidence, top3, neighbors, risk_flags, decision, level, queue, reason, draft, assigned_to, status, created_at, ai_wrong`.
- `closure.REQUIRED = ["category","subcategory","root_cause","resolution_steps","resolved_by_level","time_spent_min","reusable","reopened"]`; `validate_closure(payload: dict) -> list[str]` (erros pt-BR; `resolution_steps` ≥ 20 chars; `category` ∈ CLASSES; `resolved_by_level` ∈ {N1-IA,N2,N3}; `time_spent_min` > 0); `SUBCATEGORIES: dict[str, list[str]]` (3–5 por classe); `kb_examples(category: str) -> dict` com campos ilustrativos por classe e `illustrative: True`.

- [ ] **Step 1: testes**

```python
# tests/test_board.py
from app.board import Board
def _t(i, level="N1", decision="auto_route"):
    return {"id": f"t{i}", "text": "x", "true_category": "Access", "category": "Access", "confidence": 0.95,
            "top3": [], "neighbors": [], "risk_flags": [], "decision": decision, "level": level,
            "queue": "Access", "reason": "r", "draft": "d"}
def test_add_and_snapshot():
    b = Board(":memory:"); b.add(_t(1)); s = b.snapshot()
    assert len(s["N1"]) == 1 and s["counters"]["total"] == 1 and s["counters"]["ai_correct"] == 1
def test_escalate_moves_to_n3():
    b = Board(":memory:"); b.add(_t(1, "N2", "suggest")); b.action("t1", "escalate")
    assert b.snapshot()["N3"][0]["id"] == "t1"
def test_ai_wrong_moves_n1_to_n2():
    b = Board(":memory:"); b.add(_t(1)); b.action("t1", "ai_wrong"); s = b.snapshot()
    assert s["N1"] == [] and s["N2"][0]["queue"] == "N2-triagem" and s["counters"]["ai_wrong"] == 1
def test_resolve_counts():
    b = Board(":memory:"); b.add(_t(1)); b.action("t1", "resolve")
    assert b.snapshot()["resolved"] == 1
# tests/test_closure.py
from app.closure import validate_closure, REQUIRED
def test_missing_required_lists_errors():
    errs = validate_closure({})
    assert len(errs) >= len(REQUIRED)
def test_valid_payload():
    ok = {"category": "Access", "subcategory": "Novo acesso", "root_cause": "Conta fora do grupo",
          "resolution_steps": "Adicionado ao grupo AD apos aprovacao do gestor", "resolved_by_level": "N2",
          "time_spent_min": 12, "reusable": True, "reopened": False}
    assert validate_closure(ok) == []
# tests/test_model.py
import pathlib, pytest
from app.model import TriageModel
@pytest.fixture(scope="module")
def model():
    p = pathlib.Path("models/index.pkl")
    if not p.exists(): pytest.skip("run make train first")
    return TriageModel.load(str(p))
def test_predict_shape(model):
    r = model.predict("printer not working after windows update")
    assert r["category"] in model.classes and 0 <= r["confidence"] <= 1 and len(r["neighbors"]) == 3
```

- [ ] **Step 2: rodar** → FAIL. **Step 3: implementar** os quatro módulos conforme as interfaces (SQLite: tabela `tickets` com colunas JSON para `top3/neighbors/risk_flags`, `PRAGMA journal_mode=WAL`, `check_same_thread=False`, lock `threading.Lock`).
- [ ] **Step 4: rodar** `uv run pytest -q` → PASS. **Step 5: Commit** `feat: runtime model, holdout replay, board store and closure template`.

---

### Task 7: API FastAPI

**Files:**
- Create: `PROTO/app/api.py`, `PROTO/tests/test_api.py`

**Interfaces (contrato final; a UI depende disto):**
- `GET /api/health` → `{status:"ok", model_loaded:bool, n_train:int, n_holdout:int, version:"0.1.0", llm_enabled:false}`
- `POST /api/triage` body `{text:str, threshold?:float}` → `{category, confidence, top3, neighbors, risk_flags, decision, level, queue, reason, draft}`
- `POST /api/replay/next` body `{n?:int=10, threshold?:float}` → `{tickets:[Ticket], position:int, total:int}` — cada ticket passa por `decide()` com o limiar recebido e é adicionado ao board
- `POST /api/tickets/{id}/action` body `{action}` → `Ticket` (404 se não existe, 400 se ação inválida)
- `GET /api/board` → snapshot; `POST /api/reset` → `{ok:true}` (reseta board e replay)
- `GET /api/metrics` → `metrics.json`; `GET /api/ds1` → `ds1_metrics.json`; `GET /api/policy` → `policy.json`
- `GET /api/examples` → `{examples:[{id,text,true_category}]}` (3 ids fixos: posições 0, 1, 2 do replay com seed 7)
- `POST /api/closure` body = campos do template → `{ok:bool, errors:[str], kb_entry:dict|null}`
- `GET /api/kb/example?ticket_id=` → `{ticket:{id,text,category}, similar:[{id, excerpt, category, similarity, closure:{...illustrative}}], illustrative:true, note:str}`
- `GET /` serve `web/index.html`; `/static/*` serve `web/`.
- Estado: `Board("board.db")` e `HoldoutReplay("artifacts/holdout_pred.csv.gz")` criados no startup (lifespan); modelo carregado no startup (se `models/index.pkl` faltar, `model_loaded=false` e `/api/triage` devolve 503).

- [ ] **Step 1: testes**

```python
import pathlib, pytest
from fastapi.testclient import TestClient
from app.api import app
@pytest.fixture(scope="module")
def client():
    if not pathlib.Path("models/index.pkl").exists(): pytest.skip("run make train first")
    with TestClient(app) as c: yield c
def test_health(client):
    r = client.get("/api/health"); assert r.status_code == 200 and r.json()["model_loaded"] is True
def test_triage_contract(client):
    r = client.post("/api/triage", json={"text": "quero cancelar e pedir reembolso"}); j = r.json()
    assert j["decision"] == "human_required" and j["draft"] is None and "refund" in j["risk_flags"]
def test_replay_adds_to_board(client):
    client.post("/api/reset")
    r = client.post("/api/replay/next", json={"n": 10}); assert len(r.json()["tickets"]) == 10
    s = client.get("/api/board").json(); assert s["counters"]["total"] == 10
    t = r.json()["tickets"][0]; a = client.post(f"/api/tickets/{t['id']}/action", json={"action": "resolve"})
    assert a.status_code == 200 and client.get("/api/board").json()["resolved"] == 1
def test_no_auto_route_for_suggest_classes(client):
    client.post("/api/reset"); ts = client.post("/api/replay/next", json={"n": 200}).json()["tickets"]
    for t in ts:
        if t["decision"] == "auto_route": assert t["category"] in {"Access","Storage","Hardware"} and not t["risk_flags"]
def test_closure_validation(client):
    r = client.post("/api/closure", json={}); assert r.json()["ok"] is False and r.json()["errors"]
```

- [ ] **Step 2: rodar** → FAIL. **Step 3: implementar `api.py`** (pydantic models para bodies; `StaticFiles`; `lifespan`; ticket id no replay = `f"h{row.id}"`; `threshold` validado em [0.5, 0.99]).
- [ ] **Step 4: rodar** `uv run pytest -q` → PASS; `uv run uvicorn app.api:app --port 8010` e `curl localhost:8010/api/health`.
- [ ] **Step 5: Commit** `feat: FastAPI service with triage, replay, board, closure and kb endpoints`.

---

### Task 8: Página única (web/)

**Files:**
- Create: `PROTO/web/index.html`, `PROTO/web/style.css`, `PROTO/web/app.js`

**Interfaces:** Consome exatamente os endpoints da Task 7. Sem build, sem CDN de JS. Google Fonts via `<link>` com fallback `system-ui`.

- [ ] **Step 1: estrutura do `index.html`** — `<header>` navy com título "Triagem N1-IA / N2 / N3" e subtítulo "Protótipo · Challenge 002 · dados reais do hold-out"; `<nav>` com 7 abas (`data-tab`): `painel`, `board`, `operacao`, `politica`, `novo`, `fechamento`, `similaridade`; uma `<section>` por aba; `<footer>` com "Protótipo de candidatura — não afiliado à G4 · LLM desligado: rascunhos por macro". Selos: `.badge-real` ("REAL"), `.badge-sim` ("SIMULAÇÃO"), `.badge-ilustrativo` ("EXEMPLO ILUSTRATIVO").
- [ ] **Step 2: `style.css`** — tokens em `:root` (`--navy:#001F35; --maua:#031A26; --gold:#B9915B; --silver:#F5F4F3; --gray:#9CA3AF; --ok:#2E7D32; --warn:#C77700; --danger:#B3261E`), `body{font-family:Manrope,system-ui}` e `h1,h2{font-family:"Libre Baskerville",serif;font-style:italic;color:var(--gold)}`, grid do board `grid-template-columns:repeat(3,1fr)` com `@media (max-width:768px){grid-template-columns:1fr}`, cards com borda esquerda por decisão (`auto_route` verde, `suggest` dourado, `human_triage` cinza, `human_required` vermelho), tabelas roláveis em `overflow-x:auto`.
- [ ] **Step 3: `app.js`** — funções: `api(path, opts)`; `loadMetrics()` (guarda `metrics`, `policy`, `ds1`); `renderPainel()` (contadores do `/api/board`, cards fixos "TMA real: não mensurável" com os números de `ds1` e "controle negativo"); `renderBoard()` (3 colunas, máx. 30 cards por coluna, botões com `data-action`, contador de resolvidos); `replayNext(n)`; `toggleAuto()` (`setInterval` 3 s); `resetAll()`; `renderOperacao()` (slider `input[type=range]` 0.50–0.99 passo 0.01 lendo `metrics.thresholds`; mostra cobertura bruta/útil/acurácia/erros e calculadora: `tickets_mes=2500` × cobertura útil × `min_triagem` (default 3) / 60 × `custo_hora` (default 41) com selo SIMULAÇÃO e campos editáveis); `renderPolitica()` (tabela `policy` + `metrics.per_class_at["0.90"]`); `submitNovo()` (`POST /api/triage`, mostra decisão, motivo, top-3, vizinhos, rascunho; 3 botões de exemplo vindos de `/api/examples`; aviso de domínio); `submitFechamento()` (`POST /api/closure`, lista erros em vermelho ou mostra `kb_entry`); `renderSimilaridade()` (`GET /api/kb/example?ticket_id=` do primeiro exemplo; cards com similaridade REAL e fechamento ILUSTRATIVO; botão "Aplicar tratativa sugerida" desabilitado com tooltip "requer similaridade ≥ 0,90, classe auto-roteável e base padronizada"). O limiar do slider também é enviado em `replay/next` para que o board reflita a escolha.
- [ ] **Step 4: verificar no navegador** (`make run` + preview em 1280 px e 375 px): sem erros de console; replay adiciona cards; ações movem cards; slider muda números; formulário valida; abas funcionam por teclado. Capturar screenshots em `process-log/screenshots/`.
- [ ] **Step 5: Commit** `feat: single-page UI with board, operating point, policy, closure template and similarity preview`.

---

### Task 9: Prova de setup em clone limpo e README do protótipo

- [ ] `PROTO/README.md`: requisitos (Python ≥ 3.12, uv), `make setup && make run`, fallback sem uv (`python3 -m venv .venv && .venv/bin/pip install -e . && ...`), portas, o que é real vs simulado, como regenerar métricas, como rodar testes.
- [ ] Clone limpo: `git clone -b submission/hugo-cunha https://github.com/StartIACode/ai-master-challenge /tmp/g4check && cd /tmp/g4check/submissions/hugo-cunha/solution/prototipo && time (make setup && make train && make test)`; registrar tempos no README.
- [ ] Commit `docs: prototype README with setup proof`.

### Task 10: `solution/diagnostico.md` e `solution/proposta.md`
- [ ] `diagnostico.md` (≤ 2 páginas): 1 parágrafo do que os dados permitem; tabela ingênua (de `ds1_metrics.json`) + veredito; 3 evidências; o que exportar do helpdesk para medir em 2 semanas; o que o Dataset 2 mostra (mix, onde o classificador erra, quanto custa o erro); controle negativo.
- [ ] `proposta.md` (≤ 3 páginas): fluxo N1-IA/N2/N3 (figura em Mermaid ou PNG), gate e limiar explicado, política por classe com exemplos reais onde o modelo erra, template de fechamento e retro-padronização, similaridade hoje vs depois, fases de adoção, KPIs, custo de API (tabela de 3 linhas) e ROI paramétrico com 3 cenários, o que NÃO automatizar, limitações.
- [ ] Commit `docs: diagnostic and automation proposal`.

### Task 11: README da submissão, process log e PDF
- [ ] `submissions/hugo-cunha/README.md` no template do G4 (Sobre mim, Executive summary, Abordagem, Resultados com screenshots e link do protótipo, Recomendações priorizadas, Limitações, Process Log com ferramentas/workflow/onde a IA errou/o que o humano adicionou, Evidências).
- [ ] `process-log/prompts.md` (cópia literal de `~/Desktop/G4/evidencias/prompts.md`), `process-log/PROCESS_LOG.md` (tabela cronológica, iterações, tempo por fase), `process-log/evidencias.pdf` (gerado com reportlab ou via HTML → PDF com Chrome headless), screenshots.
- [ ] Commit `docs: submission README, process log and evidence PDF`.

### Task 12: PR
- [ ] `git push -u fork submission/hugo-cunha`; `gh pr create --repo Gestao-Quatro-Ponto-Zero/ai-master-challenge --head StartIACode:submission/hugo-cunha --base main --title "[Submission] Hugo Cunha — Challenge 002"`; conferir "Files changed" só em `submissions/hugo-cunha/`; registrar URL no process log.

### Task 13: VPS (último)
- [ ] `deploy/vps.sh` (idempotente): cria `/opt/g4-triagem`, instala uv, copia repo (`rsync` da pasta do protótipo sem `models/`), copia `models/index.pkl` treinado no Mac, `uv sync --no-dev`, instala `deploy/g4-triagem.service` (`User=www-data`, `WorkingDirectory=/opt/g4-triagem`, `ExecStart=/opt/g4-triagem/.venv/bin/uvicorn app.api:app --host 127.0.0.1 --port 8010 --workers 1`, `MemoryMax=512M`, `Restart=on-failure`), vhost `deploy/zz-g4-triagem.conf` (porta 80 com Alias ACME + redirect; 443 com `ProxyPass / http://127.0.0.1:8010/`), `certbot certonly --webroot -w /var/www/html -d g4-triagem.187-77-249-237.sslip.io`, `apache2ctl -S` conferindo default, `curl -I https://g4-triagem.187-77-249-237.sslip.io/api/health`.
- [ ] Link no README e commit `docs: public prototype URL`.
