'use strict';

/**
 * diagnostics.js
 * Drives the Diagnostics tab — streaming agent pipeline with live audit trail.
 *
 * Lifecycle:
 *   renderDiagnostics(patient) → called when Diagnostics tab is activated
 *   Renders the launch panel → on "Run" button, opens WS and streams results
 */

const NODE_META = {
  orchestrator: { label: 'Orchestrator',     icon: '🎯', color: '#6366f1' },
  drug_graph:   { label: 'Drug / KG Agent',  icon: '💊', color: '#f59e0b' },
  diagnosis:    { label: 'Diagnosis Agent',  icon: '🧠', color: '#10b981' },
  tool_node:    { label: 'Calculators',      icon: '🔢', color: '#3b82f6' },
  summarizer:   { label: 'Summarizer',       icon: '📋', color: '#8b5cf6' },
  __start__:    { label: 'Pipeline Start',   icon: '▶',  color: '#64748b' },
  __done__:     { label: 'Complete',         icon: '✅', color: '#10b981' },
  __error__:    { label: 'Error',            icon: '❌', color: '#ef4444' },
};

let _diagnosticsRunning = false;

function renderDiagnostics(patient) {
  const el = document.getElementById('tab-diagnostics');
  if (!el) return;

  const p = patient.patient || {};
  const caseKey = patient._caseKey || null;

  el.innerHTML = `
    <div class="diag-container">

      <!-- Launch panel -->
      <div class="diag-launch-panel" id="diagLaunchPanel">
        <div class="diag-launch-header">
          <div class="diag-launch-icon">🧠</div>
          <div>
            <div class="diag-launch-title">Multi-Agent Diagnostic Pipeline</div>
            <div class="diag-launch-sub">
              Orchestrator → Drug/KG Agent → Diagnosis Agent → Calculators → Summarizer
            </div>
          </div>
        </div>

        <div class="diag-provider-pills">
          <span class="diag-pill groq">Groq llama-3.3-70b</span>
          <span class="diag-pill gemini">Gemini 1.5 Flash</span>
          <span class="diag-pill openrouter">OpenRouter (fallback)</span>
          <span class="diag-pill neo4j">Neo4j KG</span>
        </div>

        <button class="btn-run-agent" id="btnRunAgent" ${_diagnosticsRunning ? 'disabled' : ''}>
          ${_diagnosticsRunning ? '<span class="spinner-sm"></span> Running…' : '▶ Run Agent Pipeline'}
        </button>

        <div class="diag-warning">
          ⚡ This will make live API calls to Groq and Google Gemini using your configured API keys.
        </div>
      </div>

      <!-- Progress: pipeline steps -->
      <div class="diag-pipeline" id="diagPipeline" style="display:none;">
        <div class="diag-pipeline-title">Agent Execution Trail</div>
        <div class="diag-audit-log" id="diagAuditLog"></div>
      </div>

      <!-- Results panels (shown progressively) -->
      <div class="diag-results" id="diagResults"></div>

    </div>
  `;

  document.getElementById('btnRunAgent')?.addEventListener('click', () => {
    if (_diagnosticsRunning) return;
    const payload = caseKey ? { case: caseKey } : patient;
    runDiagnosticsPipeline(patient.patient_id || 'demo', payload);
  });
}


function runDiagnosticsPipeline(patientId, payload) {
  _diagnosticsRunning = true;
  const btn = document.getElementById('btnRunAgent');
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner-sm"></span> Running…'; }

  const pipeline = document.getElementById('diagPipeline');
  const auditLog = document.getElementById('diagAuditLog');
  const results  = document.getElementById('diagResults');

  if (pipeline) pipeline.style.display = '';
  if (auditLog) auditLog.innerHTML = '';
  if (results)  results.innerHTML  = '';

  API.runAgentWs(patientId, payload, (event) => {
    appendAuditEntry(auditLog, event);

    if (event.node === 'drug_graph')   renderInteractions(results, event);
    if (event.node === 'diagnosis')    renderDiagnoses(results, event);
    if (event.node === 'tool_node')    renderCalculators(results, event);
    if (event.node === 'summarizer')   renderAgentSummary(results, event);

    if (event.node === '__done__' || event.node === '__error__') {
      _diagnosticsRunning = false;
      if (btn) { btn.disabled = false; btn.innerHTML = '↻ Run Again'; }
    }
  }).catch(err => {
    _diagnosticsRunning = false;
    if (btn) { btn.disabled = false; btn.innerHTML = '↻ Retry'; }
    appendAuditEntry(auditLog, { node: '__error__', audit_entry: `Connection failed: ${err}` });
  });
}


