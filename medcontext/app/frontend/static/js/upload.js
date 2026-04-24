/**
 * upload.js
 * Renders the Documents/Upload tab.
 */

/**
 * Render the upload tab for a patient.
 * @param {Object} patient  Full patient object
 * @param {Boolean} isDemo  True when running in demo mode
 */
function renderUpload(patient, isDemo = false) {
  const el = document.getElementById('tab-upload');
  if (!el) return;

  const docs = (patient.source_documents || []);

  el.innerHTML = `
    <!-- Drop zone -->
    <div class="upload-zone" id="uploadZone">
      <div class="upload-zone-icon">📂</div>
      <h3>Drop patient documents here</h3>
      <p>Drag and drop files, or click to browse</p>
      <div class="upload-filetypes">
        <span class="filetype-chip">.pdf</span>
        <span class="filetype-chip">.jpg</span>
        <span class="filetype-chip">.png</span>
        <span class="filetype-chip">.txt</span>
        <span class="filetype-chip">.docx</span>
      </div>
      <button class="btn-browse" id="btnBrowse">Browse files</button>
      <input type="file" id="fileInput" multiple hidden
             accept=".pdf,.jpg,.jpeg,.png,.tiff,.txt,.docx">
    </div>

    <!-- Queue (populated when files are selected) -->
    <div id="uploadQueue" style="margin-bottom:20px;display:flex;flex-direction:column;gap:8px;"></div>

    <!-- Existing / demo documents -->
    ${docs.length ? `
      <div class="upload-section-label" style="margin-top:4px;">
        ${isDemo ? 'Demo Documents' : 'Uploaded Documents'}
      </div>
      <div class="doc-grid">
        ${docs.map(buildDocCard).join('')}
      </div>
    ` : ''}

    ${isDemo ? `
      <div style="margin-top:28px;padding:16px 20px;
                  background:var(--bg-raised);border:1px solid var(--border);
                  border-radius:var(--r-md);font-size:13px;color:var(--text-muted);">
        💡 Demo mode: these documents are pre-processed synthetic data stored in
        <code style="font-family:var(--font-mono);background:var(--bg-surface);
               padding:2px 6px;border-radius:4px;">data/seed/</code>.
        File upload is disabled in demo mode.
      </div>
    ` : ''}
  `;

  initUploadZone(isDemo);
}

/* ── Document card ──────────────────────────────────────── */
function buildDocCard(doc) {
  return `
    <div class="doc-card">
      <div class="doc-card-top">
        <div class="doc-icon">${doc.icon}</div>
        <div class="doc-label">${doc.label}</div>
        <div class="doc-status processed">✓ Ready</div>
      </div>
      <div class="doc-desc">${doc.description}</div>
    </div>
  `;
}

/* ── Upload zone interaction ────────────────────────────── */
function initUploadZone(isDemo) {
  const zone      = document.getElementById('uploadZone');
  const fileInput = document.getElementById('fileInput');
  const btnBrowse = document.getElementById('btnBrowse');
  if (!zone) return;

  if (isDemo) {
    zone.style.opacity = '0.45';
    zone.style.pointerEvents = 'none';
    if (btnBrowse) btnBrowse.disabled = true;
    return;
  }

  // Click to browse
  btnBrowse?.addEventListener('click', () => fileInput?.click());
  zone.addEventListener('click', () => fileInput?.click());

  // Drag + drop
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    handleFiles(Array.from(e.dataTransfer.files));
  });

  fileInput?.addEventListener('change', () => {
    handleFiles(Array.from(fileInput.files));
    fileInput.value = '';
  });
}

function handleFiles(files) {
  const queue = document.getElementById('uploadQueue');
  if (!queue) return;

  files.forEach(file => {
    const item = document.createElement('div');
    item.style.cssText = `
      display:flex;align-items:center;gap:12px;padding:12px 16px;
      background:var(--bg-card);border:1px solid var(--border);
      border-radius:var(--r-sm);font-size:13px;backdrop-filter:blur(12px);
    `;
    item.innerHTML = `
      <span>${fileIcon(file.name)}</span>
      <div style="flex:1;min-width:0;">
        <div style="font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
          ${file.name}
        </div>
        <div style="font-size:11px;color:var(--text-muted);">${formatBytes(file.size)}</div>
      </div>
      <div class="doc-status pending" style="flex-shrink:0;">⏳ Queued</div>
    `;
    queue.appendChild(item);

    // Simulate processing (will be replaced by real API call)
    setTimeout(() => {
      const badge = item.querySelector('.doc-status');
      if (badge) {
        badge.className = 'doc-status processed';
        badge.textContent = '✓ Ready';
      }
    }, 1800 + Math.random() * 1200);
  });
}

function fileIcon(name) {
  const ext = name.split('.').pop().toLowerCase();
  if (ext === 'pdf')  return '📄';
  if (['jpg','jpeg','png','tiff'].includes(ext)) return '🖼️';
  if (ext === 'txt')  return '📝';
  if (['m4a','mp3','wav'].includes(ext)) return '🎙️';
  return '📁';
}

function formatBytes(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}
