/**
 * summary.js
 * Renders the Summary tab from a patient data object.
 *
 * Panel order:
 *  1. ClinicalSummary block (agent output: chief complaint, HPI, assessment,
 *     patient-facing summary, key concerns, follow-up actions)
 *  2. Legacy narrative card (fallback when no clinical_summary present)
 *  3. 2×2 grid: Diagnoses | Medications | Labs | Clinical Flags
 *  4. Timeline
 */

/**
 * Render the full summary panel for a patient.
 * @param {Object} patient  Full patient object (from demo-data.js or API)
 */
function renderSummary(patient) {
  const el = document.getElementById('tab-summary');
  if (!el) return;

  const s  = patient.summary;
  const cs = s.clinical_summary || null;  // ClinicalSummary schema

  el.innerHTML = `
    ${cs ? buildClinicalSummaryBlock(cs) : buildNarrative(s)}
    <div class="summary-grid">
      ${buildDiagnoses(s.diagnoses)}
      ${buildMedications(s.medications)}
      ${buildLabs(s.lab_results)}
      ${buildFlags(s.clinical_flags, s.allergies)}
    </div>
    ${buildTimeline(s.timeline)}
  `;
}


/* ── Narrative (fallback) ───────────────────────────────── */
function buildNarrative(s) {
  return `
    <div class="summary-narrative">
      <h3>Clinical Summary</h3>
      <p>${s.summary_narrative || 'No narrative available.'}</p>
    </div>
  `;
}

/* ── ClinicalSummary block (agent output) ───────────────── */
function buildClinicalSummaryBlock(cs) {
  const modelBadge = cs.model_used
    ? `<span style="margin-left:auto;font-size:10px;font-family:var(--font-mono);
                   color:var(--text-muted);padding:2px 8px;
                   background:var(--bg-raised);border:1px solid var(--border);
                   border-radius:4px;">${cs.model_used}</span>`
    : '';

  const keyConCerns = (cs.key_concerns || []).map(c => `
    <div class="flag-item warn">⚠ ${c}</div>
  `).join('');

  const followUp = (cs.follow_up_actions || []).map(f => `
    <div style="display:flex;align-items:flex-start;gap:8px;padding:6px 0;
                border-bottom:1px solid var(--border);font-size:13px;color:var(--text-secondary);">
      <span style="color:var(--accent);flex-shrink:0;">→</span>
      <span>${f}</span>
    </div>
  `).join('');

  const patientBox = cs.patient_facing_summary ? `
    <div style="margin-top:16px;padding:16px 18px;
                background:rgba(20,184,166,0.06);
                border:1px solid var(--accent-border);
                border-radius:var(--r-md);">
      <div style="font-size:10px;font-weight:700;letter-spacing:1px;
                  text-transform:uppercase;color:var(--accent);margin-bottom:8px;">
        🙋 Patient-Facing Summary
      </div>
      <p style="font-size:13px;line-height:1.75;color:var(--text-secondary);">
        ${cs.patient_facing_summary}
      </p>
    </div>
  ` : '';

  return `
    <!-- ClinicalSummary agent output -->
    <div class="summary-narrative" style="border-left-color:var(--accent);">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:14px;">
        <h3 style="margin:0;">🤖 Agent Clinical Summary</h3>
        ${modelBadge}
      </div>

      <!-- Chief Complaint -->
      <div style="margin-bottom:14px;">
        <div style="font-size:10px;font-weight:700;letter-spacing:1px;
                    text-transform:uppercase;color:var(--text-muted);margin-bottom:6px;">
          Chief Complaint
        </div>
        <p style="font-size:14px;font-weight:600;color:var(--text-primary);line-height:1.6;">
          ${cs.chief_complaint}
        </p>
      </div>

      <!-- HPI -->
      <div style="margin-bottom:14px;">
        <div style="font-size:10px;font-weight:700;letter-spacing:1px;
                    text-transform:uppercase;color:var(--text-muted);margin-bottom:6px;">
          History of Present Illness
        </div>
        <p style="font-size:13px;line-height:1.75;color:var(--text-secondary);">
          ${cs.history_of_present_illness}
        </p>
      </div>

      <!-- Clinical Assessment -->
      <div>
        <div style="font-size:10px;font-weight:700;letter-spacing:1px;
                    text-transform:uppercase;color:var(--text-muted);margin-bottom:6px;">
          Clinical Assessment
        </div>
        <p style="font-size:13px;line-height:1.75;color:var(--text-secondary);">
          ${cs.clinical_assessment}
        </p>
      </div>

      ${patientBox}
    </div>

    <!-- Key Concerns + Follow-up -->
    ${(cs.key_concerns?.length || cs.follow_up_actions?.length) ? `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px;">

      ${cs.key_concerns?.length ? `
      <div class="sum-card">
        <div class="sum-card-header">
          <div class="sum-card-icon" style="background:rgba(245,158,11,0.12);">⚠</div>
          <span class="sum-card-title">Key Concerns</span>
          <span class="sum-card-count" style="background:var(--warning-bg);color:#FDE68A;">
            ${cs.key_concerns.length}
          </span>
        </div>
        <div class="flags-list">${keyConCerns}</div>
      </div>` : ''}

      ${cs.follow_up_actions?.length ? `
      <div class="sum-card">
        <div class="sum-card-header">
          <div class="sum-card-icon" style="background:rgba(20,184,166,0.12);">📋</div>
          <span class="sum-card-title">Follow-up Actions</span>
          <span class="sum-card-count">${cs.follow_up_actions.length}</span>
        </div>
        <div>${followUp}</div>
      </div>` : ''}

    </div>` : ''}
  `;
}



