// notebook-ui.js
// Atlantis [CODEX] Lab Notebook: Timeline, Metadata, Attachments, Versioning, Smart Linking, AI, and more

// --- Globals ---
let notebookEntries = [];
let currentEntryId = null;
let notebookMode = 'freeform';
let notebookEditor = null;
let notebookDiffs = {};
let notebookUser = null;
let notebookDevice = navigator.userAgent;
let notebookLocation = null;
let notebookProjectId = null;

// --- Utility: Get Project ID ---
function getNotebookProjectId() {
  if (notebookProjectId) return notebookProjectId;
  const params = new URLSearchParams(window.location.search);
  notebookProjectId = params.get('project_id');
  return notebookProjectId;
}

// --- Utility: Get User Info (JWT) ---
async function getNotebookUser() {
  if (notebookUser) return notebookUser;
  const token = localStorage.getItem('access_token');
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    const res = await fetch(`/users/${payload.sub}`, { headers: { 'Authorization': 'Bearer ' + token } });
    if (res.ok) {
      notebookUser = await res.json();
      return notebookUser;
    }
  } catch (e) {}
  return null;
}

// --- Utility: Get Location (if allowed) ---
function getNotebookLocation() {
  if (notebookLocation) return notebookLocation;
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(pos => {
      notebookLocation = `${pos.coords.latitude.toFixed(4)},${pos.coords.longitude.toFixed(4)}`;
    });
  }
}
getNotebookLocation();

// --- Timeline Fetch/Render ---
async function fetchNotebookEntries() {
  const projectId = getNotebookProjectId();
  const token = localStorage.getItem('access_token');
  if (!projectId || !token) return [];
  const res = await fetch(`/projects/${encodeURIComponent(projectId)}/notebook`, { headers: { 'Authorization': 'Bearer ' + token } });
  if (!res.ok) return [];
  notebookEntries = await res.json();
  return notebookEntries;
}

function groupEntries(entries, groupBy) {
  if (groupBy === 'day') {
    const byDay = {};
    entries.forEach(e => {
      const day = (e.timestamp || '').slice(0, 10);
      if (!byDay[day]) byDay[day] = [];
      byDay[day].push(e);
    });
    return byDay;
  }
  if (groupBy === 'session') {
    const bySession = {};
    entries.forEach(e => {
      const session = e.session_id || 'Session';
      if (!bySession[session]) bySession[session] = [];
      bySession[session].push(e);
    });
    return bySession;
  }
  if (groupBy === 'experiment') {
    const byExp = {};
    entries.forEach(e => {
      const exp = e.experiment_id || 'Experiment';
      if (!byExp[exp]) byExp[exp] = [];
      byExp[exp].push(e);
    });
    return byExp;
  }
  return { All: entries };
}

function renderNotebookTimeline() {
  const groupBy = document.getElementById('notebook-group-toggle').value;
  const search = document.getElementById('notebook-search').value.trim().toLowerCase();
  let entries = notebookEntries;
  if (search) {
    entries = entries.filter(e => (e.content || '').toLowerCase().includes(search) || (e.structured || '').toLowerCase().includes(search));
  }
  const grouped = groupEntries(entries, groupBy);
  const timeline = document.getElementById('notebook-timeline');
  timeline.innerHTML = '';
  Object.keys(grouped).forEach(group => {
    const groupDiv = document.createElement('div');
    groupDiv.className = 'mb-4';
    groupDiv.innerHTML = `<div class="text-cyan-300 font-semibold mb-2">${group}</div>`;
    grouped[group].forEach(entry => {
      const div = document.createElement('div');
      div.className = 'glass rounded p-2 mb-2 cursor-pointer hover:bg-cyan-900/10';
      div.innerHTML = `
        <div class="flex items-center gap-2">
          <span class="text-cyan-200 font-bold">${entry.user_name || 'Unknown'}</span>
          <span class="text-xs text-cyan-400">${entry.timestamp ? new Date(entry.timestamp).toLocaleString() : ''}</span>
          <span class="text-xs text-cyan-400 ml-2">${entry.device || ''}</span>
          <span class="text-xs text-cyan-400 ml-2">${entry.location || ''}</span>
        </div>
        <div class="text-cyan-100 text-sm mt-1">${(entry.content || '').slice(0, 80)}${(entry.content && entry.content.length > 80 ? '...' : '')}</div>
        <div class="flex gap-2 mt-1">
          ${(entry.attachments||[]).map(a => `<span class='text-cyan-400 text-xs'>📎 ${a.filename}</span>`).join(' ')}
        </div>
      `;
      div.onclick = () => loadNotebookEntry(entry.id);
      timeline.appendChild(div);
    });
    timeline.appendChild(groupDiv);
  });
}