/* Audit log entry */
function appendAuditEntry(container, event) {
  if (!container) return;
  const meta = NODE_META[event.node] || { label: event.node, icon: '•', color: '#64748b' };
  const entry = document.createElement('div');
  entry.className = 'audit-entry';
  entry.innerHTML = `
    <div class="audit-node-badge" style="--node-color:${meta.color}">
      ${meta.icon} ${meta.label}
    </div>
    <div class="audit-text">${event.audit_entry || event.error || ''}</div>
  `;
  container.appendChild(entry);
  container.scrollTop = container.scrollHeight;
}


/* Drug interactions result panel */
function renderInteractions(container, event) {
  const data = event.interactions || {};
  const interactions = data.interactions || [];
  const contraindications = data.contraindications || [];
  const risk = data.overall_risk || 'unknown';
  const riskCls = risk === 'high' ? 'high' : risk === 'moderate' ? 'moderate' : 'low';

  const intRows = interactions.map(i => `
    <div class="diag-result-row">
      <span class="severity-badge ${i.severity || 'minor'}">${i.severity || '?'}</span>
      <div>
        <div class="diag-row-title">${(i.drugs || []).join(' + ')}</div>
        <div class="diag-row-sub">${i.mechanism || ''}</div>
        <div class="diag-row-action">${i.clinical_significance || ''}</div>
      </div>
    </div>
  `).join('') || '<div class="diag-empty">No interactions identified.</div>';

  const ciRows = contraindications.map(c => `
    <div class="diag-result-row">
      <span class="severity-badge major">⚠</span>
      <div>
        <div class="diag-row-title">${c.drug} + ${c.condition}</div>
        <div class="diag-row-sub">${c.risk || c.reason || ''}</div>
      </div>
    </div>
  `).join('');

  const panel = document.createElement('div');
  panel.className = 'diag-result-panel animate-in';
  panel.innerHTML = `
    <div class="drp-header">
      <span class="drp-icon" style="background:rgba(245,158,11,0.12)">💊</span>
      <span class="drp-title">Drug Interactions & KG</span>
      <span class="risk-badge ${riskCls}">Risk: ${risk}</span>
      <span class="kg-source-badge">${data.kg_source || 'local'}</span>
    </div>
    <div class="drp-body">
      ${interactions.length || contraindications.length ? `
        <div class="drp-section-label">Drug-Drug Interactions</div>
        ${intRows}
        ${contraindications.length ? `
          <div class="drp-section-label" style="margin-top:12px;">Contraindications</div>
          ${ciRows}
        ` : ''}
      ` : '<div class="diag-empty">No drug interactions or contraindications found.</div>'}
      ${data.summary ? `<div class="diag-summary-text">${data.summary}</div>` : ''}
    </div>
  `;
  container.appendChild(panel);
}