/* ── Diagnoses ──────────────────────────────────────────── */
function buildDiagnoses(diagnoses = []) {
  const rows = diagnoses.map(dx => {
    const indicator = statusClass(dx.status);
    return `
      <div class="dx-item">
        <div class="dx-indicator ${indicator}"></div>
        <div>
          <div class="dx-name">${dx.name}</div>
          <div class="dx-sub">
            <span class="icd-code">${dx.icd_code}</span>
            <span>${dx.date_first_noted}</span>
            <span>${dx.status}</span>
          </div>
        </div>
      </div>
    `;
  }).join('');

  return `
    <div class="sum-card">
      <div class="sum-card-header">
        <div class="sum-card-icon" style="background:rgba(239,68,68,0.12);">🩺</div>
        <span class="sum-card-title">Diagnoses</span>
        <span class="sum-card-count">${diagnoses.length}</span>
      </div>
      <div class="diagnoses-list">${rows}</div>
    </div>
  `;
}

function statusClass(status = '') {
  const s = status.toLowerCase();
  if (s.includes('resolv')) return 'resolving';
  if (s.includes('suspect')) return 'suspected';
  if (s.includes('improv')) return 'stable';
  if (s.includes('active')) return 'active';
  return 'stable';
}

/* ── Medications ────────────────────────────────────────── */
function buildMedications(meds = []) {
  const rows = meds.map(m => `
    <div class="med-item">
      <div class="med-name">💊 ${m.name}</div>
      <div class="med-dose">${m.dose}</div>
      <div class="med-freq">${m.frequency} · from ${m.start_date}</div>
    </div>
  `).join('');

  return `
    <div class="sum-card">
      <div class="sum-card-header">
        <div class="sum-card-icon" style="background:rgba(20,184,166,0.12);">💊</div>
        <span class="sum-card-title">Medications</span>
        <span class="sum-card-count">${meds.length}</span>
      </div>
      <div class="meds-list">${rows}</div>
    </div>
  `;
}

/* ── Labs ───────────────────────────────────────────────── */
function buildLabs(labs = []) {
  const rows = labs.map(l => {
    const flagCls = l.flag === 'high' ? 'H' : l.flag === 'low' ? 'L' : 'N';
    const flagLabel = l.flag === 'high' ? 'H' : l.flag === 'low' ? 'L' : '✓';
    const valColor = l.flag === 'high'
      ? 'color:var(--danger)'
      : l.flag === 'low'
      ? 'color:var(--info)'
      : 'color:var(--success)';
    return `
      <div class="lab-item">
        <span class="lab-name">${l.test_name}</span>
        <span class="lab-value" style="${valColor}">${l.value}</span>
        <span class="lab-unit">${l.unit}</span>
        <span class="lab-flag ${flagCls}">${flagLabel}</span>
      </div>
    `;
  }).join('');

  return `
    <div class="sum-card">
      <div class="sum-card-header">
        <div class="sum-card-icon" style="background:rgba(59,130,246,0.12);">🧪</div>
        <span class="sum-card-title">Latest Labs</span>
        <span class="sum-card-count">${labs.length}</span>
      </div>
      <div class="labs-list">${rows}</div>
    </div>
  `;
}

/* ── Clinical flags ─────────────────────────────────────── */
function buildFlags(flags = [], allergies = []) {
  const allergyRows = allergies.map(a => `
    <div class="flag-item warn">⚠ Allergy: ${a}</div>
  `).join('');

  const flagRows = flags.map(f => {
    const cls = f.type === 'warn' ? 'warn' : 'info';
    const icon = f.type === 'warn' ? '⚠' : 'ℹ';
    const text = typeof f === 'string' ? f : f.text;
    return `<div class="flag-item ${cls}">${icon} ${text}</div>`;
  }).join('');

  return `
    <div class="sum-card">
      <div class="sum-card-header">
        <div class="sum-card-icon" style="background:rgba(245,158,11,0.12);">⚠</div>
        <span class="sum-card-title">Clinical Flags</span>
        <span class="sum-card-count" style="background:var(--warning-bg);color:#FDE68A;">${flags.length + allergies.length}</span>
      </div>
      <div class="flags-list">
        ${allergyRows}
        ${flagRows}
      </div>
    </div>
  `;
}

/* ── Timeline ───────────────────────────────────────────── */
function buildTimeline(timeline = []) {
  const items = [...timeline].reverse().map(t => `
    <div class="tl-item">
      <div class="tl-dot ${t.category || 'visit'}"></div>
      <div class="tl-content">
        <div class="tl-date">${t.date}</div>
        <div class="tl-event">${t.event}</div>
      </div>
    </div>
  `).join('');

  return `
    <div class="timeline-section">
      <div class="timeline-title">
        📅 Clinical Timeline
        <span style="font-size:11px;font-weight:400;color:var(--text-muted);">Most recent first</span>
      </div>
      <div class="timeline-list">${items}</div>
    </div>
  `;
}