// --- Entry Editor ---
function setNotebookMode(mode) {
  notebookMode = mode;
  document.getElementById('notebook-structured-fields').classList.toggle('hidden', mode !== 'structured');
  document.getElementById('notebook-editor').style.display = (mode === 'structured') ? 'none' : 'block';
  document.getElementById('mode-freeform').classList.toggle('bg-cyan-800', mode === 'freeform');
  document.getElementById('mode-structured').classList.toggle('bg-cyan-800', mode === 'structured');
}

function clearNotebookEditor() {
  currentEntryId = null;
  document.getElementById('notebook-entry-meta').innerHTML = '';
  document.getElementById('notebook-editor').value = '';
  document.getElementById('notebook-obs').value = '';
  document.getElementById('notebook-hyp').value = '';
  document.getElementById('notebook-method').value = '';
  document.getElementById('notebook-result').value = '';
  document.getElementById('notebook-conc').value = '';
  document.getElementById('notebook-attachments').innerHTML = '';
  document.getElementById('notebook-preview').innerHTML = '';
  document.getElementById('notebook-diff-view').classList.add('hidden');
}

async function loadNotebookEntry(entryId) {
  const entry = notebookEntries.find(e => e.id === entryId);
  if (!entry) return;
  currentEntryId = entryId;
  // Meta
  document.getElementById('notebook-entry-meta').innerHTML = `
    <span>By: <b>${entry.user_name || 'Unknown'}</b></span>
    <span>Time: <b>${entry.timestamp ? new Date(entry.timestamp).toLocaleString() : ''}</b></span>
    <span>Device: <b>${entry.device || ''}</b></span>
    <span>Location: <b>${entry.location || ''}</b></span>
    <span>Session: <b>${entry.session_id || ''}</b></span>
    <span>Experiment: <b>${entry.experiment_id || ''}</b></span>
    <span>Version: <b>${entry.version || ''}</b></span>
    <span>Visibility: <b>${entry.visibility || 'team'}</b></span>
  `;
  // Editor
  if (entry.structured) {
    setNotebookMode('structured');
    document.getElementById('notebook-obs').value = entry.structured.observation || '';
    document.getElementById('notebook-hyp').value = entry.structured.hypothesis || '';
    document.getElementById('notebook-method').value = entry.structured.method || '';
    document.getElementById('notebook-result').value = entry.structured.result || '';
    document.getElementById('notebook-conc').value = entry.structured.conclusion || '';
  } else {
    setNotebookMode('freeform');
    document.getElementById('notebook-editor').value = entry.content || '';
  }
  // Attachments
  renderNotebookAttachments(entry.attachments || []);
  // Preview
  updateNotebookPreview();
  // Diffs
  if (entry.diffs && entry.diffs.length > 0) {
    document.getElementById('notebook-diff-view').classList.remove('hidden');
    document.getElementById('notebook-diff-view').innerHTML = entry.diffs.map(d => `<div class='mb-2'><b>${d.timestamp}</b><pre>${d.diff}</pre></div>`).join('');
  } else {
    document.getElementById('notebook-diff-view').classList.add('hidden');
  }
}

function renderNotebookAttachments(attachments) {
  const container = document.getElementById('notebook-attachments');
  container.innerHTML = '';
  attachments.forEach(att => {
    const ext = (att.filename || '').split('.').pop().toLowerCase();
    let preview = '';
    if (["png","jpg","jpeg","gif","svg"].includes(ext)) {
      preview = `<img src="/notebook-attachments/${att.id}/download" class="max-h-32 rounded shadow" />`;
    } else if (["mp3","wav","ogg"].includes(ext)) {
      preview = `<audio controls src="/notebook-attachments/${att.id}/download"></audio>`;
    } else if (["mp4","webm","mov"].includes(ext)) {
      preview = `<video controls class="max-h-32" src="/notebook-attachments/${att.id}/download"></video>`;
    } else if (["csv","fasta","tiff","hdf5","log","txt"].includes(ext)) {
      preview = `<a href="/notebook-attachments/${att.id}/download" target="_blank" class="underline text-cyan-300">${att.filename}</a>`;
    } else {
      preview = `<a href="/notebook-attachments/${att.id}/download" target="_blank" class="underline text-cyan-300">${att.filename}</a>`;
    }
    const div = document.createElement('div');
    div.className = 'inline-block mr-2 mb-2';
    div.innerHTML = preview;
    container.appendChild(div);
  });
}

function updateNotebookPreview() {
  let content = '';
  if (notebookMode === 'structured') {
    content = [
      `**Observation:** ${document.getElementById('notebook-obs').value}`,
      `**Hypothesis:** ${document.getElementById('notebook-hyp').value}`,
      `**Method:** ${document.getElementById('notebook-method').value}`,
      `**Result:** ${document.getElementById('notebook-result').value}`,
      `**Conclusion:** ${document.getElementById('notebook-conc').value}`
    ].join('\n\n');
  } else {
    content = document.getElementById('notebook-editor').value;
  }
  document.getElementById('notebook-preview').innerHTML = marked.parse(content || '');
}

