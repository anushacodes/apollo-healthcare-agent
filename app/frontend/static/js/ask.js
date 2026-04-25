'use strict';

/**
 * ask.js — Agentic RAG chat for the Ask tab.
 * WebSocket → /api/rag/stream/{patient_id}
 * Streams thinking + result events per node; renders live reasoning trace.
 */

window.AskController = (function () {
  let _patient = null;
  let _ws      = null;
  let _busy    = false;

  /* ── Public ──────────────────────────────────────────────── */
  function init(patient) {
    _patient = patient;
    _renderShell();
  }

  /* ── Shell ───────────────────────────────────────────────── */
  function _renderShell() {
    const panel = document.getElementById('tab-ask');
    if (!panel) return;
    panel.innerHTML = `
      <div class="ask-layout">

        <div class="ask-header">
          <div class="ask-header-info">
            <h2 class="ask-title">Ask the Clinical Agent</h2>
            <p class="ask-sub">
              Answers grounded in patient documents, PubMed literature, and live
              clinical web search. Every claim is cited and evaluated before delivery.
            </p>
          </div>
          <div class="ask-badges">
            <span class="ask-badge">RAG</span>
            <span class="ask-badge">PubMed</span>
            <span class="ask-badge">Tavily</span>
            <span class="ask-badge">Eval Gate</span>
          </div>
        </div>

        <div class="ask-messages" id="askMessages">
          <div class="ask-welcome" id="askWelcome">
            <p>Ask anything about this patient — their records, lab trends, treatment
               options, or relevant clinical guidelines.</p>
            <div class="ask-suggestion-grid" id="askSuggestions">
              <button class="ask-suggestion" data-q="What are the key concerns for this patient?">Key concerns</button>
              <button class="ask-suggestion" data-q="Summarise the most recent lab abnormalities.">Lab abnormalities</button>
              <button class="ask-suggestion" data-q="What is the current standard of care for the primary diagnosis?">Standard of care</button>
              <button class="ask-suggestion" data-q="Are there any drug interaction risks in the current medication list?">Drug interactions</button>
              <button class="ask-suggestion" data-q="What monitoring is recommended for the current treatments?">Treatment monitoring</button>
              <button class="ask-suggestion" data-q="What are the latest clinical trial options for this diagnosis?">Clinical trials</button>
            </div>
          </div>
        </div>

        <form class="ask-input-row" id="askForm" autocomplete="off">
          <input
            type="text"
            id="askInput"
            class="ask-input"
            placeholder="Ask about this patient…"
            maxlength="500"
          >
          <button type="submit" class="ask-send-btn" id="askSendBtn" title="Send">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24"
                 fill="none" stroke="currentColor" stroke-width="2.5"
                 stroke-linecap="round" stroke-linejoin="round">
              <line x1="22" y1="2" x2="11" y2="13"/>
              <polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          </button>
        </form>

      </div>
    `;

    document.getElementById('askForm').addEventListener('submit', e => {
      e.preventDefault();
      _send();
    });

    // Use event delegation for dynamically generated suggestions (follow-ups)
    document.getElementById('askMessages').addEventListener('click', e => {
      const btn = e.target.closest('.ask-suggestion');
      if (btn) {
        const inp = document.getElementById('askInput');
        inp.value = btn.dataset.q;
        inp.focus();
        _send();
      }
    });
  }

  /* ── Send ────────────────────────────────────────────────── */
  function _send() {
    if (_busy) return;
    const input = document.getElementById('askInput');
    const q = input.value.trim();
    if (!q) return;
    input.value = '';
    _appendUserBubble(q);
    _streamAnswer(q);
  }

  /* ── User bubble ─────────────────────────────────────────── */
  function _appendUserBubble(text) {
    const msgs = document.getElementById('askMessages');
    const el = document.createElement('div');
    el.className = 'ask-msg user';
    el.innerHTML = `<div class="ask-bubble user-bubble">${_esc(text)}</div>`;
    msgs.appendChild(el);
    _scrollBottom();
  }

  /* ── Stream ──────────────────────────────────────────────── */
  function _streamAnswer(question) {
    _busy = true;
    _setBusy(true);

    const patientId = _patient?.patient_id || 'unknown';
    const caseKey   = _patient?._caseKey || null;

    // Create agent response container
    const msgs = document.getElementById('askMessages');
    const wrap = document.createElement('div');
    wrap.className = 'ask-msg agent';
    const uid = `ag_${Date.now()}`;
    wrap.innerHTML = `
      <div class="ask-agent-wrap" id="${uid}">
        <div class="ask-trace" id="${uid}_trace"></div>
        <div class="ask-answer" id="${uid}_answer" style="display:none;"></div>
      </div>`;
    msgs.appendChild(wrap);
    _scrollBottom();

    const traceEl  = document.getElementById(`${uid}_trace`);
    const answerEl = document.getElementById(`${uid}_answer`);

    const wsUrl = `ws://${location.host}/api/rag/stream/${patientId}`;
    _ws = new WebSocket(wsUrl);

    _ws.onopen = () => _ws.send(JSON.stringify({ question, case_key: caseKey }));

    _ws.onmessage = e => {
      let evt;
      try { evt = JSON.parse(e.data); } catch { return; }

      const { type, node, message, data } = evt;

      if (type === 'thinking') {
        _addTrace(traceEl, node, message, 'thinking');
      } else if (type === 'result') {
        _addTrace(traceEl, node, message, 'result', data);
      } else if (type === 'done') {
        _renderAnswer(answerEl, traceEl, data, uid);
        _done();
      } else if (type === 'patch_eval') {
        _patchEval(uid, data);
      } else if (type === 'patch_followups') {
        _patchFollowUps(uid, data);
        _ws.close();
      } else if (type === 'error') {
        _addTrace(traceEl, 'error', message || 'Unknown error', 'error');
        _done();
      }
      _scrollBottom();
    };

    _ws.onerror = () => {
      _addTrace(traceEl, 'error', 'WebSocket error — is the server running?', 'error');
      _done();
    };
    _ws.onclose = () => { _ws = null; };
  }

  function _done() {
    _busy = false;
    _setBusy(false);
  }

  /* ── Trace ───────────────────────────────────────────────── */
  const NODE_LABELS = {
    query_router:      'Query Router',
    patient_retriever: 'Patient Docs',
    research_fetcher:  'PubMed',
    web_search:        'Web Search',
    context_assembler: 'Assembler',
    sufficiency_judge: 'Coverage Check',
    generator:         'Generator',
    eval_agent:        'Eval Agent',
    follow_up_agent:   'Follow-Up Agent',
    cache:             'Cache',
    error:             'Error',
  };

  function _addTrace(container, node, message, type, data) {
    const label = NODE_LABELS[node] || node;
    const icon  = { thinking: '⟳', result: '✓', error: '✗' }[type] || '·';

    let pills = '';
    if (data && type === 'result') {
      if (data.route)              pills += `<span class="trace-pill">${data.route}</span>`;
      if (data.chunk_count != null) pills += `<span class="trace-pill">${data.chunk_count} chunks</span>`;
      if (data.paper_count != null) pills += `<span class="trace-pill">${data.paper_count} papers</span>`;
      if (data.cached)             pills += `<span class="trace-pill pill-good">⚡ cached</span>`;
      if (data.faithfulness != null) {
        const pct = Math.round(data.faithfulness * 100);
        pills += `<span class="trace-pill ${pct>=90?'pill-good':pct>=70?'pill-warn':'pill-bad'}">Faith ${pct}%</span>`;
      }
      if (data.hallucination_detected != null)
        pills += data.hallucination_detected
          ? `<span class="trace-pill pill-bad">⚠ hallucination</span>`
          : `<span class="trace-pill pill-good">✓ verified</span>`;
    }

    container.insertAdjacentHTML('beforeend', `
      <div class="trace-entry trace-${type}">
        <span class="trace-icon">${icon}</span>
        <span class="trace-node">${label}</span>
        <span class="trace-msg">${_esc(message)}</span>
        ${pills ? `<span class="trace-pills">${pills}</span>` : ''}
      </div>`);
  }

  /* ── Final answer ────────────────────────────────────────── */
  function _renderAnswer(answerEl, traceEl, data, uid) {
    const { final_response='', citations=[], eval_scores={}, is_refusal=false } = data;

    // Collapse trace
    traceEl.style.transition = 'max-height 0.35s ease';
    traceEl.style.overflow   = 'hidden';
    traceEl.style.maxHeight  = traceEl.scrollHeight + 'px';
    requestAnimationFrame(() => { traceEl.style.maxHeight = '0'; });

    // Toggle button
    const toggle = document.createElement('button');
    toggle.className   = 'trace-toggle';
    toggle.textContent = 'Show reasoning ▾';
    let open = false;
    toggle.addEventListener('click', () => {
      open = !open;
      traceEl.style.maxHeight = open ? (traceEl.scrollHeight + 200) + 'px' : '0';
      toggle.textContent = open ? 'Hide reasoning ▴' : 'Show reasoning ▾';
    });

    answerEl.style.display = '';

    if (is_refusal) {
      answerEl.innerHTML = `
        <div class="ask-refusal">
          <div class="ask-refusal-icon">🔍</div>
          <div class="ask-refusal-body">
            <strong>Sources still indexing</strong>
            <p>PubMed abstracts are being embedded into the vector store.
               This usually takes 10–30 seconds on first run.</p>
            <p>Try again in a moment, or upload patient documents in the <strong>Documents</strong> tab to get answers grounded in actual patient data.</p>
          </div>
        </div>`;
      answerEl.insertAdjacentElement('afterbegin', toggle);
      return;
    }

    const html = _insertCitations(final_response, citations);

    answerEl.innerHTML = `
      <div class="ask-answer-text"><p>${html}</p></div>
      ${_citationList(citations)}
      <div class="eval-pills-slot" id="${uid}_eval"></div>
      <div class="followups-slot"  id="${uid}_followups"></div>`;

    answerEl.insertAdjacentElement('afterbegin', toggle);
  }

  /* ── Patch: eval scores ──────────────────────────────────── */
  function _patchEval(uid, data) {
    const slot = document.getElementById(`${uid}_eval`);
    if (!slot) return;
    const evalHtml = _evalPills(data.eval_scores);
    slot.innerHTML = evalHtml;
    // If there's a faithfulness warning in final_response, update the text
    if (data.final_response) {
      const textEl = document.querySelector(`#${uid}_answer .ask-answer-text p`);
      if (textEl) {
        const citations = Array.from(
          document.querySelectorAll(`#${uid}_answer .citation-card`)
        ).map((_, i) => ({ ref: i + 1 }));
        textEl.innerHTML = _insertCitations(data.final_response, citations);
      }
    }
  }

  /* ── Patch: follow-up questions ──────────────────────────── */
  function _patchFollowUps(uid, data) {
    const slot = document.getElementById(`${uid}_followups`);
    if (!slot) return;
    slot.innerHTML = _followUps(data.follow_ups);
    _scrollBottom();
  }

  function _followUps(followUps) {
    if (!followUps || !followUps.length) return '';
    return `
      <div class="ask-dynamic-suggestions">
        <div class="citation-label" style="margin-top:15px;">Suggested Follow-ups</div>
        <div class="ask-suggestion-grid">
          ${followUps.map(q => `<button class="ask-suggestion" data-q="${_esc(q)}">${_esc(q)}</button>`).join('')}
        </div>
      </div>
    `;
  }

  function _insertCitations(text, citations) {
    return _esc(text)
      .replace(/\[(\d+)\]/g, (_, n) => {
        const c = citations.find(c => c.ref === parseInt(n));
        const tip = c ? _esc(c.source_doc || c.title || '') : '';
        return `<sup class="cite-ref" title="${tip}">[${n}]</sup>`;
      })
      .replace(/\n{2,}/g, '</p><p>')
      .replace(/\n/g, '<br>');
  }

  function _citationList(citations) {
    if (!citations.length) return '';
    return `
      <div class="citation-list">
        <div class="citation-label">Sources</div>
        ${citations.map(c => {
          const src  = c.source_doc || c.title || 'Unknown';
          const link = c.url ? `<a href="${c.url}" target="_blank" rel="noopener" class="cite-link">↗ View</a>` : '';
          const jrnl = c.journal ? `<span class="cite-journal">${c.journal}${c.year?` ${c.year}`:''}</span>` : '';
          const snip = c.snippet ? `<div class="cite-snippet">${_esc(c.snippet.slice(0,150))}…</div>` : '';
          return `
            <div class="citation-card">
              <span class="cite-num">[${c.ref}]</span>
              <div class="cite-body">
                <div class="cite-title">${_esc(src)}</div>
                ${jrnl}${snip}${link}
              </div>
            </div>`;
        }).join('')}
      </div>`;
  }

  function _evalPills(scores) {
    if (!scores || scores.skipped) return '';
    const f = scores.faithfulness != null ? Math.round(scores.faithfulness*100) : null;
    const r = scores.context_relevance != null ? Math.round(scores.context_relevance*100) : null;
    const c = scores.answer_completeness != null ? Math.round(scores.answer_completeness*100) : null;
    const pills = [
      f!=null ? `<span class="eval-pill ${f>=90?'ep-good':f>=70?'ep-warn':'ep-bad'}">Faithfulness ${f}%</span>` : '',
      r!=null ? `<span class="eval-pill ep-neutral">Relevance ${r}%</span>` : '',
      c!=null ? `<span class="eval-pill ep-neutral">Completeness ${c}%</span>` : '',
    ].filter(Boolean).join('');
    return pills ? `<div class="eval-pills">${pills}</div>` : '';
  }

  /* ── Helpers ─────────────────────────────────────────────── */
  function _setBusy(busy) {
    const btn = document.getElementById('askSendBtn');
    const inp = document.getElementById('askInput');
    if (btn) { btn.disabled = busy; btn.style.opacity = busy ? '0.5' : '1'; }
    if (inp) inp.disabled = busy;
  }
  function _scrollBottom() {
    const msgs = document.getElementById('askMessages');
    if (msgs) msgs.scrollTop = msgs.scrollHeight;
  }
  function _esc(s='') {
    return String(s)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;')
      .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  return { init };
})();
