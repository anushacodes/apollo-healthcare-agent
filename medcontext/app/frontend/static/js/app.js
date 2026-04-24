/**
 * app.js — Main application controller
 *
 * Responsibilities:
 *  1. Detect demo mode (?demo=true in URL)
 *  2. Populate the patient sidebar list
 *  3. Load a patient → show patient view, render summary & upload tabs
 *  4. Handle tab switching
 *  5. Handle "Add Patient" + search
 */

(function () {
  'use strict';

  /* ── State ──────────────────────────────────────────── */
  let currentPatient = null;
  const isDemo = new URLSearchParams(window.location.search).get('demo') === 'true';

  /* ── Boot ───────────────────────────────────────────── */
  document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initSidebar();
    initSearch();

    if (isDemo) {
      loadPatient(window.DEMO_PATIENT, true);
    } else {
      showEmptyState();
    }

    // "Try demo" from empty state
    document.getElementById('btnDemoFromEmpty')?.addEventListener('click', e => {
      e.preventDefault();
      loadPatient(window.DEMO_PATIENT, true);
      history.replaceState(null, '', '?demo=true');
    });

    // "Upload" from empty state → navigate to app + open upload tab
    document.getElementById('btnUploadFromEmpty')?.addEventListener('click', () => {
      if (!currentPatient) {
        // Create an empty placeholder patient
        loadPatient(emptyPatient(), false);
      }
      activateTab('upload');
    });

    // "Add Patient" in sidebar
    document.getElementById('btnAddPatient')?.addEventListener('click', () => {
      loadPatient(emptyPatient(), false);
      activateTab('upload');
    });
  });

  /* ── Patient list ───────────────────────────────────── */
  function initSidebar() {
    const list = document.getElementById('patientList');
    if (!list) return;

    // Always show demo patient as an entry
    list.innerHTML = buildPatientItem({
      id: 'demo-jh-001',
      initials: 'JH',
      name: 'James Hartwell',
      sub: 'JH-001 · Demo',
      badge: 'demo',
      badgeLabel: 'Demo',
      isDemo: true,
    });

    list.querySelectorAll('.patient-item').forEach(el => {
      el.addEventListener('click', () => {
        if (el.dataset.id === 'demo-jh-001') {
          loadPatient(window.DEMO_PATIENT, true);
          history.replaceState(null, '', '?demo=true');
        }
        // Real patients would be fetched from API here
      });
    });
  }

  function buildPatientItem({ id, initials, name, sub, badge, badgeLabel, isDemo: dem }) {
    return `
      <div class="patient-item" data-id="${id}">
        <div class="patient-avatar${dem ? ' demo' : ''}">${initials}</div>
        <div class="patient-info">
          <div class="patient-name">${name}</div>
          <div class="patient-sub">${sub}</div>
        </div>
        ${badge ? `<span class="patient-badge badge-${badge}">${badgeLabel}</span>` : ''}
      </div>
    `;
  }

  /* ── Load patient ───────────────────────────────────── */
  function loadPatient(patient, demo) {
    currentPatient = patient;

    // Mark active sidebar item
    document.querySelectorAll('.patient-item').forEach(el => {
      el.classList.toggle('active', el.dataset.id === patient.patient_id);
    });

    showPatientView();

    // Demo banner
    const banner = document.getElementById('demoBanner');
    if (banner) banner.style.display = demo ? '' : 'none';

    renderPatientHeader(patient);
    renderSummary(patient);
    renderUpload(patient, demo);
  }

  /* ── Patient header ─────────────────────────────────── */
  function renderPatientHeader(patient) {
    const el = document.getElementById('patientHeader');
    if (!el) return;

    const p  = patient.patient || {};
    const s  = patient.summary || {};
    const dx = (s.diagnoses || []).slice(0, 3).map(d => d.name).join(' · ');

    el.innerHTML = `
      <div class="ph-avatar">${initials(p.name)}</div>
      <div class="ph-info">
        <div class="ph-name">
          ${p.name || 'Unknown Patient'}
        </div>
        <div class="ph-meta">
          <span class="ph-meta-item">🗓 DOB: ${p.dob || '—'}</span>
          <span class="ph-meta-item">🪪 MRN: ${p.mrn || '—'}</span>
          <span class="ph-meta-item">🎂 Age: ${p.age || '—'}</span>
          ${dx ? `<span class="ph-meta-item" style="color:var(--text-secondary)">${dx}</span>` : ''}
        </div>
      </div>
      <div class="ph-badges">
        <span class="status-badge demo">✦ Demo</span>
        <span class="status-badge active">● Active</span>
      </div>
    `;
  }

  function initials(name = '') {
    return name.split(' ')
      .filter(Boolean)
      .map(w => w[0].toUpperCase())
      .slice(0, 2)
      .join('');
  }

  /* ── Tabs ───────────────────────────────────────────── */
  function initTabs() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => activateTab(btn.dataset.tab));
    });
  }

  function activateTab(tabId) {
    document.querySelectorAll('.tab-btn').forEach(btn =>
      btn.classList.toggle('active', btn.dataset.tab === tabId)
    );
    document.querySelectorAll('.tab-panel').forEach(panel =>
      panel.classList.toggle('active', panel.id === `tab-${tabId}`)
    );
  }

  /* ── Search ─────────────────────────────────────────── */
  function initSearch() {
    const input = document.getElementById('patientSearch');
    if (!input) return;
    input.addEventListener('input', () => {
      const q = input.value.trim().toLowerCase();
      document.querySelectorAll('.patient-item').forEach(el => {
        const text = el.textContent.toLowerCase();
        el.style.display = text.includes(q) ? '' : 'none';
      });
    });
  }

  /* ── Visibility helpers ─────────────────────────────── */
  function showEmptyState() {
    document.getElementById('emptyState').style.display  = '';
    document.getElementById('patientView').style.display = 'none';
  }
  function showPatientView() {
    document.getElementById('emptyState').style.display  = 'none';
    document.getElementById('patientView').style.display = '';
  }

  /* ── Empty patient placeholder ──────────────────────── */
  function emptyPatient() {
    return {
      patient_id: 'new-' + Date.now(),
      patient: { name: 'New Patient', dob: '—', mrn: '—', age: '—' },
      summary: {
        summary_narrative: 'No summary yet — upload documents to generate one.',
        diagnoses: [], medications: [], lab_results: [],
        clinical_flags: [], allergies: [], timeline: [],
      },
      source_documents: [],
      demo_questions: [],
    };
  }

})();
