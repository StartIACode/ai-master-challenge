/* Triagem N1-IA / N2 / N3 — single-page UI (vanilla JS, no build, no CDN).
   Consumes the API contract in app/api.py. All user-facing text is pt-BR; class names travel
   in English to/from the API and are translated for display through LABEL_PT.
   Invariant mirrored from the backend: the AI never answers the customer nor closes a ticket. */
(() => {
  'use strict';

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const TABS = ['painel', 'board', 'novo', 'fechamento'];
  const LEVELS = ['N1', 'N2', 'N3'];
  const DEFAULT_THRESHOLD = 0.90;
  const THRESHOLD_OPTIONS = [0.80, 0.90, 0.95];
  const BATCH = 10;
  const AUTO_MS = 3000;
  const TICK_MS = 5000; // Painel auto-refresh and "nesta coluna há" clocks on the board
  const MAX_CARDS = 30;

  // Display labels for the API class keys (values sent to the API stay in English).
  const LABEL_PT = {
    Access: 'Acesso',
    'Administrative rights': 'Direitos administrativos',
    'HR Support': 'Suporte de RH',
    Hardware: 'Hardware',
    'Internal Project': 'Projeto interno',
    Miscellaneous: 'Diversos',
    Purchase: 'Compras',
    Storage: 'Armazenamento',
  };
  const labelPt = (c) => (c == null || c === '' ? c : (LABEL_PT[c] || String(c)));
  const CLASS_RE = new RegExp(`\\b(${Object.keys(LABEL_PT).sort((a, b) => b.length - a.length).join('|')})\\b`, 'g');
  const ptText = (s) => String(s ?? '').replace(CLASS_RE, (m) => LABEL_PT[m]); // policy reasons quote class keys

  const DECISION_LABEL = {
    auto_route: 'auto-roteio',
    suggest: 'sugerir fila',
    human_triage: 'triagem humana',
    human_required: 'humano obrigatório',
  };
  const DECISION_LONG = {
    auto_route: 'Auto-roteio (N1-IA): entra na fila da classe com rascunho pronto; o humano responde, edita ou marca "IA errou".',
    suggest: 'Sugerir fila (N2): a IA sugere a fila e o analista confirma antes de entrar; sem rascunho.',
    human_triage: 'Triagem humana (N2): confiança abaixo do limiar ou classe Diversos; o analista decide a fila.',
    human_required: 'Humano obrigatório (N2): sinal de risco no texto; sem rascunho, sem automação.',
  };
  const STATUS_LABEL = { aberto: 'aberto', em_atendimento: 'em atendimento', resolvido: 'resolvido' };
  const RISK_LABEL = {
    legal: 'jurídico', cancel: 'cancelamento', refund: 'reembolso', harassment: 'assédio/ameaça',
    health: 'saúde', vip: 'VIP/enterprise', social: 'canal social', reopened: 'reaberto',
  };
  const ACTION_LABEL = { assume: 'assumido', resolve: 'resolvido', escalate: 'escalado ao N3', ai_wrong: 'marcado como "IA errou"' };
  const TMA_TITLE = { N1: 'TMA N1-IA', N2: 'TMA N2', N3: 'TMA N3' };

  const state = {
    threshold: DEFAULT_THRESHOLD,
    health: null, options: null,
    examples: [], board: null, position: 0, total: 0,
    autoTimer: null, uiTimer: null, busy: false, currentTab: 'painel',
  };

  // ------------------------------------------------------------------ helpers
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const isNum = (x) => typeof x === 'number' && Number.isFinite(x);
  const fmtNum = (x, d = 0) => (isNum(x) ? x.toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d }) : '—');
  const fmtPct = (x, d = 1) => (isNum(x) ? (x * 100).toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d }) + '%' : '—');
  const fmtP = (x) => (isNum(x) ? (x >= 0.995 ? '0,99+' : x.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })) : '—');
  const ratio = (a, b) => (isNum(a) && isNum(b) && b > 0 ? a / b : null);
  const truncate = (s, n) => { const t = String(s || ''); return t.length > n ? t.slice(0, n - 1).trimEnd() + '…' : t; };
  const plural = (n, one, many) => `${fmtNum(n)} ${n === 1 ? one : many}`;
  // Seconds -> mm:ss, or h:mm:ss from one hour on; null/NaN -> em dash.
  function fmtDur(seconds) {
    if (!isNum(seconds) || seconds < 0) return '—';
    const t = Math.round(seconds);
    const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60;
    const p = (n) => String(n).padStart(2, '0');
    return h ? `${h}:${p(m)}:${p(s)}` : `${p(m)}:${p(s)}`;
  }
  const ageSeconds = (iso) => { const ms = Date.parse(iso || ''); return Number.isFinite(ms) ? Math.max(0, (Date.now() - ms) / 1000) : null; };

  async function api(path, opts = {}) {
    const init = { method: opts.method || (opts.body !== undefined ? 'POST' : 'GET'), headers: {} };
    if (opts.body !== undefined) {
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(opts.body);
    }
    const res = await fetch(path, init);
    const ct = res.headers.get('content-type') || '';
    const data = ct.includes('application/json') ? await res.json() : await res.text();
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      if (data && typeof data === 'object' && data.detail !== undefined) {
        detail = typeof data.detail === 'string' ? data.detail
          : Array.isArray(data.detail) ? data.detail.map((d) => d.msg || JSON.stringify(d)).join('; ')
          : JSON.stringify(data.detail);
      }
      const err = new Error(detail);
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  let toastTimer = null;
  function toast(msg, kind = 'info', action = null) {
    const el = $('#toast');
    el.className = 'toast' + (kind === 'err' ? ' err' : '');
    el.innerHTML = `<span>${esc(msg)}</span>` + (action ? `<button type="button" class="btn btn-sm btn-primary" id="toast-action">${esc(action.label)}</button>` : '');
    el.hidden = false;
    if (action) $('#toast-action').addEventListener('click', () => { el.hidden = true; action.run(); });
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, action ? 9000 : 4000);
  }

  function badge(kind) {
    const map = { real: ['badge-real', 'REAL'], board: ['badge-real', 'MEDIDO NO BOARD'], sim: ['badge-sim', 'SIMULAÇÃO'] };
    const [cls, label] = map[kind] || map.real;
    return `<span class="badge ${cls}">${label}</span>`;
  }
  function kpi(label, value, sub = '', kind = 'real', gold = false) {
    return `<div class="kpi"><div class="k"><span>${label}</span>${badge(kind)}</div><div class="v${gold ? ' gold' : ''}">${value}</div>${sub ? `<div class="s">${sub}</div>` : ''}</div>`;
  }

  // ------------------------------------------------------------------ tabs
  function showTab(name, { focus = false } = {}) {
    if (!TABS.includes(name)) name = 'painel';
    state.currentTab = name;
    for (const btn of $$('.tabs [role="tab"]')) {
      const on = btn.dataset.tab === name;
      btn.setAttribute('aria-selected', on ? 'true' : 'false');
      btn.tabIndex = on ? 0 : -1;
      if (on && focus) btn.focus();
    }
    for (const t of TABS) {
      const panel = $(`#tab-${t}`);
      if (panel) panel.hidden = t !== name;
    }
    if (history.replaceState) history.replaceState(null, '', `#${name}`);
    if (name === 'painel') renderPainel();
    if (name === 'board') tickAges();
    syncTicker();
  }
  function bindTabs() {
    const list = $('.tabs');
    list.addEventListener('click', (e) => {
      const btn = e.target.closest('[role="tab"]');
      if (btn) showTab(btn.dataset.tab);
    });
    list.addEventListener('keydown', (e) => {
      const keys = ['ArrowLeft', 'ArrowRight', 'Home', 'End'];
      if (!keys.includes(e.key)) return;
      e.preventDefault();
      const i = TABS.indexOf(state.currentTab);
      let j = i;
      if (e.key === 'ArrowLeft') j = (i - 1 + TABS.length) % TABS.length;
      if (e.key === 'ArrowRight') j = (i + 1) % TABS.length;
      if (e.key === 'Home') j = 0;
      if (e.key === 'End') j = TABS.length - 1;
      showTab(TABS[j], { focus: true });
    });
    window.addEventListener('hashchange', () => showTab(location.hash.slice(1) || 'painel'));
    document.addEventListener('visibilitychange', syncTicker);
  }

  // One 5 s ticker, alive only while the page is visible and the Painel or the Board is the
  // current tab: the Painel re-reads /api/board (TMA moves as humans act); the Board only
  // recomputes the "nesta coluna há" clocks locally from level_entered_at.
  function syncTicker() {
    const wanted = !document.hidden && (state.currentTab === 'painel' || state.currentTab === 'board');
    if (!wanted && state.uiTimer) { clearInterval(state.uiTimer); state.uiTimer = null; }
    if (wanted && !state.uiTimer) {
      state.uiTimer = setInterval(async () => {
        if (document.hidden) return;
        if (state.currentTab === 'board') { tickAges(); return; }
        if (state.currentTab === 'painel' && !state.busy) {
          const ok = await refreshBoard();
          if (!ok) { clearInterval(state.uiTimer); state.uiTimer = null; } // API down: stop polling (resumes on tab change or Atualizar)
        }
      }, TICK_MS);
    }
  }

  // ------------------------------------------------------------------ loaders
  async function loadHealth() {
    const el = $('#health');
    try {
      state.health = await api('/api/health');
      const h = state.health;
      el.innerHTML = `<span class="dot${h.model_loaded ? '' : ' off'}"></span>` +
        (h.model_loaded ? `modelo carregado · <b>${fmtNum(h.n_train)}</b> treino · <b>${fmtNum(h.n_holdout)}</b> hold-out` : 'modelo não carregado (rode make train)') +
        ` · v${esc(h.version)} · LLM ${h.llm_enabled ? 'ligado' : 'desligado'}`;
    } catch (err) {
      el.innerHTML = `<span class="dot off"></span>API indisponível: ${esc(err.message)}`;
    }
  }
  async function loadExamples() {
    try { state.examples = (await api('/api/examples')).examples || []; } catch (_) { state.examples = []; }
  }
  async function loadOptions() {
    try { state.options = await api('/api/closure/options'); } catch (_) { state.options = null; }
  }

  // ------------------------------------------------------------------ 1. painel
  function tmaCard(level) {
    const c = state.board && state.board.counters;
    const tma = (c && c.tma && c.tma[level]) || {};
    const open = (c && c.tma && c.tma.open && c.tma.open[level]) || 0;
    const n = isNum(tma.n) ? tma.n : 0;
    const openTxt = `${plural(open, 'card', 'cards')} ainda no nível`;
    if (!n || !isNum(tma.avg_s)) {
      return kpi(TMA_TITLE[level], '—', `ainda sem cards concluídos${open ? ` · ${openTxt}` : ''}`, 'board');
    }
    return kpi(TMA_TITLE[level], fmtDur(tma.avg_s), `${plural(n, 'estadia concluída', 'estadias concluídas')} · ${openTxt}`, 'board');
  }

  function renderPainel() {
    const c = state.board && state.board.counters;
    const el = $('#kpis');
    const holdout = state.total || (state.health && state.health.n_holdout) || 0;
    const available = holdout ? `de ${fmtNum(holdout)} disponíveis no hold-out` : 'hold-out indisponível';
    const bd = (c && c.by_decision) || {};
    const tmas = LEVELS.map(tmaCard).join('');
    if (!c || !c.total) {
      el.innerHTML =
        kpi('Tickets recebidos', '0', `${available} · rode o replay na aba Board`) +
        kpi('Tratados pela IA (N1-IA)', '—', 'a IA resolveu a triagem; humano só confirma', 'real', true) +
        kpi('Delegados ao humano (N2)', '—', 'a IA passou a decisão para uma pessoa') +
        kpi('Escalados ao N3', '—', 'só por clique humano') +
        kpi('Acerto da IA', '—', 'classe prevista = classe verdadeira') +
        kpi('IA errou', '0', 'correções humanas') +
        tmas;
      return;
    }
    el.innerHTML =
      kpi('Tickets recebidos', fmtNum(c.total), `entraram no board nesta sessão, ${available}`) +
      kpi('Tratados pela IA (N1-IA)', fmtPct(ratio(c.n1, c.total)),
        `${plural(c.n1, 'ticket', 'tickets')}: a IA resolveu a triagem; humano só confirma o rascunho. Não é escalação.`, 'real', true) +
      kpi('Delegados ao humano (N2)', fmtPct(ratio(c.n2, c.total)),
        `decisão da IA na chegada: ${plural(c.n2, 'ticket', 'tickets')} em que uma pessoa decide · sugestão de fila ${fmtNum(bd.suggest)} · triagem ${fmtNum(bd.human_triage)} · humano obrigatório ${fmtNum(bd.human_required)}`) +
      kpi('Escalados ao N3', fmtPct(ratio(c.n3, c.total)), `${plural(c.n3, 'escalado', 'escalados')} por clique humano`) +
      kpi('Acerto da IA', fmtPct(ratio(c.ai_correct, c.ai_evaluated)),
        `${fmtNum(c.ai_correct)} de ${fmtNum(c.ai_evaluated)} com classe prevista = verdadeira · nos tratados pela IA: ${fmtPct(ratio(c.auto_correct, c.auto_evaluated))}`) +
      kpi('IA errou', fmtNum(c.ai_wrong), `correções humanas · ${plural(c.resolved, 'resolvido', 'resolvidos')} por humano`) +
      tmas;
  }

  // ------------------------------------------------------------------ 2. board
  function ticketCard(t) {
    const ok = t.true_category === t.category;
    const text = t.text || '';
    const long = text.length > 220;
    const flags = (t.risk_flags || []).map((f) => `<span class="chip chip-danger">${esc(RISK_LABEL[f] || f)}</span>`).join(' ');
    const top3 = (t.top3 || []).map((x) => `${esc(labelPt(x.category))} ${fmtP(x.p)}`).join(' · ');
    const nb = (t.neighbors || []).map((n) =>
      `<li><span class="sim">${fmtP(n.similarity)}</span> <span class="cls">${esc(labelPt(n.category) || '?')}</span> <span class="ex">${esc(n.excerpt || '(sem trecho)')}</span></li>`).join('');
    const draft = t.draft
      ? `<details class="sub"><summary>Rascunho (macro; LLM desligado)</summary><pre class="draft">${esc(t.draft)}</pre><p class="tiny">Humano revisa, edita e envia. A IA não responde ao cliente.</p></details>`
      : `<p class="tiny">Sem rascunho: ${t.decision === 'auto_route' ? 'classe sem macro' : 'só auto-roteio recebe rascunho'}.</p>`;
    const age = t.level_entered_at
      ? `<span class="chip chip-age" data-entered="${esc(t.level_entered_at)}">nesta coluna há ${fmtDur(ageSeconds(t.level_entered_at))}</span>`
      : '';
    return `<article class="ticket dec-${esc(t.decision)}" data-id="${esc(t.id)}" aria-label="Ticket ${esc(t.id)}">
      <header class="ticket-head">
        <span class="tid">${esc(t.id)}</span>
        <span class="badge badge-dec">${esc(DECISION_LABEL[t.decision] || t.decision)}</span>
        <span class="chip chip-status status-${esc(t.status)}">${esc(STATUS_LABEL[t.status] || t.status)}</span>
        ${t.ai_wrong ? '<span class="chip chip-danger">IA errou</span>' : ''}
        ${age}
      </header>
      <p class="ticket-text${long ? ' clamp' : ''}">${esc(text)}</p>
      ${long ? '<button type="button" class="linkbtn" data-toggle="text">ver tudo</button>' : ''}
      <dl class="meta">
        <div><dt>Classe prevista</dt><dd>${esc(labelPt(t.category))} <b>p ${fmtP(t.confidence)}</b></dd></div>
        <div><dt>Classe verdadeira</dt><dd>${esc(labelPt(t.true_category))} <span class="${ok ? 'ok' : 'bad'}" title="${ok ? 'acertou' : 'errou'}">${ok ? '✓' : '✗'}</span></dd></div>
        <div><dt>Fila · nível</dt><dd>${esc(labelPt(t.queue))} · ${esc(t.level)}</dd></div>
        <div><dt>Responsável</dt><dd>${t.assigned_to ? esc(t.assigned_to) : '—'} ${badge('sim').replace('SIMULAÇÃO', 'SIMULADO')}</dd></div>
      </dl>
      ${top3 ? `<p class="top3">Top-3 classes: ${top3}</p>` : ''}
      ${flags ? `<p class="flags">Risco: ${flags}</p>` : ''}
      <p class="reason"><b>Decisão:</b> ${esc(ptText(t.reason))}</p>
      <details class="sub"><summary>Top-3 similares no treino ${badge('real')}</summary><ol class="nb">${nb || '<li>sem vizinhos</li>'}</ol></details>
      ${draft}
      <div class="actions">
        <button type="button" class="btn btn-sm" data-action="assume" ${t.status !== 'aberto' ? 'disabled' : ''}>Assumir</button>
        <button type="button" class="btn btn-sm btn-primary" data-action="resolve">Resolver</button>
        <button type="button" class="btn btn-sm" data-action="escalate" ${t.level === 'N3' ? 'disabled' : ''}>Escalar N3</button>
        <button type="button" class="btn btn-sm btn-danger" data-action="ai_wrong" ${t.ai_wrong ? 'disabled' : ''}>IA errou</button>
      </div>
    </article>`;
  }

  // Refresh the "nesta coluna há mm:ss" chips in place (no fetch, no re-render).
  function tickAges() {
    for (const el of $$('#board [data-entered]')) el.textContent = `nesta coluna há ${fmtDur(ageSeconds(el.dataset.entered))}`;
  }

  function renderBoard() {
    const snap = state.board;
    if (!snap) return;
    for (const lvl of LEVELS) {
      const items = snap[lvl] || [];
      const shown = items.slice(0, MAX_CARDS);
      $(`#count-${lvl}`).textContent = items.length > MAX_CARDS ? `${MAX_CARDS}+` : String(items.length);
      $(`#col-${lvl}`).innerHTML = shown.length
        ? shown.map(ticketCard).join('') + (items.length > MAX_CARDS ? `<p class="empty">mostrando os ${MAX_CARDS} mais recentes</p>` : '')
        : '<p class="empty">Sem tickets abertos.</p>';
    }
    $('#resolved-chip').textContent = `resolvidos por humano: ${fmtNum(snap.resolved)}`;
    // The cursor only travels in /api/replay/next; before the first batch of this page load it is unknown.
    const pos = state.position ? fmtNum(state.position) : '—';
    $('#replay-pos').textContent = `${pos} de ${fmtNum(state.total || (state.health && state.health.n_holdout) || 0)}`;
  }

  async function refreshBoard() {
    try {
      state.board = await api(`/api/board?limit=${MAX_CARDS + 1}`);
      renderBoard();
      if (state.currentTab === 'painel') renderPainel();
      return true;
    } catch (err) {
      toast(`Board indisponível: ${err.message}`, 'err');
      return false;
    }
  }

  async function replayNext(n = BATCH) {
    if (state.busy) return;
    state.busy = true;
    $('#btn-next').disabled = true;
    try {
      const r = await api('/api/replay/next', { body: { n, threshold: state.threshold } });
      state.position = r.position;
      state.total = r.total;
      await refreshBoard();
    } catch (err) {
      toast(`Replay falhou: ${err.message}`, 'err');
      if (state.autoTimer) toggleAuto();
    } finally {
      state.busy = false;
      $('#btn-next').disabled = false;
    }
  }

  function toggleAuto() {
    const btn = $('#btn-auto');
    if (state.autoTimer) {
      clearInterval(state.autoTimer);
      state.autoTimer = null;
      btn.setAttribute('aria-pressed', 'false');
      btn.textContent = 'Auto a cada 3 s: desligado';
    } else {
      state.autoTimer = setInterval(() => replayNext(BATCH), AUTO_MS);
      btn.setAttribute('aria-pressed', 'true');
      btn.textContent = 'Auto a cada 3 s: ligado';
      replayNext(BATCH);
    }
  }

  async function resetAll() {
    if (state.autoTimer) toggleAuto(); // reviewer: reset must also stop the auto-replay
    try {
      await api('/api/reset', { body: {} });
      state.position = 0;
      await refreshBoard();
      toast('Board e replay reiniciados.');
    } catch (err) {
      toast(`Reiniciar falhou: ${err.message}`, 'err');
    }
  }

  async function doAction(id, action) {
    try {
      const t = await api(`/api/tickets/${encodeURIComponent(id)}/action`, { body: { action } });
      await refreshBoard();
      if (action === 'resolve') {
        toast(`${t.id} ${ACTION_LABEL[action]} por humano. Registre o fechamento padronizado.`, 'info', {
          label: 'Registrar fechamento',
          run: () => { prefillClosure(t); showTab('fechamento', { focus: true }); },
        });
      } else {
        toast(`${t.id} ${ACTION_LABEL[action] || action}.`);
      }
    } catch (err) {
      toast(`Ação falhou: ${err.message}`, 'err');
    }
  }

  function bindBoard() {
    $('#btn-next').addEventListener('click', () => replayNext(BATCH));
    $('#btn-auto').addEventListener('click', toggleAuto);
    $('#btn-reset').addEventListener('click', resetAll);
    $('#board').addEventListener('click', (e) => {
      const tg = e.target.closest('[data-toggle="text"]');
      if (tg) {
        const p = tg.previousElementSibling;
        const clamped = p.classList.toggle('clamp');
        tg.textContent = clamped ? 'ver tudo' : 'ver menos';
        return;
      }
      const btn = e.target.closest('[data-action]');
      if (!btn || btn.disabled) return;
      const card = btn.closest('.ticket[data-id]');
      if (card) doAction(card.dataset.id, btn.dataset.action);
    });
  }

  // ------------------------------------------------------------------ threshold (gate)
  // The threshold is the minimum confidence for the AI to act alone; it is sent with every
  // /api/replay/next and /api/triage call. Choices are the three values the hold-out curves
  // were measured at; the default stays 0,90.
  function setThreshold(v) {
    const t = THRESHOLD_OPTIONS.includes(v) ? v : DEFAULT_THRESHOLD;
    state.threshold = t;
    $('#threshold-select').value = t.toFixed(2);
    for (const el of $$('.threshold-readout')) el.textContent = fmtP(t);
  }
  function bindThreshold() {
    $('#threshold-select').addEventListener('change', (e) => {
      setThreshold(parseFloat(e.target.value));
      toast(`Limiar de confiança ${fmtP(state.threshold)}: vale para os próximos lotes e para a triagem de novo ticket.`);
    });
  }

  // ------------------------------------------------------------------ 3. novo ticket
  function renderNovoExamples() {
    const el = $('#novo-examples');
    if (!state.examples.length) { el.innerHTML = '<p class="hint">Exemplos indisponíveis (hold-out ausente).</p>'; return; }
    el.innerHTML = state.examples.map((e, i) =>
      `<button type="button" class="example" data-example="${i}"><span class="cls">exemplo real ${i + 1} · classe verdadeira: ${esc(labelPt(e.true_category))}</span><span class="ex">${esc(truncate(e.text, 110))}</span></button>`).join('');
  }

  function renderTriage(r, text) {
    const flags = (r.risk_flags || []).map((f) => `<span class="chip chip-danger">${esc(RISK_LABEL[f] || f)}</span>`).join(' ');
    const bars = (r.top3 || []).map((x) => `<div class="bar"><span>${esc(labelPt(x.category))}</span><div class="track"><div class="fill" style="width:${Math.max(1, x.p * 100).toFixed(1)}%"></div></div><span class="n">${fmtP(x.p)}</span></div>`).join('');
    const nb = (r.neighbors || []).length
      ? `<ol class="nb">${r.neighbors.map((n) => `<li><span class="sim">${fmtP(n.similarity)}</span> <span class="cls">${esc(labelPt(n.category))}</span> <span class="ex">${esc(n.excerpt)}</span></li>`).join('')}</ol>`
      : '<p class="hint">Sem vizinhos: o texto não tem termos conhecidos pelo vocabulário do modelo.</p>';
    const draft = r.draft
      ? `<pre class="draft">${esc(r.draft)}</pre><p class="tiny">Macro por classe (LLM desligado). Humano revisa, edita e envia.</p>`
      : `<p class="hint">Sem rascunho: ${r.decision === 'human_required' ? 'sinal de risco exige humano' : r.decision === 'suggest' ? 'classe sensível: N2 confirma a fila antes' : 'só auto-roteio recebe rascunho'}.</p>`;
    $('#novo-result').innerHTML = `
      <div class="result-dec dec-${esc(r.decision)}">
        <div class="result-head"><span class="big"><span class="badge badge-dec">${esc(DECISION_LABEL[r.decision] || r.decision)}</span> nível ${esc(r.level)} · fila <b>${esc(labelPt(r.queue))}</b></span>${badge('real')}</div>
        <p style="margin:6px 0 0">${esc(DECISION_LONG[r.decision] || '')}</p>
        <p class="reason" style="margin-top:6px"><b>Motivo:</b> ${esc(ptText(r.reason))}</p>
        ${flags ? `<p class="flags">Sinais de risco: ${flags}</p>` : ''}
      </div>
      <div class="cards-2" style="margin-top:12px">
        <article class="card"><header class="card-head"><h3>Classe prevista: ${esc(labelPt(r.category))} · p ${fmtP(r.confidence)}</h3>${badge('real')}</header><div class="bars">${bars}</div><p class="tiny">Limiar aplicado: ${fmtP(state.threshold)}. Texto triado (${text.length} caracteres) normalizado no servidor.</p></article>
        <article class="card"><header class="card-head"><h3>Top-3 tickets históricos parecidos</h3>${badge('real')}</header>${nb}</article>
        <article class="card" style="grid-column:1/-1"><header class="card-head"><h3>Rascunho para o analista</h3>${r.draft ? badge('real') : ''}</header>${draft}</article>
      </div>`;
  }

  async function submitNovo(e) {
    e.preventDefault();
    const text = $('#novo-text').value.trim();
    if (!text) { toast('Digite ou escolha um texto.', 'err'); return; }
    const btn = $('#btn-triar');
    btn.disabled = true;
    try {
      const r = await api('/api/triage', { body: { text, threshold: state.threshold } });
      renderTriage(r, text);
    } catch (err) {
      $('#novo-result').innerHTML = `<div class="notice err">Triagem falhou: ${esc(err.message)}</div>`;
    } finally {
      btn.disabled = false;
    }
  }
  function bindNovo() {
    $('#form-novo').addEventListener('submit', submitNovo);
    $('#novo-examples').addEventListener('click', (e) => {
      const b = e.target.closest('[data-example]');
      if (!b) return;
      const ex = state.examples[Number(b.dataset.example)];
      if (ex) { $('#novo-text').value = ex.text; $('#novo-text').focus(); }
    });
  }

  // ------------------------------------------------------------------ 4. fechamento padronizado
  // Option values are what the API expects (class keys in English); labelOf renders the text.
  function fillSelect(sel, values, placeholder, labelOf = (v) => v) {
    sel.innerHTML = `<option value="">${esc(placeholder)}</option>` + values.map((v) => `<option value="${esc(v)}">${esc(labelOf(v))}</option>`).join('');
  }
  function buildClosureForm() {
    const o = state.options;
    if (!o) {
      $('#fechamento-result').innerHTML = '<div class="notice warn">Listas do formulário indisponíveis (/api/closure/options). A validação continua na API.</div>';
      return;
    }
    fillSelect($('#fc-category'), o.categories || [], '— escolha —', labelPt);
    fillSelect($('#fc-root'), o.root_causes || [], '— escolha —');
    fillSelect($('#fc-level'), o.levels || [], '— escolha —');
    updateSubcategories();
  }
  function updateSubcategories(keep = '') {
    const cat = $('#fc-category').value;
    const subs = (state.options && state.options.subcategories && state.options.subcategories[cat]) || [];
    fillSelect($('#fc-subcategory'), subs, cat ? '— escolha —' : '— escolha a categoria —');
    if (keep && subs.includes(keep)) $('#fc-subcategory').value = keep;
  }
  // form.reset() dispatches 'reset' synchronously; the listener below defers its cleanup with
  // setTimeout, which would run AFTER a programmatic prefill and wipe it. The flag makes the
  // listener react only to the user's "Limpar" button.
  let programmaticReset = false;
  function resetClosureForm() {
    programmaticReset = true;
    try { $('#form-fechamento').reset(); } finally { programmaticReset = false; }
  }
  function prefillClosure(t) {
    resetClosureForm();
    $('#fc-ticket').value = t.id || '';
    $('#fc-category').value = t.category || '';
    updateSubcategories();
    $('#fc-level').value = t.level === 'N3' ? 'N3' : 'N2';
    $('#fechamento-result').innerHTML = `<div class="notice">Ticket <b>${esc(t.id)}</b> resolvido por ${esc(t.assigned_to || 'humano')}: preencha o template para o fechamento valer.</div>`;
  }
  function closurePayload(form) {
    const fd = new FormData(form);
    const s = (k) => String(fd.get(k) ?? '').trim();
    const opt = s('root_cause_option');
    const detail = s('root_cause_detail');
    let root_cause = opt;
    if (opt === 'Outro (descrever)') root_cause = detail;
    else if (opt && detail) root_cause = `${opt}: ${detail}`;
    const bool = (k) => (fd.get(k) === null ? null : fd.get(k) === 'true');
    return {
      ticket_id: s('ticket_id') || null,
      category: s('category'),
      subcategory: s('subcategory'),
      root_cause,
      resolution_steps: s('resolution_steps'),
      resolved_by_level: s('resolved_by_level'),
      time_spent_min: s('time_spent_min') === '' ? null : Number(s('time_spent_min')),
      customer_reply: s('customer_reply') || null,
      reusable: bool('reusable'),
      reopened: bool('reopened'),
      kb_article: s('kb_article') || null,
      satisfaction: s('satisfaction') === '' ? null : Number(s('satisfaction')),
      affected_system: s('affected_system') || null,
      tags: s('tags'),
    };
  }
  function renderKbEntry(k) {
    const rows = [
      ['ID na base', k.id], ['Ticket', k.ticket_id || '—'], ['Categoria', `${labelPt(k.category)} › ${k.subcategory}`],
      ['Causa raiz', k.root_cause], ['Ação de resolução', k.resolution_steps], ['Nível', k.resolved_by_level],
      ['Tempo gasto', `${fmtNum(k.time_spent_min)} min`], ['Resposta ao cliente', k.customer_reply || '—'],
      ['Reutilizável', k.reusable ? 'sim' : 'não'], ['Reaberto', k.reopened ? 'sim' : 'não'],
      ['Artigo vinculado', k.kb_article || '—'], ['Satisfação', k.satisfaction ?? '—'],
      ['Sistema afetado', k.affected_system || '—'], ['Tags', (k.tags || []).join(', ') || '—'],
    ];
    return `<div class="notice ok"><b>Fechamento válido.</b> Esta é a entrada que iria para a base de conhecimento.</div>
      <article class="card" style="margin-top:12px"><header class="card-head"><h3>Entrada da base de conhecimento</h3>${badge('sim').replace('SIMULAÇÃO', 'NÃO PERSISTIDA')}</header>
      <dl class="dl">${rows.map(([a, b]) => `<dt>${esc(a)}</dt><dd><pre>${esc(b)}</pre></dd>`).join('')}</dl>
      <p class="tiny">${esc(k.note || '')}</p></article>`;
  }
  async function submitFechamento(e) {
    e.preventDefault();
    const form = $('#form-fechamento');
    const btn = $('#btn-fechar');
    btn.disabled = true;
    try {
      const r = await api('/api/closure', { body: closurePayload(form) });
      if (r.ok) {
        $('#fechamento-result').innerHTML = renderKbEntry(r.kb_entry);
      } else {
        $('#fechamento-result').innerHTML = `<div class="notice err"><b>O ticket não fecha:</b> ${r.errors.length} campo(s) obrigatório(s) pendente(s), validados pela API.<ul class="errors">${r.errors.map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>`;
      }
      $('#fechamento-result').scrollIntoView({ block: 'nearest' });
    } catch (err) {
      $('#fechamento-result').innerHTML = `<div class="notice err">Validação falhou: ${esc(err.message)}</div>`;
    } finally {
      btn.disabled = false;
    }
  }
  function fillClosureExample() {
    const form = $('#form-fechamento');
    resetClosureForm();
    $('#fc-ticket').value = (state.examples[0] && state.examples[0].id) || 'h12';
    $('#fc-category').value = 'Access';
    updateSubcategories('Novo acesso');
    $('#fc-root').value = 'Falta de permissão ou aprovação';
    $('#fc-root-detail').value = 'conta fora do grupo de segurança exigido pelo sistema';
    $('#fc-steps').value = '1. Conferir no diretório o grupo exigido pelo sistema\n2. Validar a aprovação do gestor no chamado\n3. Adicionar a conta ao grupo\n4. Pedir ao usuário para sair e entrar novamente\n5. Confirmar o acesso com o usuário';
    $('#fc-level').value = 'N2';
    $('#fc-min').value = '12';
    $('#fc-reply').value = 'Olá! Seu acesso foi liberado após a aprovação do gestor. Saia e entre novamente para a permissão ser aplicada.';
    form.querySelector('[name="reusable"][value="true"]').checked = true;
    form.querySelector('[name="reopened"][value="false"]').checked = true;
    form.querySelector('[name="kb_article"]').value = 'KB-ACC-014';
    form.querySelector('[name="satisfaction"]').value = '5';
    form.querySelector('[name="affected_system"]').value = 'Active Directory';
    form.querySelector('[name="tags"]').value = 'acesso, grupo AD, aprovação';
    $('#fechamento-result').innerHTML = '';
  }
  function bindFechamento() {
    $('#form-fechamento').addEventListener('submit', submitFechamento);
    $('#form-fechamento').addEventListener('reset', () => {
      if (programmaticReset) return;
      setTimeout(() => { updateSubcategories(); $('#fechamento-result').innerHTML = ''; }, 0);
    });
    $('#fc-category').addEventListener('change', () => updateSubcategories());
    $('#btn-fc-exemplo').addEventListener('click', fillClosureExample);
  }

  // ------------------------------------------------------------------ init
  async function init() {
    bindTabs();
    bindBoard();
    bindThreshold();
    bindNovo();
    bindFechamento();
    $('#btn-refresh-painel').addEventListener('click', async () => { await refreshBoard(); renderPainel(); });

    await Promise.allSettled([loadHealth(), loadExamples(), loadOptions()]);
    state.total = (state.health && state.health.n_holdout) || 0;
    setThreshold(DEFAULT_THRESHOLD);
    renderNovoExamples();
    buildClosureForm();
    await refreshBoard();
    showTab(location.hash.slice(1) || 'painel');
    renderPainel();
  }

  document.addEventListener('DOMContentLoaded', init);
})();
