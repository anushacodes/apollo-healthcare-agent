'use strict';

/**
 * research.js — Research tab: PubMed paper cards + Ask integration.
 * Calls GET /api/rag/research/{patient_id}?case_key=...
 * Pre-fetches papers when tab activates; renders sortable cards.
 */

window.ResearchController = (function () {
  let _patient = null;
  let _papers  = [];
  let _loaded  = false;

  /* ── Public API ──────────────────────────────────────────── */
  function init(patient) {
    _patient = patient;
    _loaded  = false;
    _papers  = [];
    _renderShell();
    _fetchPapers();
  }

  /* ── Shell ───────────────────────────────────────────────── */
  function _renderShell() {
    const panel = document.getElementById('tab-research');
    if (!panel) return;
    panel.innerHTML = `
      <div class="research-layout">

        <div class="research-header">
          <div>
            <h2 class="research-title">Research Agent</h2>
            <p class="research-sub">
              Live PubMed search for this patient's active diagnoses.
              Papers are embedded and available for RAG queries in the Ask tab.
            </p>
          </div>
          <button class="btn-outline research-refresh-btn" id="researchRefresh">
            ↻ Refresh
          </button>
        </div>

        <div class="research-status" id="researchStatus">
          <div class="research-loading">
            <div class="spinner"></div>
            <span>Querying PubMed…</span>
          </div>
        </div>

        <div class="research-grid" id="researchGrid"></div>

      </div>
    `;

    document.getElementById('researchRefresh').addEventListener('click', () => {
      _loaded = false;
      _fetchPapers();
    });
  }

  /* ── Fetch papers ────────────────────────────────────────── */
  async function _fetchPapers() {
    const statusEl = document.getElementById('researchStatus');
    const gridEl   = document.getElementById('researchGrid');
    if (!statusEl || !gridEl) return;

    statusEl.innerHTML = `
      <div class="research-loading">
        <div class="spinner"></div>
        <span>Querying PubMed for relevant literature…</span>
      </div>`;
    gridEl.innerHTML = '';

    const patientId = _patient?.patient_id || 'unknown';
    const caseKey   = _patient?._caseKey   || null;

    try {
      const url = `/api/rag/research/${patientId}${caseKey ? `?case_key=${caseKey}` : ''}`;
      const res  = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      _papers = data.papers || [];
      _loaded = true;
      _render();
    } catch (err) {
      statusEl.innerHTML = `
        <div class="research-error">
          <span class="research-err-icon">⚠</span>
          <span>Could not fetch papers: ${err.message}</span>
          <button class="btn-outline" id="researchRetry">Retry</button>
        </div>`;
      document.getElementById('researchRetry')?.addEventListener('click', () => _fetchPapers());
    }
  }

  /* ── Render cards ────────────────────────────────────────── */
  function _render() {
    const statusEl = document.getElementById('researchStatus');
    const gridEl   = document.getElementById('researchGrid');
    if (!statusEl || !gridEl) return;

    if (!_papers.length) {
      statusEl.innerHTML = `<div class="research-empty">No relevant papers found. Try running the Diagnostics pipeline first to populate diagnoses.</div>`;
      return;
    }

    statusEl.innerHTML = `
      <div class="research-meta">
        <span class="research-count">${_papers.length} papers retrieved</span>
        <span class="research-source-badge">PubMed</span>
      </div>`;

    gridEl.innerHTML = _papers.map((p, i) => _paperCard(p, i)).join('');

    // Wire "Ask about this paper" buttons
    gridEl.querySelectorAll('.paper-ask-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const title = btn.dataset.title;
        // Switch to Ask tab and pre-fill question
        document.querySelector('[data-tab="ask"]')?.click();
        setTimeout(() => {
          const inp = document.getElementById('askInput');
          if (inp) {
            inp.value = `What does the paper "${title}" say about treatment for this patient?`;
            inp.focus();
          }
        }, 100);
      });
    });
  }

  function _paperCard(paper, idx) {
    const journal = [paper.journal, paper.year].filter(Boolean).join(' · ');
    const doiLink = paper.doi
      ? `<a href="https://doi.org/${paper.doi}" target="_blank" rel="noopener" class="paper-doi">DOI ↗</a>`
      : paper.url
      ? `<a href="${paper.url}" target="_blank" rel="noopener" class="paper-doi">PubMed ↗</a>`
      : '';

    const abstract = paper.abstract_snippet || '';

    return `
      <div class="paper-card" data-idx="${idx}">
        <div class="paper-card-top">
          <div class="paper-index">${idx + 1}</div>
          ${journal ? `<span class="paper-journal">${_esc(journal)}</span>` : ''}
          ${doiLink}
        </div>
        <h3 class="paper-title">${_esc(paper.title || 'Untitled')}</h3>
        ${abstract ? `<p class="paper-abstract">${_esc(abstract)}</p>` : ''}
        <div class="paper-card-footer">
          <button class="paper-ask-btn" data-title="${_esc(paper.title || '')}">
            Ask about this paper →
          </button>
        </div>
      </div>
    `;
  }

  function _esc(s = '') {
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  return { init };
})();
