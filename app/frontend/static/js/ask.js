'use strict';

/**
 * ask.js — Agentic RAG chat for the Ask tab.
 * Connects to WS /api/rag/stream/{patient_id}, streams thinking + result events,
 * renders live reasoning trace, then final answer with inline citations.
 */

window.AskController = (function () {
  let _patient = null;
  let _ws = null;
  let _busy = false;

  /* ── Public API ──────────────────────────────────────────── */
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
              Answers are grounded in patient documents and PubMed literature.
              Every claim is cited and evaluated for faithfulness before delivery.
            </p>
          </div>
          <div class="ask-badges">
            <span class="ask-badge">RAG</span>
            <span class="ask-badge">PubMed</span>
            <span class="ask-badge">Eval Gate</span>
          </div>
        </div>

        <div class="ask-messages" id="askMessages">
          <div class="ask-welcome">
            <p>Ask anything about this patient — their records, lab trends, treatment options, or relevant clinical guidelines.</p>
            <div class="ask-suggestion-grid">
              <button class="ask-suggestion" data-q="What are the key concerns for this patient?">Key concerns</button>
              <button class="ask-suggestion" data-q="Summarise the most recent lab abnormalities.">Recent lab abnormalities</button>
              <button class="ask-suggestion" data-q="What is the current standard of care for the primary diagnosis?">Standard of care</button>
              <button class="ask-suggestion" data-q="Are there any drug interaction risks in the current medication list?">Drug interactions</button>
            </div>
          </div>
        </div>

        <form class="ask-input-row" id="askForm">
          <input
            type="text"
            id="askInput"
            class="ask-input"
            placeholder="Ask about this patient…"
            autocomplete="off"
            maxlength="500"
          >
          <button type="submit" class="ask-send-btn" id="askSendBtn">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          </button>
        </form>

      </div>
    `;

    document.getElementById('askForm').addEventListener('submit', e => {
      e.preventDefault();
      _sendQuestion();
    });

    document.querySelectorAll('.ask-suggestion').forEach(btn => {
      btn.addEventListener('click', () => {
        document.getElementById('askInput').value = btn.dataset.q;
        _sendQuestion();
      });
    });
  }

  /* ── Send question ───────────────────────────────────────── */
  function _sendQuestion() {
    if (_busy) return;
    const input = document.getElementById('askInput');
    const q = input.value.trim();
    if (!q) return;
    input.value = '';
    _appendUserMessage(q);
    _streamAnswer(q);
  }

  /* ── User bubble ─────────────────────────────────────────── */
  function _appendUserMessage(text) {
    const msgs = document.getElementById('askMessages');
    // Remove welcome block on first message
    msgs.querySelector('.ask-welcome')?.remove();
    const el = document.createElement('div');
    el.className = 'ask-msg user';
    el.innerHTML = `<div class="ask-bubble user-bubble">${_esc(text)}</div>`;
    msgs.appendChild(el);
    msgs.scrollTop = msgs.scrollHeight;
  }

  /* ── Stream answer via WebSocket ─────────────────────────── */
  function _streamAnswer(question) {
    _busy = true;
    _setBtnState(true);

    const patientId = _patient?.patient_id || 'unknown';
    const caseKey   = _patient?._caseKey || null;

    // Create answer container
    const msgs = document.getElementById('askMessages');
    const el = document.createElement('div');
    el.className = 'ask-msg agent';
    el.innerHTML = `
      <div class="ask-agent-wrap">
        <div class="ask-trace" id="askTrace_${Date.now()}"></div>
        <div class="ask-answer" style="display:none;"></div>
      </div>
    `;
    msgs.appendChild(el);
    msgs.scrollTop = msgs.scrollHeight;

    const traceEl  = el.querySelector('.ask-trace');
    const answerEl = el.querySelector('.ask-answer');
    const traceId  = traceEl.id;

    const wsUrl = `ws://${location.host}/api/rag/stream/${patientId}`;
    _ws = new WebSocket(wsUrl);

    _ws.onopen = () => {
      _ws.send(JSON.stringify({ question, case_key: caseKey }));
    };

    _ws.onmessage = e => {
      let evt;
      try { evt = JSON.parse(e.data); } catch { return; }

      const { type, node, message, data } = evt;

      if (type === 'thinking') {
        _appendTrace(traceEl, node, message, 'thinking');
      } else if (type === 'result') {
        _appendTrace(traceEl, node, message, 'result', data);
      } else if (type === 'done') {
        _renderAnswer(answerEl, data, traceEl);
        _busy = false;
        _setBtnState(false);
        _ws?.close();
      } else if (type === 'error') {
        _appendTrace(traceEl, 'error', message, 'error');
        _busy = false;
        _setBtnState(false);
      }

      msgs.scrollTop = msgs.scrollHeight;
    };

    _ws.onerror = () => {
      _appendTrace(traceEl, 'error', 'Connection error — is the server running?', 'error');
      _busy = false;
      _setBtnState(false);
    };

    _ws.onclose = () => { _ws = null; };
  }

  /* ── Trace entry ─────────────────────────────────────────── */
  const NODE_LABELS = {
    query_router:      'Query Router',
    patient_retriever: 'Patient Docs',
    research_fetcher:  'PubMed Research',
    context_assembler: 'Context Assembly',
    sufficiency_judge: 'Sufficiency Check',
    generator:         'Generator',
    eval_agent:        'Eval Agent',
    error:             'Error',
  };

  function _appendTrace(container, node, message, type, data) {
    const label = NODE_LABELS[node] || node;
    const icon  = type === 'thinking' ? '⟳'
                : type === 'result'   ? '✓'
                : type === 'error'    ? '✗'
                : '·';
    const cls   = `trace-entry trace-${type}`;

    // Build optional data pills
    let pills = '';
    if (data && type === 'result') {
      if (data.route)            pills += `<span class="trace-pill">${data.route}</span>`;
      if (data.chunk_count != null) pills += `<span class="trace-pill">${data.chunk_count} chunks</span>`;
      if (data.paper_count != null) pills += `<span class="trace-pill">${data.paper_count} papers</span>`;
      if (data.faithfulness != null) {
        const pct = Math.round(data.faithfulness * 100);
        const cls2 = pct >= 90 ? 'pill-good' : pct >= 70 ? 'pill-warn' : 'pill-bad';
        pills += `<span class="trace-pill ${cls2}">Faithfulness ${pct}%</span>`;
      }
      if (data.hallucination_detected != null) {
        pills += data.hallucination_detected
          ? `<span class="trace-pill pill-bad">⚠ Hallucination detected</span>`
          : `<span class="trace-pill pill-good">✓ No hallucination</span>`;
      }
    }

    container.insertAdjacentHTML('beforeend', `
      <div class="${cls}">
        <span class="trace-icon">${icon}</span>
        <span class="trace-node">${label}</span>
        <span class="trace-msg">${_esc(message)}</span>
        ${pills ? `<span class="trace-pills">${pills}</span>` : ''}
      </div>
    `);
  }

  /* ── Final answer ────────────────────────────────────────── */
  function _renderAnswer(el, data, traceEl) {
    const { final_response = '', citations = [], eval_scores = {} } = data;
    const faith = eval_scores.faithfulness;
    const blocked = eval_scores.blocked;

    // Render inline citations [1] → superscript links
    const html = _renderCitations(final_response, citations);

    el.style.display = '';
    el.innerHTML = `
      ${blocked ? `<div class="ask-blocked">⚠ Response blocked by Eval Agent — faithfulness too low.</div>` : ''}
      <div class="ask-answer-text">${html}</div>
      ${_renderCitationList(citations)}
      ${faith != null ? _renderEvalPills(eval_scores) : ''}
    `;

    // Collapse trace to a summary line
    traceEl.style.maxHeight = traceEl.scrollHeight + 'px';
    traceEl.style.overflow  = 'hidden';
    traceEl.style.maxHeight = '0';
    traceEl.style.transition = 'max-height 0.3s ease';

    // Add toggle
    const toggleBtn = document.createElement('button');
    toggleBtn.className = 'trace-toggle';
    toggleBtn.textContent = 'Show reasoning ▾';
    let open = false;
    toggleBtn.addEventListener('click', () => {
      open = !open;
      traceEl.style.maxHeight = open ? traceEl.scrollHeight + 40 + 'px' : '0';
      toggleBtn.textContent = open ? 'Hide reasoning ▴' : 'Show reasoning ▾';
    });
    el.insertAdjacentElement('afterbegin', toggleBtn);
  }

  function _renderCitations(text, citations) {
    // Replace [N] with superscript anchors
    return _esc(text).replace(/\[(\d+)\]/g, (_, n) => {
      const c = citations.find(c => c.ref === parseInt(n));
      const tip = c ? _esc(c.source_doc || c.title || '') : '';
      return `<sup class="cite-ref" title="${tip}">[${n}]</sup>`;
    }).replace(/\n{2,}/g, '</p><p>').replace(/\n/g, '<br>');
  }

  function _renderCitationList(citations) {
    if (!citations.length) return '';
    const items = citations.map(c => {
      const source = c.source_doc || c.title || 'Unknown source';
      const link   = c.url ? `<a href="${c.url}" target="_blank" rel="noopener" class="cite-link">↗ ${c.doi || 'View'}</a>` : '';
      const journal = c.journal ? `<span class="cite-journal">${c.journal}${c.year ? ` ${c.year}` : ''}</span>` : '';
      const snippet = c.snippet ? `<div class="cite-snippet">${_esc(c.snippet.slice(0, 140))}…</div>` : '';
      return `
        <div class="citation-card">
          <span class="cite-num">[${c.ref}]</span>
          <div class="cite-body">
            <div class="cite-title">${_esc(source)}</div>
            ${journal}
            ${snippet}
            ${link}
          </div>
        </div>`;
    }).join('');
    return `<div class="citation-list"><div class="citation-label">Sources</div>${items}</div>`;
  }

  function _renderEvalPills(scores) {
    const faith = scores.faithfulness != null ? Math.round(scores.faithfulness * 100) : null;
    const rel   = scores.context_relevance != null ? Math.round(scores.context_relevance * 100) : null;
    const comp  = scores.answer_completeness != null ? Math.round(scores.answer_completeness * 100) : null;
    const pills = [
      faith != null ? `<span class="eval-pill ${faith>=90?'ep-good':faith>=70?'ep-warn':'ep-bad'}">Faithfulness ${faith}%</span>` : '',
      rel   != null ? `<span class="eval-pill ep-neutral">Relevance ${rel}%</span>` : '',
      comp  != null ? `<span class="eval-pill ep-neutral">Completeness ${comp}%</span>` : '',
    ].filter(Boolean).join('');
    return `<div class="eval-pills">${pills}</div>`;
  }

  /* ── Helpers ─────────────────────────────────────────────── */
  function _setBtnState(loading) {
    const btn = document.getElementById('askSendBtn');
    if (!btn) return;
    btn.disabled = loading;
    btn.style.opacity = loading ? '0.5' : '1';
  }

  function _esc(s = '') {
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  return { init };
})();
