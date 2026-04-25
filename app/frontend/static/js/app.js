'use strict';

/**
 * app.js — Main application controller
 * Loads demo cases from /api/agent/cases, drives sidebar, tabs, and KG status.
 */

(function () {

  let currentPatient = null;

  document.addEventListener('DOMContentLoaded', async () => {
    initTabs();
    initSearch();

    const isDemo = new URLSearchParams(window.location.search).get('demo') === 'true';
    const caseParam = new URLSearchParams(window.location.search).get('case');

    await initSidebar();      // loads cases from API
    await initKgStatus();     // KG status indicator

    if (caseParam) {
      await loadCaseByKey(caseParam);
    } else if (isDemo) {
      await loadCaseByKey('case_a');  // default demo = James Hartwell
    } else {
      showEmptyState();
    }

    document.getElementById('btnDemoFromEmpty')?.addEventListener('click', async e => {
      e.preventDefault();
      await loadCaseByKey('case_a');
      history.replaceState(null, '', '?case=case_a');
    });

    document.getElementById('btnUploadFromEmpty')?.addEventListener('click', () => {
      if (!currentPatient) loadPatient(emptyPatient(), false);
      activateTab('upload');
    });

    document.getElementById('btnAddPatient')?.addEventListener('click', () => {
      loadPatient(emptyPatient(), false);
      activateTab('upload');
    });
  });


  /* ── Sidebar — loads cases from API ─────────────────────── */
  async function initSidebar() {
    const list = document.getElementById('patientList');
    if (!list) return;

    let cases = [];
    try {
      cases = await API.getCases();
    } catch {
      // fallback: show James Hartwell only
      cases = [{ key: 'case_a', label: 'Case A — James Hartwell (SLE / Lupus Nephritis)' }];
    }

    list.innerHTML = cases.map(c => {
      const [initials, sub] = parseCaseLabel(c.label);
      return buildPatientItem({ id: c.key, initials, name: c.label.split('—')[1]?.trim() || c.label, sub, caseKey: c.key });
    }).join('');

    list.querySelectorAll('.patient-item').forEach(el => {
      el.addEventListener('click', async () => {
        await loadCaseByKey(el.dataset.id);
        history.replaceState(null, '', `?case=${el.dataset.id}`);
      });
    });
  }

  function parseCaseLabel(label) {
    // "Case A — James Hartwell (SLE / Lupus Nephritis)"
    const match = label.match(/Case\s+([A-Z])/i);
    const letter = match ? match[1].toUpperCase() : '?';
    const nameMatch = label.split('—')[1]?.trim() || label;
    const name = nameMatch.split('(')[0].trim();
    const initials = name.split(' ').filter(Boolean).map(w => w[0]).slice(0, 2).join('').toUpperCase();
    return [initials, label.match(/\(([^)]+)\)/)?.[1] || ''];
  }

  function buildPatientItem({ id, initials, name, sub, caseKey }) {
    return `
      <div class="patient-item" data-id="${id}" data-case="${caseKey}">
        <div class="patient-avatar demo">${initials}</div>
        <div class="patient-info">
          <div class="patient-name">${name}</div>
          <div class="patient-sub">${sub}</div>
        </div>
        <span class="patient-badge badge-demo">Demo</span>
      </div>
    `;
  }


  /* ── KG status indicator ─────────────────────────────────── */
  async function initKgStatus() {
    const el = document.getElementById('kgStatusBar');
    if (!el) return;
    try {
      const status = await API.getKgStatus();
      const neo4jUp = status.neo4j_available;
      el.innerHTML = `
        <div class="kg-status-row">
          <span class="kg-dot ${neo4jUp ? 'online' : 'offline'}"></span>
          <span class="kg-label">Neo4j</span>
          <span class="kg-val">${neo4jUp ? `${status.neo4j_conditions_seeded}/${status.local_conditions}` : 'offline'}</span>
          ${neo4jUp && status.unseeded > 0 ? `
            <button class="kg-seed-btn" id="btnSeedKg">Seed ${status.unseeded} more</button>
          ` : ''}
        </div>
      `;
      document.getElementById('btnSeedKg')?.addEventListener('click', async () => {
        await API.triggerKgSeed(false);
        setTimeout(initKgStatus, 1500);
      });
    } catch {
      el.innerHTML = `<div class="kg-status-row"><span class="kg-dot offline"></span><span class="kg-label">KG unavailable</span></div>`;
    }
  }


  /* ── Load a demo case from API ───────────────────────────── */
  async function loadCaseByKey(caseKey) {
    try {
      const patient = await API.getCaseData(caseKey);
      patient._caseKey = caseKey;
      loadPatient(patient, true);
    } catch (err) {
      console.error('[app] Failed to load case', caseKey, err);
      // Graceful fallback: show empty state with error
      showEmptyState();
    }
  }


  /* ── Load patient into view ──────────────────────────────── */
  function loadPatient(patient, demo) {
    currentPatient = patient;

    document.querySelectorAll('.patient-item').forEach(el => {
      el.classList.toggle('active', el.dataset.id === (patient._caseKey || patient.patient_id));
    });

    showPatientView();

    const banner = document.getElementById('demoBanner');
    if (banner) {
      banner.style.display = demo ? '' : 'none';
      const sub = banner.querySelector('.db-sub');
      if (sub) sub.textContent = `— ${patient.case_label || patient.patient?.name || 'Synthetic patient data'}`;
    }

    renderPatientHeader(patient);
    renderSummary(patient);
    renderUpload(patient, demo);
    // Ask + Research: reset so they reinit for new patient
    document.getElementById('tab-ask').innerHTML = '';
    document.getElementById('tab-research').innerHTML = '';
    // Diagnostics renders on-demand when tab is activated
  }


  /* ── Patient header ──────────────────────────────────────── */
  function renderPatientHeader(patient) {
    const el = document.getElementById('patientHeader');
    if (!el) return;
    const p  = patient.patient || {};
    const s  = patient.summary || {};
    const dx = (s.diagnoses || []).slice(0, 3).map(d => d.name).join(' · ');
    el.innerHTML = `
      <div class="ph-avatar">${initials(p.name)}</div>
      <div class="ph-info">
        <div class="ph-name">${p.name || 'Unknown Patient'}</div>
        <div class="ph-meta">
          ${p.dob  ? `<span class="ph-meta-item">🗓 DOB: ${p.dob}</span>` : ''}
          ${p.mrn  ? `<span class="ph-meta-item">🪪 MRN: ${p.mrn}</span>` : ''}
          ${p.age  ? `<span class="ph-meta-item">🎂 Age: ${p.age}</span>` : ''}
          ${dx     ? `<span class="ph-meta-item" style="color:var(--text-secondary)">${dx}</span>` : ''}
        </div>
      </div>
      <div class="ph-badges">
        <span class="status-badge demo">✦ Demo</span>
        <span class="status-badge active">● Active</span>
      </div>
    `;
  }

  function initials(name = '') {
    return name.split(' ').filter(Boolean).map(w => w[0].toUpperCase()).slice(0, 2).join('');
  }


  /* ── Tabs ────────────────────────────────────────────────── */
  function initTabs() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        if (btn.classList.contains('disabled')) return;
        activateTab(btn.dataset.tab);
      });
    });
  }

  function activateTab(tabId) {
    document.querySelectorAll('.tab-btn').forEach(btn =>
      btn.classList.toggle('active', btn.dataset.tab === tabId)
    );
    document.querySelectorAll('.tab-panel').forEach(panel =>
      panel.classList.toggle('active', panel.id === `tab-${tabId}`)
    );

    if (tabId === 'diagnostics' && currentPatient) {
      renderDiagnostics(currentPatient);
    }
    if (tabId === 'ask' && currentPatient) {
      if (!document.querySelector('.ask-layout')) {
        window.AskController?.init(currentPatient);
      }
    }
    if (tabId === 'research' && currentPatient) {
      if (!document.querySelector('.research-layout')) {
        window.ResearchController?.init(currentPatient);
      }
    }
  }


  /* ── Search ──────────────────────────────────────────────── */
  function initSearch() {
    const input = document.getElementById('patientSearch');
    if (!input) return;
    input.addEventListener('input', () => {
      const q = input.value.trim().toLowerCase();
      document.querySelectorAll('.patient-item').forEach(el => {
        el.style.display = el.textContent.toLowerCase().includes(q) ? '' : 'none';
      });
    });
  }


  /* ── Visibility helpers ──────────────────────────────────── */
  function showEmptyState() {
    document.getElementById('emptyState').style.display  = '';
    document.getElementById('patientView').style.display = 'none';
  }
  function showPatientView() {
    document.getElementById('emptyState').style.display  = 'none';
    document.getElementById('patientView').style.display = '';
  }

  function emptyPatient() {
    return {
      patient_id: 'new-' + Date.now(),
      patient: { name: 'New Patient', dob: '—', mrn: '—', age: '—' },
      summary: { summary_narrative: '', diagnoses: [], medications: [], lab_results: [], clinical_flags: [], allergies: [], timeline: [] },
      source_documents: [],
    };
  }

})();
