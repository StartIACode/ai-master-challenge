/* Triagem N1-IA / N2 / N3 — single-page UI (vanilla JS, no build, no CDN).
   Consumes the API contract in app/api.py (Task 7). All user-facing text is pt-BR.
   Invariant mirrored from the backend: the AI never answers the customer nor closes a ticket. */
(() => {
  'use strict';

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const TABS = ['painel', 'board', 'operacao', 'politica', 'novo', 'fechamento', 'similaridade'];
  const AUTO = new Set(['Access', 'Storage', 'Hardware']);
  const DEFAULT_THRESHOLD = 0.90;
  const BATCH = 10;
  const AUTO_MS = 3000;
  const MAX_CARDS = 30;
  const PER_CLASS_KEYS = ['0.80', '0.90', '0.95'];

  const DECISION_LABEL = {
    auto_route: 'auto-roteio',
    suggest: 'sugerir fila',
    human_triage: 'triagem humana',
    human_required: 'humano obrigatório',
  };
  const DECISION_LONG = {
    auto_route: 'Auto-roteio (N1-IA): entra na fila da classe com rascunho pronto; o humano responde, edita ou marca "IA errou".',
    suggest: 'Sugerir fila (N2): a IA sugere a fila e o analista confirma antes de entrar; sem rascunho.',
    human_triage: 'Triagem humana (N2): confiança abaixo do limiar ou classe Miscellaneous; o analista decide a fila.',
    human_required: 'Humano obrigatório (N2): sinal de risco no texto; sem rascunho, sem automação.',
  };
  const STATUS_LABEL = { aberto: 'aberto', em_atendimento: 'em atendimento', resolvido: 'resolvido' };
  const RISK_LABEL = {
    legal: 'jurídico', cancel: 'cancelamento', refund: 'reembolso', harassment: 'assédio/ameaça',
    health: 'saúde', vip: 'VIP/enterprise', social: 'canal social', reopened: 'reaberto',
  };
  const ACTION_LABEL = { assume: 'assumido', resolve: 'resolvido', escalate: 'escalado ao N3', ai_wrong: 'marcado como "IA errou"' };

  const state = {
    threshold: DEFAULT_THRESHOLD,
    health: null, metrics: null, policy: null, ds1: null, options: null,
    examples: [], board: null, position: 0, total: 0,
    autoTimer: null, busy: false, currentTab: 'painel', simLoaded: false,
  };

  // ------------------------------------------------------------------ helpers
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const isNum = (x) => typeof x === 'number' && Number.isFinite(x);
  const fmtNum = (x, d = 0) => (isNum(x) ? x.toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d }) : '—');
  const fmtPct = (x, d = 1) => (isNum(x) ? (x * 100).toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d }) + '%' : '—');
  const fmtP = (x) => (isNum(x) ? (x >= 0.995 ? '0,99+' : x.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })) : '—');
  const fmtBRL = (x) => (isNum(x) ? x.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 }) : '—');
  const ratio = (a, b) => (isNum(a) && isNum(b) && b > 0 ? a / b : null);
  const truncate = (s, n) => { const t = String(s || ''); return t.length > n ? t.slice(0, n - 1).trimEnd() + '…' : t; };

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
    const map = { real: ['badge-real', 'REAL'], sim: ['badge-sim', 'SIMULAÇÃO'], ilus: ['badge-ilustrativo', 'EXEMPLO ILUSTRATIVO'] };
    const [cls, label] = map[kind] || map.real;
    return `<span class="badge ${cls}">${label}</span>`;
  }
  function kpi(label, value, sub = '', kind = 'real', gold = false) {
    return `<div class="kpi"><div class="k"><span>${label}</span>${badge(kind)}</div><div class="v${gold ? ' gold' : ''}">${value}</div>${sub ? `<div class="s">${sub}</div>` : ''}</div>`;
  }
  function fact(label, value, src = '') {
    return `<div class="fact"><span>${label}${src ? ` <span class="src">${esc(src)}</span>` : ''}</span><b>${value}</b></div>`;
  }

  function thresholdRow(t) {
    const rows = state.metrics && state.metrics.thresholds;
    if (!rows || !rows.length) return null;
    let best = rows[0];
    for (const r of rows) if (Math.abs(r.t - t) < Math.abs(best.t - t)) best = r;
    return best;
  }
  function perClassKey(t) {
    let best = PER_CLASS_KEYS[0];
    for (const k of PER_CLASS_KEYS) if (Math.abs(Number(k) - t) < Math.abs(Number(best) - t)) best = k;
    return best;
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
    if (name === 'similaridade' && !state.simLoaded) loadSimilaridade('');
    if (name === 'painel') renderPainel();
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
    document.addEventListener('click', (e) => {
      const go = e.target.closest('[data-goto]');
      if (go) { e.preventDefault(); showTab(go.dataset.goto, { focus: true }); }
    });
    window.addEventListener('hashchange', () => showTab(location.hash.slice(1) || 'painel'));
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
      $('#lead-holdout').textContent = h.n_holdout ? fmtNum(h.n_holdout) : '—';
    } catch (err) {
      el.innerHTML = `<span class="dot off"></span>API indisponível: ${esc(err.message)}`;
    }
  }
  async function loadMetrics() {
    const [m, p, d] = await Promise.allSettled([api('/api/metrics'), api('/api/policy'), api('/api/ds1')]);
    state.metrics = m.status === 'fulfilled' ? m.value : null;
    state.policy = p.status === 'fulfilled' ? p.value : null;
    if (Array.isArray(state.policy) && state.policy.length) { // derive AUTO from the API policy (fallback: static set above)
      const fromApi = state.policy.filter(r => r.action === 'auto-roteio com rascunho').map(r => r.category);
      if (fromApi.length) { AUTO.clear(); fromApi.forEach(c => AUTO.add(c)); }
    }
    state.ds1 = d.status === 'fulfilled' ? d.value : null;
    if (m.status === 'rejected') toast('metrics.json indisponível: rode make train', 'err');
  }
  async function loadExamples() {
    try { state.examples = (await api('/api/examples')).examples || []; } catch (_) { state.examples = []; }
  }
  async function loadOptions() {
    try { state.options = await api('/api/closure/options'); } catch (_) { state.options = null; }
  }

  // ------------------------------------------------------------------ 1. painel
  function renderPainel() {
    const c = state.board && state.board.counters;
    const el = $('#kpis');
    if (!c || !c.total) {
      el.innerHTML = kpi('Tickets no replay', '0', 'Rode o replay na aba Board para medir os contadores.') +
        kpi('N1-IA auto-roteado', '—', 'fração que a IA roteou sozinha e ninguém contestou') +
        kpi('N2', '—', 'sugerir fila, triagem ou humano obrigatório') +
        kpi('N3 por escalação humana', '—', 'só chega por clique do analista') +
        kpi('Acerto da IA no replay', '—', 'classe prevista = classe verdadeira') +
        kpi('Overrides "IA errou"', '0', 'marcados por humano');
    } else {
      const bd = c.by_decision || {};
      el.innerHTML =
        kpi('Tickets no replay', fmtNum(c.total), `${state.position ? fmtNum(state.position) : '—'} de ${fmtNum(state.total)} do hold-out servidos`) +
        kpi('N1-IA auto-roteado', fmtPct(ratio(c.n1, c.total)), `${fmtNum(c.n1)} no N1 agora · ${fmtNum(bd.auto_route)} decisões do gate`, 'real', true) +
        kpi('N2', fmtPct(ratio(c.n2, c.total)), `sugerir ${fmtNum(bd.suggest)} · triagem ${fmtNum(bd.human_triage)} · obrigatório ${fmtNum(bd.human_required)}`) +
        kpi('N3 por escalação humana', fmtPct(ratio(c.n3, c.total)), `${fmtNum(c.n3)} escalados por clique`) +
        kpi('Acerto da IA no replay', fmtPct(ratio(c.ai_correct, c.ai_evaluated)), `${fmtNum(c.ai_correct)} de ${fmtNum(c.ai_evaluated)} · nos auto-roteados: ${fmtPct(ratio(c.auto_correct, c.auto_evaluated))}`) +
        kpi('Overrides "IA errou"', fmtNum(c.ai_wrong), `${fmtNum(c.resolved)} resolvidos por humano`);
    }

    const d = state.ds1;
    $('#card-tma').innerHTML = d ? `
      <p class="hint">Dataset 1 (${fmtNum(d.n_rows)} linhas) é gerado por script: não dá para medir onde o suporte perde tempo.</p>
      ${fact('Janela de todos os timestamps', `${fmtNum(d.time_window_hours, 1)} h`)}
      ${fact('"Resolvidos" antes da 1ª resposta', fmtPct(d.share_negative_resolution))}
      ${fact('Descrições com placeholder', fmtPct(d.placeholder_share, 0))}
      ${fact('Primeiras frases distintas', fmtNum(d.first_sentence_distinct))}
      ${fact('Satisfação × canal/prioridade/tipo', `p ≥ ${fmtNum(Math.min(...(d.association_tests || []).filter((t) => t.variable !== 'frt_hour').map((t) => t.p_value)), 2)}`)}
      <p class="tiny">${esc(d.verdict || '')}</p>
      <p class="tiny">Dataset 2 não tem campo de resolução nem tempo. Fonte: artifacts/ds1_metrics.json.</p>`
      : '<p class="hint">artifacts/ds1_metrics.json indisponível.</p>';

    const m = state.metrics;
    const nc = d && d.negative_control;
    $('#card-controle').innerHTML = (m && nc) ? `
      <p class="hint">O mesmo pipeline (TF-IDF + regressão logística, 5-fold) aplicado aos dois datasets.</p>
      ${fact('Dataset 1: descrição → tipo', fmtPct(nc.accuracy), `chance ${fmtPct(nc.chance, 0)}, majoritária ${fmtPct(nc.majority_share)}`)}
      ${fact('Dataset 2: texto → classe (hold-out)', fmtPct(m.accuracy), `5-fold ${fmtPct(m.cv5 && m.cv5.accuracy)}`)}
      <p class="tiny">No Dataset 1 o texto não carrega sinal: as classes são sorteadas. No Dataset 2 o texto prevê a classe. É por isso que a triagem se prova no segundo e o primeiro vira controle negativo.</p>`
      : '<p class="hint">Artefatos indisponíveis.</p>';

    $('#card-modelo').innerHTML = m ? `
      ${fact('Tickets (após desduplicação)', `${fmtNum(m.n_total - m.n_dedup_removed)}`, `${fmtNum(m.n_dedup_removed)} duplicados removidos`)}
      ${fact('Treino / hold-out', `${fmtNum(m.n_train)} / ${fmtNum(m.n_holdout)}`, 'split 80/20 estratificado, seed 42')}
      ${fact('Acurácia no hold-out', fmtPct(m.accuracy))}
      ${fact('Macro-F1', fmtPct(m.macro_f1))}
      ${fact('Erro de calibração (ECE)', fmtPct(m.ece))}
      ${fact('Acerto do 1º vizinho (similaridade)', fmtPct(m.similarity && m.similarity.nn_accuracy))}
      <p class="tiny">TF-IDF (1,2) + regressão logística; similaridade por cosseno. Fonte: artifacts/metrics.json.</p>`
      : '<p class="hint">artifacts/metrics.json indisponível.</p>';

    const r = thresholdRow(state.threshold);
    $('#card-gate').innerHTML = r ? `
      <p class="hint">Limiar <b>${fmtP(r.t)}</b>, medido no hold-out (${fmtNum(m.n_holdout)} tickets). <button type="button" class="linkbtn" data-goto="operacao">ajustar</button></p>
      ${fact('Confiança ≥ limiar (cobertura bruta)', fmtPct(r.coverage), `${fmtNum(r.n_covered)} tickets`)}
      ${fact('Acerto nos cobertos', fmtPct(r.acc_covered), `${fmtNum(r.n_errors_covered)} erros`)}
      ${fact('Auto-roteável após política (cobertura útil)', fmtPct(r.useful_coverage), `${fmtNum(r.n_useful)} tickets`)}
      ${fact('Acerto nos auto-roteáveis', fmtPct(r.useful_acc), `${fmtNum(r.n_errors_useful)} erros`)}
      ${fact('Acerto no restante (vai ao humano)', fmtPct(r.acc_rest), `${fmtNum(r.n_rest)} tickets`)}`
      : '<p class="hint">Curvas por limiar indisponíveis.</p>';
  }

  // ------------------------------------------------------------------ 2. board
  function ticketCard(t) {
    const ok = t.true_category === t.category;
    const text = t.text || '';
    const long = text.length > 220;
    const flags = (t.risk_flags || []).map((f) => `<span class="chip chip-danger">${esc(RISK_LABEL[f] || f)}</span>`).join(' ');
    const top3 = (t.top3 || []).map((x) => `${esc(x.category)} ${fmtP(x.p)}`).join(' · ');
    const nb = (t.neighbors || []).map((n) =>
      `<li><span class="sim">${fmtP(n.similarity)}</span> <span class="cls">${esc(n.category || '?')}</span> <span class="ex">${esc(n.excerpt || '(sem trecho)')}</span></li>`).join('');
    const draft = t.draft
      ? `<details class="sub"><summary>Rascunho (macro; LLM desligado)</summary><pre class="draft">${esc(t.draft)}</pre><p class="tiny">Humano revisa, edita e envia. A IA não responde ao cliente.</p></details>`
      : `<p class="tiny">Sem rascunho: ${t.decision === 'auto_route' ? 'classe sem macro' : 'só auto-roteio recebe rascunho'}.</p>`;
    return `<article class="ticket dec-${esc(t.decision)}" data-id="${esc(t.id)}" aria-label="Ticket ${esc(t.id)}">
      <header class="ticket-head">
        <span class="tid">${esc(t.id)}</span>
        <span class="badge badge-dec">${esc(DECISION_LABEL[t.decision] || t.decision)}</span>
        <span class="chip chip-status status-${esc(t.status)}">${esc(STATUS_LABEL[t.status] || t.status)}</span>
        ${t.ai_wrong ? '<span class="chip chip-danger">IA errou</span>' : ''}
      </header>
      <p class="ticket-text${long ? ' clamp' : ''}">${esc(text)}</p>
      ${long ? '<button type="button" class="linkbtn" data-toggle="text">ver tudo</button>' : ''}
      <dl class="meta">
        <div><dt>Classe prevista</dt><dd>${esc(t.category)} <b>p ${fmtP(t.confidence)}</b></dd></div>
        <div><dt>Classe verdadeira</dt><dd>${esc(t.true_category)} <span class="${ok ? 'ok' : 'bad'}" title="${ok ? 'acertou' : 'errou'}">${ok ? '✓' : '✗'}</span></dd></div>
        <div><dt>Fila · nível</dt><dd>${esc(t.queue)} · ${esc(t.level)}</dd></div>
        <div><dt>Responsável</dt><dd>${t.assigned_to ? esc(t.assigned_to) : '—'} ${badge('sim').replace('SIMULAÇÃO', 'SIMULADO')}</dd></div>
      </dl>
      ${top3 ? `<p class="top3">Top-3 classes: ${top3}</p>` : ''}
      ${flags ? `<p class="flags">Risco: ${flags}</p>` : ''}
      <p class="reason"><b>Decisão:</b> ${esc(t.reason)}</p>
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

  function renderBoard() {
    const snap = state.board;
    if (!snap) return;
    for (const lvl of ['N1', 'N2', 'N3']) {
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
    } catch (err) {
      toast(`Board indisponível: ${err.message}`, 'err');
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

  // ------------------------------------------------------------------ 3. ponto de operação
  function chartSVG(rows, t) {
    const W = 640, H = 260, pl = 44, pr = 16, pt = 14, pb = 34;
    const x = (v) => pl + ((v - 0.5) / (0.99 - 0.5)) * (W - pl - pr);
    const y = (v) => pt + (1 - v) * (H - pt - pb);
    const path = (key) => rows.map((r, i) => `${i ? 'L' : 'M'}${x(r.t).toFixed(1)} ${y(r[key]).toFixed(1)}`).join(' ');
    const grid = [0, 0.25, 0.5, 0.75, 1].map((v) =>
      `<line class="grid" x1="${pl}" x2="${W - pr}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}"/><text x="${pl - 6}" y="${(y(v) + 4).toFixed(1)}" text-anchor="end">${fmtPct(v, 0)}</text>`).join('');
    const xt = [0.5, 0.6, 0.7, 0.8, 0.9, 0.99].map((v) =>
      `<text x="${x(v).toFixed(1)}" y="${H - pb + 16}" text-anchor="middle">${fmtP(v)}</text>`).join('');
    return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Cobertura e acerto em função do limiar; marcador no limiar atual ${fmtP(t)}">
      ${grid}${xt}
      <line class="axis" x1="${pl}" x2="${W - pr}" y1="${y(0)}" y2="${y(0)}"/>
      <line class="axis" x1="${pl}" x2="${pl}" y1="${y(0)}" y2="${y(1)}"/>
      <text x="${(W + pl - pr) / 2}" y="${H - 4}" text-anchor="middle">limiar de confiança</text>
      <path class="l-cov" d="${path('coverage')}"/>
      <path class="l-useful" d="${path('useful_coverage')}"/>
      <path class="l-acc" d="${path('acc_covered')}"/>
      <path class="l-useful-acc" d="${path('useful_acc')}"/>
      <line class="marker" x1="${x(t).toFixed(1)}" x2="${x(t).toFixed(1)}" y1="${y(0)}" y2="${y(1)}"/>
    </svg>
    <div class="chart-legend">
      <span><i style="border-color:var(--gold)"></i>cobertura bruta (confiança ≥ limiar)</span>
      <span><i style="border-color:var(--navy)"></i>cobertura útil (após política)</span>
      <span><i style="border-color:var(--ok)"></i>acerto nos cobertos</span>
      <span><i style="border-color:var(--ok);border-top-style:dashed"></i>acerto nos auto-roteáveis</span>
      <span><i style="border-color:var(--danger);border-top-style:dashed"></i>limiar atual</span>
    </div>`;
  }

  function calcInputs() {
    const num = (id, fallback) => { const v = parseFloat($(id).value); return Number.isFinite(v) && v >= 0 ? v : fallback; };
    return { V: num('#calc-tickets', 2500), mt: num('#calc-min', 3), h: num('#calc-hora', 41), me: num('#calc-erro', 10) };
  }
  function scenario(row, inp) {
    const c = row.useful_coverage, e = 1 - row.useful_acc;
    const auto = inp.V * c;
    const gross = auto * inp.mt / 60;
    const rework = auto * e * inp.me / 60;
    const net = gross - rework;
    return { t: row.t, c, e, auto, gross, rework, net, brl: net * inp.h };
  }
  function renderCalc() {
    const out = $('#calc-out');
    const row = thresholdRow(state.threshold);
    if (!row) { out.innerHTML = '<p class="hint">Curvas por limiar indisponíveis.</p>'; return; }
    const inp = calcInputs();
    const s = scenario(row, inp);
    const others = [0.80, 0.90, 0.95].map((t) => thresholdRow(t)).filter(Boolean).map((r) => scenario(r, inp));
    out.innerHTML = `
      <div class="kpis" style="margin-top:12px">
        ${kpi('Auto-roteados por mês', fmtNum(s.auto), `${fmtNum(inp.V)} × cobertura útil ${fmtPct(s.c)}`, 'sim')}
        ${kpi('Horas de triagem poupadas', fmtNum(s.gross, 1) + ' h', `${fmtNum(inp.mt, 1)} min por ticket`, 'sim')}
        ${kpi('Horas de retrabalho por erro', fmtNum(s.rework, 1) + ' h', `taxa de erro ${fmtPct(s.e)} × ${fmtNum(inp.me)} min`, 'sim')}
        ${kpi('Economia líquida por mês', fmtBRL(s.brl), `${fmtNum(s.net, 1)} h × ${fmtBRL(inp.h)}/h`, 'sim', true)}
      </div>
      <div class="table-wrap" style="margin-top:12px"><table>
        <thead><tr><th>Cenário</th><th class="num">Limiar</th><th class="num">Cobertura útil</th><th class="num">Erro</th><th class="num">Auto/mês</th><th class="num">Horas líquidas</th><th class="num">R$/mês</th></tr></thead>
        <tbody>${others.map((o, i) => `<tr${Math.abs(o.t - state.threshold) < 1e-6 ? ' style="font-weight:700"' : ''}><td>${['afrouxado', 'recomendado', 'conservador'][i]}</td><td class="num">${fmtP(o.t)}</td><td class="num">${fmtPct(o.c)}</td><td class="num">${fmtPct(o.e)}</td><td class="num">${fmtNum(o.auto)}</td><td class="num">${fmtNum(o.net, 1)}</td><td class="num">${fmtBRL(o.brl)}</td></tr>`).join('')}</tbody>
      </table></div>
      <p class="tiny">Fórmula: horas líquidas = V·c·m<sub>t</sub>/60 − V·c·e·m<sub>e</sub>/60, com c (cobertura útil) e e (1 − acerto nos auto-roteáveis) medidos no hold-out para cada limiar. O custo de API é zero: classificação e similaridade rodam localmente. Não inclui o ganho de N2 sobre tickets só sugeridos.</p>`;
  }

  function renderOperacao() {
    const row = thresholdRow(state.threshold);
    const el = $('#op-kpis');
    if (!row) {
      el.innerHTML = '<p class="hint">artifacts/metrics.json indisponível: rode make train.</p>';
      $('#op-chart').innerHTML = '';
      renderCalc();
      return;
    }
    const inp = calcInputs();
    el.innerHTML =
      kpi('Cobertura bruta', fmtPct(row.coverage), `${fmtNum(row.n_covered)} tickets com confiança ≥ ${fmtP(row.t)}`) +
      kpi('Cobertura útil', fmtPct(row.useful_coverage), `${fmtNum(row.n_useful)} auto-roteáveis (classes Access/Storage/Hardware, sem risco)`, 'real', true) +
      kpi('Acerto nos cobertos', fmtPct(row.acc_covered), `${fmtNum(row.n_errors_covered)} erros em ${fmtNum(row.n_covered)}`) +
      kpi('Acerto nos auto-roteáveis', fmtPct(row.useful_acc), `${fmtNum(row.n_errors_useful)} erros em ${fmtNum(row.n_useful)}`) +
      kpi('Acerto no restante', fmtPct(row.acc_rest), `${fmtNum(row.n_rest)} tickets vão ao humano`) +
      kpi('Tickets/mês auto-roteados', fmtNum(inp.V * row.useful_coverage), `${fmtNum(inp.V)} tickets/mês × cobertura útil`, 'sim');
    $('#op-chart').innerHTML = chartSVG(state.metrics.thresholds, row.t);
    renderCalc();
  }

  function setThreshold(v) {
    const t = Math.min(0.99, Math.max(0.5, Math.round(v * 100) / 100));
    state.threshold = t;
    $('#threshold').value = t.toFixed(2);
    $('#threshold-out').value = fmtP(t);
    for (const el of $$('.threshold-readout')) el.textContent = fmtP(t);
    renderOperacao();
    renderPolitica();
    if (state.currentTab === 'painel') renderPainel();
  }
  function bindOperacao() {
    $('#threshold').addEventListener('input', (e) => setThreshold(parseFloat(e.target.value)));
    for (const id of ['#calc-tickets', '#calc-min', '#calc-hora', '#calc-erro']) {
      $(id).addEventListener('input', () => renderOperacao());
    }
  }

  // ------------------------------------------------------------------ 4. política por classe
  function renderPolitica() {
    const el = $('#policy-table');
    const note = $('#policy-note');
    if (!state.policy) { el.innerHTML = '<p class="hint" style="padding:12px">artifacts/policy.json indisponível.</p>'; return; }
    const m = state.metrics;
    const key = perClassKey(state.threshold);
    const at = (m && m.per_class_at && m.per_class_at[key]) || {};
    const pc = (m && m.per_class) || {};
    const counts = (m && m.class_counts) || {};
    const rows = state.policy.map((p) => {
      const a = at[p.category] || {};
      const c = pc[p.category] || {};
      const cls = AUTO.has(p.category) ? 'act-auto' : (p.category === 'Miscellaneous' ? 'act-human' : 'act-suggest');
      return `<tr class="${cls}">
        <td><b>${esc(p.category)}</b></td>
        <td class="num">${fmtNum(counts[p.category])}</td>
        <td class="num">${fmtPct(c.precision)}</td>
        <td class="num">${fmtPct(c.recall)}</td>
        <td class="num">${fmtPct(a.coverage)}</td>
        <td class="num">${fmtPct(a.acc)}${isNum(a.n_errors) ? ` <span class="tiny">(${fmtNum(a.n_errors)} erros)</span>` : ''}</td>
        <td>${esc(p.action)}</td>
        <td>${esc(p.reason)}</td>
      </tr>`;
    }).join('');
    el.innerHTML = `<table>
      <thead><tr><th>Classe</th><th class="num">Volume</th><th class="num">Precisão</th><th class="num">Recall</th><th class="num">Cobertura @ ${fmtP(Number(key))}</th><th class="num">Acerto @ ${fmtP(Number(key))}</th><th>Ação</th><th>Motivo</th></tr></thead>
      <tbody>${rows}</tbody></table>`;
    note.innerHTML = `Volume, precisão e recall do hold-out (metrics.per_class). Cobertura e acerto por classe estão gravados para 0,80 / 0,90 / 0,95; a tabela mostra <b>${fmtP(Number(key))}</b>, o mais próximo do limiar atual (${fmtP(state.threshold)}). Cobertura = fração dos tickets previstos na classe com confiança ≥ limiar; acerto = precisão dentro dessa fração.`;
  }

  // ------------------------------------------------------------------ 5. novo ticket
  function renderNovoExamples() {
    const el = $('#novo-examples');
    if (!state.examples.length) { el.innerHTML = '<p class="hint">Exemplos indisponíveis (hold-out ausente).</p>'; return; }
    el.innerHTML = state.examples.map((e, i) =>
      `<button type="button" class="example" data-example="${i}"><span class="cls">exemplo real ${i + 1} · classe verdadeira: ${esc(e.true_category)}</span><span class="ex">${esc(truncate(e.text, 110))}</span></button>`).join('');
  }

  function renderTriage(r, text) {
    const flags = (r.risk_flags || []).map((f) => `<span class="chip chip-danger">${esc(RISK_LABEL[f] || f)}</span>`).join(' ');
    const bars = (r.top3 || []).map((x) => `<div class="bar"><span>${esc(x.category)}</span><div class="track"><div class="fill" style="width:${Math.max(1, x.p * 100).toFixed(1)}%"></div></div><span class="n">${fmtP(x.p)}</span></div>`).join('');
    const nb = (r.neighbors || []).length
      ? `<ol class="nb">${r.neighbors.map((n) => `<li><span class="sim">${fmtP(n.similarity)}</span> <span class="cls">${esc(n.category)}</span> <span class="ex">${esc(n.excerpt)}</span></li>`).join('')}</ol>`
      : '<p class="hint">Sem vizinhos: o texto não tem termos conhecidos pelo vocabulário do modelo.</p>';
    const draft = r.draft
      ? `<pre class="draft">${esc(r.draft)}</pre><p class="tiny">Macro por classe (LLM desligado). Humano revisa, edita e envia.</p>`
      : `<p class="hint">Sem rascunho: ${r.decision === 'human_required' ? 'sinal de risco exige humano' : r.decision === 'suggest' ? 'classe sensível: N2 confirma a fila antes' : 'só auto-roteio recebe rascunho'}.</p>`;
    $('#novo-result').innerHTML = `
      <div class="result-dec dec-${esc(r.decision)}">
        <div class="sim-head"><span class="big"><span class="badge badge-dec">${esc(DECISION_LABEL[r.decision] || r.decision)}</span> nível ${esc(r.level)} · fila <b>${esc(r.queue)}</b></span>${badge('real')}</div>
        <p style="margin:6px 0 0">${esc(DECISION_LONG[r.decision] || '')}</p>
        <p class="reason" style="margin-top:6px"><b>Motivo:</b> ${esc(r.reason)}</p>
        ${flags ? `<p class="flags">Sinais de risco: ${flags}</p>` : ''}
      </div>
      <div class="cards-2" style="margin-top:12px">
        <article class="card"><header class="card-head"><h3>Classe prevista: ${esc(r.category)} · p ${fmtP(r.confidence)}</h3>${badge('real')}</header><div class="bars">${bars}</div><p class="tiny">Limiar aplicado: ${fmtP(state.threshold)}. Texto triado (${text.length} caracteres) normalizado no servidor.</p></article>
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

  // ------------------------------------------------------------------ 6. fechamento padronizado
  function fillSelect(sel, values, placeholder) {
    sel.innerHTML = `<option value="">${esc(placeholder)}</option>` + values.map((v) => `<option value="${esc(v)}">${esc(v)}</option>`).join('');
  }
  function buildClosureForm() {
    const o = state.options;
    if (!o) {
      $('#fechamento-result').innerHTML = '<div class="notice warn">Listas do formulário indisponíveis (/api/closure/options). A validação continua na API.</div>';
      return;
    }
    fillSelect($('#fc-category'), o.categories || [], '— escolha —');
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
      ['ID na base', k.id], ['Ticket', k.ticket_id || '—'], ['Categoria', `${k.category} › ${k.subcategory}`],
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

  // ------------------------------------------------------------------ 7. similaridade após padronização
  const APPLY_TIP = 'requer similaridade ≥ 0,90, classe auto-roteável e base padronizada';
  function simCard(s, i) {
    const c = s.closure;
    const conds = [
      { ok: isNum(s.similarity) && s.similarity >= 0.90, label: `similaridade ≥ 0,90 (medida: ${fmtP(s.similarity)})` },
      { ok: AUTO.has(s.category), label: `classe auto-roteável (${s.category || '?'})` },
      { ok: !!(c && c.reusable), label: 'fechamento marcado como reutilizável' },
      { ok: false, label: 'base padronizada existente (ainda não: fechamento ilustrativo)' },
    ];
    const closure = c ? `
      <div class="sim-block">
        <h4>Fechamento padronizado ${badge('ilus')}</h4>
        <dl class="dl">
          <dt>Categoria</dt><dd>${esc(c.category)} › ${esc(c.subcategory)}</dd>
          <dt>Causa raiz</dt><dd>${esc(c.root_cause)}</dd>
          <dt>Ação</dt><dd><pre>${esc(c.resolution_steps)}</pre></dd>
          <dt>Nível · tempo</dt><dd>${esc(c.resolved_by_level)} · ${fmtNum(c.time_spent_min)} min</dd>
          <dt>Resposta reutilizável</dt><dd>${c.customer_reply ? esc(c.customer_reply) : '—'} ${c.reusable ? '<span class="ok">sim</span>' : '<span class="bad">não</span>'}</dd>
          <dt>Artigo</dt><dd>${esc(c.kb_article || '—')}</dd>
        </dl>
      </div>` : '<div class="sim-block"><p class="hint">Sem fechamento ilustrativo para esta classe.</p></div>';
    return `<article class="card sim-card">
      <div class="sim-head"><span class="sim-value">${fmtP(s.similarity)}</span>${badge('real')}</div>
      <p class="tiny">similaridade por cosseno · ticket de treino ${fmtNum(s.id)} · classe <b>${esc(s.category || '?')}</b></p>
      <p class="ticket-text">${esc(s.excerpt || '(sem trecho)')}</p>
      ${closure}
      <div class="sim-block">
        <span class="tip" data-tip="${esc(APPLY_TIP)}" tabindex="0"><button type="button" class="btn btn-primary" disabled aria-describedby="sim-why-${i}">Aplicar tratativa sugerida</button></span>
        <p class="tiny" id="sim-why-${i}">Desabilitado: ${esc(APPLY_TIP)}.</p>
        <ul class="conds">${conds.map((x) => `<li class="${x.ok ? 'pass' : ''}">${esc(x.label)}</li>`).join('')}</ul>
      </div>
    </article>`;
  }
  function renderSimilaridade(data) {
    const t = data.ticket;
    $('#sim-note').innerHTML = `${badge('ilus')} ${esc(data.note || '')}`;
    $('#sim-result').innerHTML = `
      <article class="card">
        <header class="card-head"><h3>Ticket de entrada · ${esc(t.id)}</h3>${badge('real')}</header>
        <p class="ticket-text">${esc(t.text)}</p>
        <p class="tiny">Classe prevista pelo modelo: <b>${esc(t.category)}</b>. Os 3 similares abaixo vêm do conjunto de treino; a similaridade é real, o fechamento é ilustrativo.</p>
      </article>
      <div class="sim-grid" style="margin-top:12px">${(data.similar || []).map(simCard).join('')}</div>
      <p class="hint">Regra da proposta: "Aplicar tratativa sugerida" só habilita com similaridade ≥ 0,90 <b>e</b> classe auto-roteável <b>e</b> fechamento reutilizável, sobre uma base padronizada. Mesmo então, o humano aplica e fecha; a IA prepara.</p>`;
  }
  async function loadSimilaridade(ticketId) {
    const el = $('#sim-result');
    el.innerHTML = '<p class="hint">carregando…</p>';
    try {
      const data = await api(`/api/kb/example${ticketId ? `?ticket_id=${encodeURIComponent(ticketId)}` : ''}`);
      state.simLoaded = true;
      renderSimilaridade(data);
    } catch (err) {
      el.innerHTML = `<div class="notice err">Não foi possível carregar: ${esc(err.message)}</div>`;
    }
  }
  function bindSimilaridade() {
    const sel = $('#sim-select');
    sel.innerHTML = state.examples.length
      ? state.examples.map((e, i) => `<option value="${esc(e.id)}">exemplo ${i + 1} · ${esc(e.id)} · ${esc(e.true_category)}</option>`).join('')
      : '<option value="">primeiro exemplo</option>';
    sel.addEventListener('change', () => { $('#sim-id').value = ''; loadSimilaridade(sel.value); });
    $('#btn-sim-load').addEventListener('click', () => loadSimilaridade($('#sim-id').value.trim() || sel.value));
    $('#sim-id').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); loadSimilaridade($('#sim-id').value.trim() || sel.value); } });
  }

  // ------------------------------------------------------------------ init
  async function init() {
    bindTabs();
    bindBoard();
    bindOperacao();
    bindNovo();
    bindFechamento();
    $('#btn-refresh-painel').addEventListener('click', async () => { await refreshBoard(); renderPainel(); });

    await Promise.allSettled([loadHealth(), loadMetrics(), loadExamples(), loadOptions()]);
    state.total = (state.health && state.health.n_holdout) || 0;
    setThreshold(DEFAULT_THRESHOLD);
    renderNovoExamples();
    buildClosureForm();
    bindSimilaridade();
    await refreshBoard();
    showTab(location.hash.slice(1) || 'painel');
    renderPainel();
  }

  document.addEventListener('DOMContentLoaded', init);
})();