// --- Save Entry ---
document.getElementById('save-entry-btn').addEventListener('click', async function() {
  const token = localStorage.getItem('access_token');
  const projectId = getNotebookProjectId();
  if (!token || !projectId) return;
  let content = '';
  let structured = null;
  if (notebookMode === 'structured') {
    structured = {
      observation: document.getElementById('notebook-obs').value,
      hypothesis: document.getElementById('notebook-hyp').value,
      method: document.getElementById('notebook-method').value,
      result: document.getElementById('notebook-result').value,
      conclusion: document.getElementById('notebook-conc').value
    };
    content = Object.values(structured).join('\n\n');
  } else {
    content = document.getElementById('notebook-editor').value;
  }
  // Metadata
  const meta = {
    device: notebookDevice,
    location: notebookLocation,
    visibility: 'team',
    session_id: (new Date()).toISOString().slice(0,10),
    experiment_id: projectId
  };
  // Attachments
  // (handled separately)
  const payload = {
    id: currentEntryId,
    content,
    structured,
    ...meta
  };
  const res = await fetch(`/projects/${encodeURIComponent(projectId)}/notebook`, {
    method: currentEntryId ? 'PATCH' : 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
    body: JSON.stringify(payload)
  });
  if (res.ok) {
    await fetchNotebookEntries();
    renderNotebookTimeline();
    clearNotebookEditor();
    document.getElementById('notebook-diff-indicator').textContent = 'Saved';
    document.getElementById('notebook-diff-indicator').classList.remove('hidden');
    setTimeout(() => document.getElementById('notebook-diff-indicator').classList.add('hidden'), 1200);
  }
});

// --- New Entry ---
document.getElementById('new-entry-btn').addEventListener('click', function() {
  clearNotebookEditor();
});

document.getElementById('mode-freeform').addEventListener('click', function() { setNotebookMode('freeform'); });
document.getElementById('mode-structured').addEventListener('click', function() { setNotebookMode('structured'); });
document.getElementById('notebook-editor').addEventListener('input', updateNotebookPreview);
document.getElementById('notebook-obs').addEventListener('input', updateNotebookPreview);
document.getElementById('notebook-hyp').addEventListener('input', updateNotebookPreview);
document.getElementById('notebook-method').addEventListener('input', updateNotebookPreview);
document.getElementById('notebook-result').addEventListener('input', updateNotebookPreview);
document.getElementById('notebook-conc').addEventListener('input', updateNotebookPreview);
document.getElementById('notebook-group-toggle').addEventListener('change', renderNotebookTimeline);
document.getElementById('notebook-search').addEventListener('input', renderNotebookTimeline);

// --- Attachments ---
document.getElementById('attach-btn').addEventListener('click', function() {
  document.getElementById('notebook-attach').click();
});
document.getElementById('notebook-attach').addEventListener('change', async function(e) {
  const files = Array.from(e.target.files);
  if (!files.length) return;
  const token = localStorage.getItem('access_token');
  const projectId = getNotebookProjectId();
  if (!token || !projectId || !currentEntryId) return;
  for (const file of files) {
    const formData = new FormData();
    formData.append('file', file);
    await fetch(`/notebook-entries/${encodeURIComponent(currentEntryId)}/attachments`, {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + token },
      body: formData
    });
  }
  await fetchNotebookEntries();
  loadNotebookEntry(currentEntryId);
});

// --- Voice-to-Entry (placeholder) ---
document.getElementById('voice-btn').addEventListener('click', function() {
  alert('Voice dictation coming soon!');
});
// --- OCR (placeholder) ---
document.getElementById('ocr-btn').addEventListener('click', function() {
  alert('OCR image-to-text coming soon!');
});

// --- AI Summary ---
document.getElementById('notebook-summary-btn').addEventListener('click', async function() {
  const token = localStorage.getItem('access_token');
  const projectId = getNotebookProjectId();
  if (!token || !projectId) return;
  const style = document.getElementById('notebook-style-toggle').value;
  const res = await fetch(`/projects/${encodeURIComponent(projectId)}/notebook/summary?style=${encodeURIComponent(style)}`, {
    headers: { 'Authorization': 'Bearer ' + token }
  });
  if (res.ok) {
    const data = await res.json();
    alert(data.summary);
  }
});

// --- Smart Linking & Mentions (placeholder) ---
// You would implement @mention autocomplete and inline linking here
// For now, just a placeholder
// --- Semantic Search (placeholder) ---
// You would implement advanced search here

// --- Initial Load ---
document.addEventListener('DOMContentLoaded', async function() {
  await fetchNotebookEntries();
  renderNotebookTimeline();
  setNotebookMode('freeform');
  clearNotebookEditor();
});
