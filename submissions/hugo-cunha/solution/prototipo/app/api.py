"""FastAPI service: triage, hold-out replay, board, closure template and KB preview.

One process serves the JSON API and the static single page in ``web/``. All state is
created in the lifespan: the model (``models/index.pkl``), the replay
(``artifacts/holdout_pred.csv.gz``), the board (SQLite file ``board.db`` in the
prototype root) and the JSON artifacts served as-is (``metrics.json``,
``ds1_metrics.json``, ``policy.json``).

Contract (docs/2026-09-16-plano-implementacao.md, Task 7); the UI is built against it:

    GET  /api/health                      {status, model_loaded, n_train, n_holdout, version, llm_enabled}
    POST /api/triage        {text, threshold?}   -> {category, confidence, top3, neighbors, risk_flags,
                                                     decision, level, queue, reason, draft}
    POST /api/replay/next   {n?=10, threshold?}  -> {tickets:[Ticket], position, total}
    POST /api/tickets/{id}/action  {action}      -> Ticket   (404 unknown id, 400 invalid action)
    GET  /api/board                              -> {N1, N2, N3, resolved, counters}
    POST /api/reset                              -> {ok:true}   (board + replay cursor)
    GET  /api/metrics | /api/ds1 | /api/policy   -> artifact JSON
    GET  /api/examples                           -> {examples:[{id, text, true_category}]}
    POST /api/closure       template fields      -> {ok, errors, kb_entry}
    GET  /api/kb/example?ticket_id=              -> {ticket, similar:[...closure], illustrative, note}
    GET  /api/closure/options                    -> lists for the closure form (extra, not in the plan)
    GET  /                                       -> web/index.html;  /static/* -> web/

Invariants the API upholds: the AI never answers the customer nor closes a ticket.
``resolve`` is a human action on the board; ``/api/triage`` only classifies, routes
and prepares a draft (macro; no LLM).
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from importlib import metadata
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from app.board import ACTIONS, Board
from app.closure import ILLUSTRATIVE_NOTE, build_kb_entry, closure_options, kb_examples, validate_closure
from app.drafts import draft_for
from app.model import TriageModel
from app.policy import AUTO, SUGGEST, DEFAULT_THRESHOLD, decide, risk_flags
from app.replay import HoldoutReplay

log = logging.getLogger("g4.api")

PROTO = Path(__file__).resolve().parents[1]
INDEX_PKL = PROTO / "models" / "index.pkl"
HOLDOUT_CSV = PROTO / "artifacts" / "holdout_pred.csv.gz"
METRICS_JSON = PROTO / "artifacts" / "metrics.json"
DS1_JSON = PROTO / "artifacts" / "ds1_metrics.json"
POLICY_JSON = PROTO / "artifacts" / "policy.json"
BOARD_DB = PROTO / "board.db"  # override with G4_BOARD_DB (tests use ":memory:")
WEB_DIR = PROTO / "web"
INDEX_HTML = WEB_DIR / "index.html"

REPLAY_SEED = 42
EXAMPLES_SEED = 7
N_EXAMPLES = 3
THRESHOLD_MIN, THRESHOLD_MAX = 0.5, 0.99


def _version() -> str:
    try:
        return metadata.version("g4-triagem")
    except metadata.PackageNotFoundError:
        return "0.1.0"


VERSION = _version()


def _read_json(path: Path) -> Any | None:
    if not path.exists():
        log.warning("artifact missing: %s", path)
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- bodies
class TriageBody(BaseModel):
    text: str = Field(..., max_length=20_000, description="Ticket text (free text; normalized server-side)")
    threshold: float | None = Field(None, ge=THRESHOLD_MIN, le=THRESHOLD_MAX)

    @field_validator("text")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("text must not be blank")
        return v


class ReplayBody(BaseModel):
    n: int = Field(10, ge=1, le=500)
    threshold: float | None = Field(None, ge=THRESHOLD_MIN, le=THRESHOLD_MAX)


class ActionBody(BaseModel):
    action: str



def _pick_examples(replay: HoldoutReplay) -> list[dict]:
    """Three representative hold-out tickets for the demo, chosen deterministically (seed EXAMPLES_SEED):
    (1) an auto-routable class with high confidence and useful neighbors, (2) a 'suggest' class with high
    confidence, (3) a low-confidence ticket that goes to human triage. Falls back to the first N rows."""
    order = replay.sample(replay.total, seed=EXAMPLES_SEED)
    picks: list[dict] = []
    wanted = [
        lambda r: r["pred_category"] in AUTO and r["confidence"] >= 0.95 and r["pred_category"] == r["true_category"]
        and r["nn_sims"] and r["nn_sims"][0] >= 0.5 and len(r["text"].split()) >= 12,
        lambda r: r["pred_category"] in SUGGEST and r["confidence"] >= 0.90 and len(r["text"].split()) >= 12,
        lambda r: r["confidence"] < 0.80 and len(r["text"].split()) >= 12,
    ]
    for cond in wanted:
        for r in order:
            if cond(r) and all(r["id"] != q["id"] for q in picks):
                picks.append(r)
                break
    if len(picks) < N_EXAMPLES:
        for r in order:
            if all(r["id"] != q["id"] for q in picks):
                picks.append(r)
            if len(picks) >= N_EXAMPLES:
                break
    return picks[:N_EXAMPLES]

# --------------------------------------------------------------------------- lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    st = app.state
    st.model = None
    try:
        st.model = TriageModel.load(INDEX_PKL)
        log.info("model loaded: %d training tickets, %d features", st.model.n_train, st.model.n_features)
    except FileNotFoundError as exc:
        log.warning("%s -> /api/triage will answer 503", exc)
    st.replay = None
    try:
        st.replay = HoldoutReplay(HOLDOUT_CSV, seed=REPLAY_SEED)
    except FileNotFoundError as exc:
        log.warning("%s -> replay endpoints will answer 503", exc)
    st.board = Board(os.environ.get("G4_BOARD_DB") or BOARD_DB)
    st.metrics = _read_json(METRICS_JSON)
    st.ds1 = _read_json(DS1_JSON)
    st.policy = _read_json(POLICY_JSON)
    st.examples = _pick_examples(st.replay) if st.replay else []
    try:
        yield
    finally:
        st.board.close()


app = FastAPI(
    title="G4 Triagem N1-IA / N2 / N3",
    version=VERSION,
    description="Protótipo de candidatura — não afiliado à G4. A IA classifica, prioriza e roteia; humano responde e fecha.",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=str(WEB_DIR), check_dir=False), name="static")


# --------------------------------------------------------------------------- helpers
def _model(request: Request) -> TriageModel:
    m = request.app.state.model
    if m is None:
        raise HTTPException(status_code=503, detail="modelo não carregado: rode `make train` para gerar models/index.pkl")
    return m


def _replay(request: Request) -> HoldoutReplay:
    r = request.app.state.replay
    if r is None:
        raise HTTPException(status_code=503, detail="hold-out ausente: rode `make train` para gerar artifacts/holdout_pred.csv.gz")
    return r


def _ticket_id(holdout_id: int) -> str:
    return f"h{int(holdout_id)}"


def _parse_ticket_id(value: str) -> int | None:
    v = (value or "").strip()
    if v[:1] in ("h", "H"):
        v = v[1:]
    return int(v) if v.isdigit() else None


def _neighbors(model: TriageModel | None, ids: list[int], sims: list[float]) -> list[dict]:
    if model is not None:
        return model.neighbors_by_ids(ids, sims)
    # Degraded mode (no pickle): keep ids and similarities, no excerpt/class.
    return [{"id": int(i), "excerpt": "", "category": None, "similarity": round(float(s), 4)} for i, s in zip(ids, sims)]


def _gate(category: str, confidence: float, text: str, threshold: float | None) -> dict:
    flags = risk_flags(text)
    d = decide(category, confidence, flags, threshold if threshold is not None else DEFAULT_THRESHOLD)
    return {"risk_flags": flags, **d.to_dict(), "draft": draft_for(category, d.decision)}


def _ticket_from_row(row: dict, model: TriageModel | None, threshold: float | None) -> dict:
    """Replay row -> ticket dict (before the board fills assigned_to/status/created_at)."""
    return {
        "id": _ticket_id(row["id"]),
        "text": row["text"],
        "true_category": row["true_category"],
        "category": row["pred_category"],
        "confidence": row["confidence"],
        "top3": row["top3"],
        "neighbors": _neighbors(model, row["nn_ids"], row["nn_sims"]),
        **_gate(row["pred_category"], row["confidence"], row["text"], threshold),
    }


# --------------------------------------------------------------------------- endpoints
@app.get("/api/health")
def health(request: Request) -> dict:
    st = request.app.state
    return {
        "status": "ok",
        "model_loaded": st.model is not None,
        "n_train": st.model.n_train if st.model else 0,
        "n_holdout": st.replay.total if st.replay else 0,
        "version": VERSION,
        "llm_enabled": False,
    }


@app.post("/api/triage")
def triage(body: TriageBody, request: Request) -> dict:
    model = _model(request)
    pred = model.predict(body.text)
    return {**pred, **_gate(pred["category"], pred["confidence"], body.text, body.threshold)}


@app.post("/api/replay/next")
def replay_next(body: ReplayBody, request: Request) -> dict:
    st = request.app.state
    replay = _replay(request)
    tickets = [st.board.add(_ticket_from_row(row, st.model, body.threshold)) for row in replay.next(body.n)]
    return {"tickets": tickets, "position": replay.position, "total": replay.total}


@app.post("/api/tickets/{ticket_id}/action")
def ticket_action(ticket_id: str, body: ActionBody, request: Request) -> dict:
    if body.action not in ACTIONS:
        raise HTTPException(status_code=400, detail=f"ação inválida: use uma de {list(ACTIONS)}")
    try:
        return request.app.state.board.action(ticket_id, body.action)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"ticket {ticket_id!r} não está no board") from None


@app.get("/api/board")
def board(request: Request, limit: int = Query(200, ge=1, le=2000)) -> dict:
    return request.app.state.board.snapshot(limit_per_level=limit)


@app.post("/api/reset")
def reset(request: Request) -> dict:
    st = request.app.state
    st.board.reset()
    if st.replay is not None:
        st.replay.reset()
    return {"ok": True}


def _artifact(request: Request, name: str, filename: str) -> Any:
    data = getattr(request.app.state, name)
    if data is None:
        raise HTTPException(status_code=404, detail=f"{filename} não encontrado: rode `make train`")
    return data


@app.get("/api/metrics")
def metrics(request: Request) -> Any:
    return _artifact(request, "metrics", "artifacts/metrics.json")


@app.get("/api/ds1")
def ds1(request: Request) -> Any:
    return _artifact(request, "ds1", "artifacts/ds1_metrics.json")


@app.get("/api/policy")
def policy(request: Request) -> Any:
    return _artifact(request, "policy", "artifacts/policy.json")


@app.get("/api/examples")
def examples(request: Request) -> dict:
    rows = request.app.state.examples
    return {"examples": [{"id": _ticket_id(r["id"]), "text": r["text"], "true_category": r["true_category"]} for r in rows]}


@app.post("/api/closure")
def closure(payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    errors = validate_closure(payload)
    if errors:
        return {"ok": False, "errors": errors, "kb_entry": None}
    return {"ok": True, "errors": [], "kb_entry": build_kb_entry(payload)}


@app.get("/api/closure/options")
def closure_form_options() -> dict:
    return closure_options()


@app.get("/api/kb/example")
def kb_example(request: Request, ticket_id: str = Query("", description="hold-out ticket id, e.g. h12 or 12")) -> dict:
    st = request.app.state
    replay = _replay(request)
    if ticket_id.strip():
        hid = _parse_ticket_id(ticket_id)
        row = replay.get(hid) if hid is not None else None
        if row is None:
            raise HTTPException(status_code=404, detail=f"ticket {ticket_id!r} não está no hold-out")
    elif st.examples:
        row = st.examples[0]
    else:
        raise HTTPException(status_code=404, detail="hold-out vazio")

    similar = []
    for i, nb in enumerate(_neighbors(st.model, row["nn_ids"], row["nn_sims"])):
        closure_example = None
        if nb["category"] is not None:
            variants = kb_examples(nb["category"])["examples"]
            closure_example = variants[i % len(variants)]
        similar.append({**nb, "closure": closure_example})
    return {
        "ticket": {"id": _ticket_id(row["id"]), "text": row["text"], "category": row["pred_category"]},
        "similar": similar,
        "illustrative": True,
        "note": ILLUSTRATIVE_NOTE,
    }


@app.get("/", include_in_schema=False)
def index() -> Any:
    if INDEX_HTML.exists():
        return FileResponse(str(INDEX_HTML), media_type="text/html; charset=utf-8")
    return HTMLResponse(
        "<!doctype html><meta charset='utf-8'><title>Triagem N1-IA</title>"
        "<body style='font-family:system-ui;padding:2rem'><h1>Triagem N1-IA / N2 / N3</h1>"
        "<p>A página ainda não foi construída. A API está no ar: <a href='/docs'>/docs</a>, "
        "<a href='/api/health'>/api/health</a>.</p>"
        "<p><small>Protótipo de candidatura — não afiliado à G4</small></p></body>"
    )
