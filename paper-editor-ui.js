// paper-editor-ui.js
// Atlantis [CODEX] Paper Editor: Ace editor, PDF preview, journal matching, and Copilot chat

let aceEditor;
let copilotModal = null;
document.addEventListener('DOMContentLoaded', function() {
  // --- Ace Editor Setup ---
  aceEditor = ace.edit('paper-ace-editor');
  aceEditor.setTheme('ace/theme/textmate');
  aceEditor.session.setMode('ace/mode/markdown');
  aceEditor.setValue('## Start writing your paper here...\n', -1);
  aceEditor.setOptions({
    fontSize: '1.1rem',
    showPrintMargin: false,
    wrap: true
  });
  // Set font color to dark gray
  aceEditor.container.style.color = '#fff';
  aceEditor.renderer.setStyle('ace_custom_fontcolor');
  aceEditor.renderer.$theme.cssText += '.ace_content { color: #fff !important; }';
  aceEditor.session.on('change', updatePdfPreview);
  updatePdfPreview();

  // --- Autosave logic ---
  const paperKey = 'codex_paper_draft';
  // Load from localStorage if present
  const saved = localStorage.getItem(paperKey);
  if (saved) aceEditor.setValue(saved, -1);
  // Save on change
  aceEditor.session.on('change', function() {
    localStorage.setItem(paperKey, aceEditor.getValue());
  });

  // --- Markdown Toolbar ---
  const toolbar = document.getElementById('editor-toolbar');
  if (toolbar) {
    const buttons = [
      {icon: '<b>B</b>', title: 'Bold', insert: '**bold**', select: [2,6]},
      {icon: '<i>I</i>', title: 'Italic', insert: '*italic*', select: [1,7]},
      {icon: 'H1', title: 'Heading 1', insert: '# Heading 1', select: [2,10]},
      {icon: 'H2', title: 'Heading 2', insert: '## Heading 2', select: [3,11]},
      {icon: '•', title: 'Bulleted List', insert: '- List item', select: [2,11]},
      {icon: '1.', title: 'Numbered List', insert: '1. List item', select: [3,12]},
      {icon: '<i class="fas fa-link"></i>', title: 'Link', insert: '[text](url)', select: [1,5]},
      {icon: '<i class="fas fa-image"></i>', title: 'Image', insert: '![alt](url)', select: [2,5]},
    ];
    buttons.forEach(btn => {
      const b = document.createElement('button');
      b.innerHTML = btn.icon;
      b.title = btn.title;
      b.className = 'px-2 py-1 rounded glass border border-cyan-400/20 text-cyan-900 bg-cyan-100 hover:bg-cyan-200 text-xs';
      b.onclick = function() {
        const pos = aceEditor.getCursorPosition();
        aceEditor.session.insert(pos, btn.insert);
        if (btn.select) {
          aceEditor.selection.setSelectionRange({
            start: {row: pos.row, column: pos.column + btn.select[0]},
            end: {row: pos.row, column: pos.column + btn.select[1]}
          });
        }
        aceEditor.focus();
      };
      toolbar.appendChild(b);
    });
  }

  // --- Download PDF ---
  document.getElementById('download-pdf-btn').onclick = function() {
    const content = aceEditor.getValue();
    const preview = document.createElement('div');
    preview.innerHTML = marked.parse(content);
    preview.style.fontFamily = 'Georgia, Times, serif';
    preview.style.color = '#222';
    preview.style.padding = '2em';
    html2pdf().from(preview).set({ margin: 0.5, filename: 'paper.pdf', html2canvas: { scale: 2 } }).save();
  };

  // --- Journal Matching ---
  document.getElementById('journal-match-btn').onclick = async function() {
    const paperContent = aceEditor.getValue();
    const experimentContext = getFullExperimentContext();
    let res, data;
    try {
      res = await fetch('/journal-match', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + (localStorage.getItem('access_token')||'') },
        body: JSON.stringify({ content: paperContent, experiment_context: experimentContext })
      });
      data = await res.json();
      if (!res.ok || !data.journals) throw new Error('No journals');
    } catch (e) {
      // Fallback: try old API format (just paper content)
      try {
        res = await fetch('/journal-match', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + (localStorage.getItem('access_token')||'') },
          body: JSON.stringify({ content: paperContent })
        });
        data = await res.json();
      } catch (err) {
        data = { journals: [] };
      }
    }
    renderJournalMatches(data.journals||[]);
  };

  // --- Copilot Modal ---
  createCopilotModal();
  document.getElementById('open-copilot-btn').onclick = function() {
    copilotModal.style.display = 'block';
  };
});

function updatePdfPreview() {
  const content = aceEditor.getValue();
  const html = marked.parse(content);
  const iframe = document.getElementById('pdf-preview');
  if (iframe) {
    const doc = iframe.contentDocument || iframe.contentWindow.document;
    doc.open();
    doc.write('<html><head><style>body{font-family:Georgia,Times,serif;padding:2em;color:#222;}</style></head><body>' + html + '</body></html>');
    doc.close();
  }
}

function renderJournalMatches(journals) {
  const container = document.getElementById('journal-matches');
  container.innerHTML = '';
  journals.forEach(j => {
    const panel = document.createElement('div');
    panel.className = 'glass rounded-xl holo-glow p-4 flex flex-col gap-2 cursor-pointer hover:bg-cyan-900/10 border border-cyan-400/20';
    panel.innerHTML = `<div class='text-lg font-bold text-cyan-200'>${j.name}</div><div class='text-cyan-100 text-sm'>${j.description||''}</div><div class='text-xs text-cyan-400'>${j.url}</div>`;
    panel.onclick = () => window.open(j.url, '_blank');
    container.appendChild(panel);
  });
}