/* Diagnosis result panel */
function renderDiagnoses(container, event) {
  const data = event.diagnoses || {};
  const proposed = data.proposed_diagnoses || [];

  const rows = proposed.map(dx => {
    const confCls = dx.confidence === 'high' ? 'high' : dx.confidence === 'moderate' ? 'moderate' : 'low';
    const evidence = (dx.supporting_evidence || []).map(e => `<li>${e}</li>`).join('');
    return `
      <div class="dx-diag-item">
        <div class="dx-diag-header">
          <span class="dx-diag-name">${dx.name}</span>
          ${dx.icd_code ? `<span class="icd-code">${dx.icd_code}</span>` : ''}
          <span class="conf-badge ${confCls}">${dx.confidence}</span>
          ${dx.name === data.primary_diagnosis ? '<span class="primary-badge">Primary</span>' : ''}
        </div>
        <div class="dx-diag-reasoning">${dx.reasoning || ''}</div>
        ${evidence ? `<ul class="dx-diag-evidence">${evidence}</ul>` : ''}
      </div>
    `;
  }).join('') || '<div class="diag-empty">No diagnoses proposed.</div>';

  const panel = document.createElement('div');
  panel.className = 'diag-result-panel animate-in';
  panel.innerHTML = `
    <div class="drp-header">
      <span class="drp-icon" style="background:rgba(16,185,129,0.12)">🧠</span>
      <span class="drp-title">Differential Diagnoses</span>
      <span class="diag-count-badge">${proposed.length} proposed</span>
    </div>
    <div class="drp-body">
      ${rows}
      ${data.differential_notes ? `
        <div class="diag-notes-box">
          <span class="diag-notes-label">Differentials to rule out:</span>
          ${data.differential_notes}
        </div>
      ` : ''}
      ${(data.recommended_investigations || []).length ? `
        <div class="diag-notes-box" style="margin-top:8px;">
          <span class="diag-notes-label">Recommended investigations:</span>
          ${(data.recommended_investigations || []).join(', ')}
        </div>
      ` : ''}
    </div>
  `;
  container.appendChild(panel);
}


/* Calculator results panel */
function renderCalculators(container, event) {
  const results = event.calculator_results || [];
  if (!results.length) return;

  const rows = results.map(r => {
    if (r.error) return `<div class="calc-row error">${r.tool}: ${r.error}</div>`;
    const res = r.result || {};
    return `
      <div class="calc-row">
        <div class="calc-tool-name">${res.tool || r.tool}</div>
        <div class="calc-values">
          ${Object.entries(res)
            .filter(([k]) => k !== 'tool')
            .map(([k, v]) => `
              <div class="calc-kv">
                <span class="calc-k">${k.replace(/_/g, ' ')}</span>
                <span class="calc-v">${v}</span>
              </div>
            `).join('')}
        </div>
      </div>
    `;
  }).join('');

  const panel = document.createElement('div');
  panel.className = 'diag-result-panel animate-in';
  panel.innerHTML = `
    <div class="drp-header">
      <span class="drp-icon" style="background:rgba(59,130,246,0.12)">🔢</span>
      <span class="drp-title">Clinical Calculators</span>
    </div>
    <div class="drp-body">${rows}</div>
  `;
  container.appendChild(panel);
}


/* Agent summary panel */
function renderAgentSummary(container, event) {
  const summary = event.final_summary;
  if (!summary) return;

  const concerns = (summary.key_concerns || []).map(c => `<li>${c}</li>`).join('');
  const actions = (summary.follow_up_actions || []).map(a => `<li>${a}</li>`).join('');

  const panel = document.createElement('div');
  panel.className = 'diag-result-panel animate-in';
  panel.innerHTML = `
    <div class="drp-header">
      <span class="drp-icon" style="background:rgba(139,92,246,0.12)">📋</span>
      <span class="drp-title">Agent Clinical Summary</span>
      ${summary.model_used ? `<span class="kg-source-badge">${summary.model_used}</span>` : ''}
    </div>
    <div class="drp-body">
      ${summary.chief_complaint ? `
        <div class="diag-summary-field">
          <span class="dsf-label">Chief Complaint</span>
          <p>${summary.chief_complaint}</p>
        </div>
      ` : ''}
      ${summary.clinical_assessment ? `
        <div class="diag-summary-field">
          <span class="dsf-label">Clinical Assessment</span>
          <p>${summary.clinical_assessment}</p>
        </div>
      ` : ''}
      ${concerns ? `
        <div class="diag-summary-field">
          <span class="dsf-label">Key Concerns</span>
          <ul class="diag-list">${concerns}</ul>
        </div>
      ` : ''}
      ${actions ? `
        <div class="diag-summary-field">
          <span class="dsf-label">Follow-up Actions</span>
          <ul class="diag-list">${actions}</ul>
        </div>
      ` : ''}
      ${summary.patient_facing_summary ? `
        <div class="diag-patient-box">
          <span class="dsf-label">🙋 Patient-Facing</span>
          <p>${summary.patient_facing_summary}</p>
        </div>
      ` : ''}
    </div>
  `;
  container.appendChild(panel);
}

window.renderDiagnostics = renderDiagnostics;