// --- Copilot Modal Logic ---
function createCopilotModal() {
  copilotModal = document.createElement('div');
  copilotModal.id = 'copilot-modal';
  copilotModal.style.position = 'fixed';
  copilotModal.style.top = '120px';
  copilotModal.style.left = 'calc(50vw - 220px)';
  copilotModal.style.width = '440px';
  copilotModal.style.zIndex = 9999;
  copilotModal.style.background = 'rgba(10,20,40,0.98)';
  copilotModal.style.border = '2px solid #22d3ee';
  copilotModal.style.borderRadius = '1.2rem';
  copilotModal.style.boxShadow = '0 0 32px 0 rgba(0,255,255,0.18)';
  copilotModal.style.display = 'none';
  copilotModal.innerHTML = `
    <div id="copilot-modal-header" style="display:flex;align-items:center;justify-content:space-between;padding:1rem 1.2rem 0 1.2rem;cursor:move;user-select:none;">
      <h3 class="text-cyan-200 text-lg font-semibold m-0 p-0" style="user-select:none;">Copilot</h3>
      <button id="close-copilot-btn" class="text-cyan-400 hover:text-cyan-200 text-xl" style="background:none;border:none;cursor:pointer;">&times;</button>
    </div>
    <div id="copilot-chat-window" class="glass rounded-xl holo-glow scanlines flex-1 p-3 overflow-y-auto" style="min-height:200px; max-height:320px;"></div>
    <form id="copilot-chat-form" class="flex gap-2 m-3">
      <input id="copilot-chat-input" class="flex-1 p-2 rounded glass border border-cyan-400/20 text-cyan-100 bg-transparent" placeholder="Ask Copilot anything..." autocomplete="off" />
      <button type="submit" class="px-3 py-1 rounded glass border border-cyan-400/20 text-cyan-200 text-xs">Send</button>
    </form>
  `;
  document.body.appendChild(copilotModal);
  // Improved Drag logic
  let isDragging = false, dragOffsetX = 0, dragOffsetY = 0;
  const header = copilotModal.querySelector('#copilot-modal-header');
  header.addEventListener('mousedown', function(e) {
    isDragging = true;
    dragOffsetX = e.clientX - copilotModal.offsetLeft;
    dragOffsetY = e.clientY - copilotModal.offsetTop;
    document.body.classList.add('noselect');
    document.addEventListener('mousemove', moveModal);
    document.addEventListener('mouseup', stopDrag);
    e.preventDefault();
  });
  function moveModal(e) {
    if (!isDragging) return;
    let x = e.clientX - dragOffsetX;
    let y = e.clientY - dragOffsetY;
    // Constrain to viewport
    const minX = 0, minY = 0;
    const maxX = window.innerWidth - copilotModal.offsetWidth;
    const maxY = window.innerHeight - copilotModal.offsetHeight;
    x = Math.max(minX, Math.min(x, maxX));
    y = Math.max(minY, Math.min(y, maxY));
    copilotModal.style.left = x + 'px';
    copilotModal.style.top = y + 'px';
  }
  function stopDrag() {
    isDragging = false;
    document.body.classList.remove('noselect');
    document.removeEventListener('mousemove', moveModal);
    document.removeEventListener('mouseup', stopDrag);
  }
  // Prevent text selection during drag
  if (!document.getElementById('copilot-noselect-style')) {
    const style = document.createElement('style');
    style.id = 'copilot-noselect-style';
    style.innerHTML = `.noselect, .noselect * { user-select: none !important; }`;
    document.head.appendChild(style);
  }
  copilotModal.querySelector('#close-copilot-btn').onclick = function() {
    copilotModal.style.display = 'none';
  };
  // Chat logic
  copilotModal.querySelector('#copilot-chat-form').onsubmit = async function(e) {
    e.preventDefault();
    const input = copilotModal.querySelector('#copilot-chat-input');
    const msg = input.value.trim();
    if (!msg) return;
    appendCopilotMessage('user', msg);
    input.value = '';
    const experimentContext = getFullExperimentContext();
    const res = await fetch('/copilot-chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + (localStorage.getItem('access_token')||'') },
      body: JSON.stringify({ message: msg, experiment_context: experimentContext })
    });
    const data = await res.json();
    appendCopilotMessage('copilot', data.reply||'[No response]');
  };
}

function appendCopilotMessage(sender, text) {
  const win = document.getElementById('copilot-chat-window');
  const div = document.createElement('div');
  div.className = sender === 'user' ? 'text-right mb-2' : 'text-left mb-2';
  div.innerHTML = `<span class='inline-block px-3 py-2 rounded ${sender==='user'?'bg-cyan-800 text-cyan-100':'bg-cyan-900 text-cyan-200'}'>${text}</span>`;
  win.appendChild(div);
  win.scrollTop = win.scrollHeight;
}

// --- Helper: Get full experiment context for prompts ---
function getFullExperimentContext() {
  const title = document.getElementById('experiment-title')?.textContent || '';
  const notebook = Array.isArray(window.notebookEntries) ? window.notebookEntries.map(e => `- ${e.content || e.text || ''}`).join('\n') : '';
  let steps = '';
  let results = '';
  if (window.stepMap && window.stepMap.step_map) {
    const nodes = window.stepMap.step_map.nodes || [];
    steps = nodes.map(n => `- ${n.name || n.type || ''}`).join('\n');
    // If results are present in node data, include them
    results = nodes.map(n => n.result ? `- ${n.result}` : '').filter(Boolean).join('\n');
  }
  return `Experiment Title: ${title}\n\nLab Notebook Entries:\n${notebook}\n\nExperiment Steps:\n${steps}\n\nStep Results:\n${results}`;
}
