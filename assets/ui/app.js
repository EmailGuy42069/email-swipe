/* Email Swipe - Optional notes via button click */

const DB_NAME = 'EmailSwipe';
const DB_VERSION = 3;
const STORE_NAME = 'preferences';
const CONFIG_KEY = 'emailSwipeConfig';

const DEFAULT_FOLDERS = [
  { id: 'spam', label: 'Spam', icon: '🗑️', color: '#ef4444' },
  { id: 'archive', label: 'Archive', icon: '🗄️', color: '#6b7280' },
  { id: 'keep', label: 'Keep', icon: '✓', color: '#10b981' },
  { id: 'important', label: 'Important', icon: '⭐', color: '#f59e0b' },
];

const state = {
  emails: [],
  trainingTotal: 0,
  swipeCount: 0,
  advancedMode: false,
  folders: [],
  currentNote: '',  // Note for current email
  editingNote: false,
  isAnimating: false,
};

// ─── IndexedDB ───────────────────────────────────────────────

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onerror = () => reject(req.error);
    req.onsuccess = () => resolve(req.result);
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const store = db.createObjectStore(STORE_NAME, { keyPath: 'id', autoIncrement: true });
        store.createIndex('emailId', 'emailId', { unique: false });
      }
    };
  });
}

async function saveSwipe(swipe) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    tx.objectStore(STORE_NAME).add(swipe);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function getAllSwipes() {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly');
    const req = tx.objectStore(STORE_NAME).getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(tx.error);
  });
}

// ─── Config (Folders from Agent) ─────────────────────────────

function loadConfig() {
  try {
    const config = JSON.parse(localStorage.getItem(CONFIG_KEY) || '{}');
    state.folders = config.folders || DEFAULT_FOLDERS;
    return config;
  } catch {
    state.folders = DEFAULT_FOLDERS;
    return {};
  }
}

function saveConfig(config) {
  localStorage.setItem(CONFIG_KEY, JSON.stringify({ ...loadConfig(), ...config }));
}

// ─── Email Loading ───────────────────────────────────────────

function normalizeEmail(raw, index) {
  return {
    id: raw.id || `email-${index}`,
    sender: raw.sender || raw.from?.split('@')[0] || 'Unknown',
    from: raw.from || raw.sender || '',
    subject: raw.subject || '(no subject)',
    snippet: raw.snippet || raw.body || '',
    html: raw.html || raw.bodyHtml || '',
    date: raw.date || '',
    hasAttachment: raw.hasAttachment || false,
    isNewsletter: raw.isNewsletter || false,
  };
}

async function fetchEmailList(url) {
  try {
    const res = await fetch(url);
    if (!res.ok) return [];
    const data = await res.json();
    const list = Array.isArray(data) ? data : data.emails || [];
    return list.map(normalizeEmail);
  } catch {
    return [];
  }
}

async function loadFromFile() {
  const agentEmails = await fetchEmailList('emails.json');
  if (agentEmails.length > 0) return agentEmails;
  return fetchEmailList('demo-emails.json');
}

async function loadEmails(emails) {
  state.trainingTotal = emails.length;
  state.emails = emails.map(normalizeEmail);
  state.currentNote = '';
  const swipes = await getAllSwipes();
  state.swipeCount = swipes.length;
  updateProgress();
  renderCards();
}

// ─── Features ────────────────────────────────────────────────

function extractFeatures(email) {
  const domain = (email.from || '').split('@')[1] || '';
  return {
    hasAttachment: email.hasAttachment || false,
    isNewsletter: email.isNewsletter || false,
    senderDomain: domain,
  };
}

// ─── Export ──────────────────────────────────────────────────

async function exportPreferences() {
  const swipes = await getAllSwipes();
  const preferences = {
    metadata: {
      generatedAt: new Date().toISOString(),
      totalSwipes: swipes.length,
      version: '1.4'
    },
    folders: state.folders.map(f => f.id),
    swipes: swipes.map(s => ({
      emailId: s.emailId,
      sender: s.sender,
      from: s.from,
      subject: s.subject,
      action: s.action,
      note: s.note || '',
      timestamp: s.timestamp,
    })),
    senderRules: extractSenderRules(swipes),
  };
  
  const blob = new Blob([JSON.stringify(preferences, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'preferences.json';
  a.click();
  URL.revokeObjectURL(url);
  
  // Also export folder creation requests
  const pendingFolders = JSON.parse(localStorage.getItem('pendingFolders') || '[]');
  if (pendingFolders.length > 0) {
    const folderBlob = new Blob([JSON.stringify({ createFolders: pendingFolders }, null, 2)], { type: 'application/json' });
    const folderUrl = URL.createObjectURL(folderBlob);
    const folderA = document.createElement('a');
    folderA.href = folderUrl;
    folderA.download = 'folder-requests.json';
    folderA.click();
    URL.revokeObjectURL(folderUrl);
  }
  
  return preferences;
}

function extractSenderRules(swipes) {
  const senderActions = {};
  for (const swipe of swipes) {
    const from = swipe.from || swipe.sender;
    if (!senderActions[from]) senderActions[from] = {};
    senderActions[from][swipe.action] = (senderActions[from][swipe.action] || 0) + 1;
  }
  const rules = {};
  for (const [sender, actions] of Object.entries(senderActions)) {
    rules[sender] = Object.entries(actions).sort((a, b) => b[1] - a[1])[0][0];
  }
  return rules;
}

// ─── UI Rendering ────────────────────────────────────────────

function updateProgress() {
  const goal = state.trainingTotal || 1;
  document.getElementById('progress-count').textContent = `${state.swipeCount} / ${goal}`;
  document.getElementById('progress-fill').style.width = `${Math.min(100, (state.swipeCount / goal) * 100)}%`;
}

function renderCards() {
  const stack = document.getElementById('card-stack');
  const empty = document.getElementById('empty-state');
  
  if (state.emails.length === 0) {
    stack.innerHTML = '';
    empty.classList.remove('hidden');
    return;
  }
  
  empty.classList.add('hidden');
  
  // Render top card
  const email = state.emails[0];
  stack.innerHTML = '';
  
  const card = createCard(email);
  stack.appendChild(card);
  
  // Update note button state
  updateNoteButton();
}

function createCard(email) {
  const card = document.createElement('div');
  card.className = 'email-card';
  
  const badges = [];
  if (email.hasAttachment) badges.push('<span class="badge">📎</span>');
  if (email.isNewsletter) badges.push('<span class="badge">📰</span>');
  
  const bodyContent = email.html 
    ? `<iframe class="email-body" sandbox="" srcdoc="${escapeHtml(wrapEmailHtml(email.html))}"></iframe>`
    : `<div class="email-text">${escapeHtml(email.snippet)}</div>`;
  
  card.innerHTML = `
    <div class="email-header">
      <div class="email-sender">${escapeHtml(email.sender)}</div>
      <div class="email-from">${escapeHtml(email.from)}</div>
      <div class="email-subject">${escapeHtml(email.subject)}</div>
      <div class="email-meta">
        ${badges.join('')}
        <span class="email-date">${escapeHtml(email.date || '')}</span>
      </div>
    </div>
    <div class="email-content">
      ${bodyContent}
    </div>
    <button class="btn-note" id="btn-add-note" title="Add note">
      📝 ${state.currentNote ? 'Edit Note' : 'Add Note'}
    </button>
  `;
  
  // Add note button listener
  const noteBtn = card.querySelector('#btn-add-note');
  noteBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    showNoteModal();
  });
  
  return card;
}

function updateNoteButton() {
  const btn = document.getElementById('btn-add-note');
  if (btn) {
    btn.innerHTML = state.currentNote ? '📝 Edit Note' : '📝 Add Note';
    if (state.currentNote) {
      btn.classList.add('has-note');
    } else {
      btn.classList.remove('has-note');
    }
  }
}

function wrapEmailHtml(html) {
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 14px; line-height: 1.5; margin: 0; padding: 16px; color: #1a1f2e; }
    img { max-width: 100%; height: auto; }
    a { color: #5b4cdb; pointer-events: none; }
    table { max-width: 100%; }
  </style></head><body>${html}</body></html>`;
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ─── Advanced Panel ──────────────────────────────────────────

function renderFolderZones() {
  const container = document.getElementById('folder-zones');
  container.innerHTML = '';
  
  state.folders.forEach(folder => {
    const zone = document.createElement('div');
    zone.className = 'folder-zone';
    zone.dataset.action = folder.id;
    zone.style.setProperty('--zone-color', folder.color);
    zone.innerHTML = `
      <span class="zone-icon">${folder.icon}</span>
      <span class="zone-label">${folder.label}</span>
    `;
    zone.addEventListener('click', () => handleAction(folder.id));
    container.appendChild(zone);
  });
}

function toggleAdvanced(show) {
  state.advancedMode = show;
  const panel = document.getElementById('advanced-panel');
  const simpleActions = document.getElementById('simple-actions');
  
  if (show) {
    panel.classList.remove('hidden');
    simpleActions.classList.add('hidden');
    renderFolderZones();
  } else {
    panel.classList.add('hidden');
    simpleActions.classList.remove('hidden');
  }
}

// ─── Actions ─────────────────────────────────────────────────

function handleAction(action) {
  if (state.isAnimating || state.emails.length === 0) return;
  
  completeSwipe(action);
}

async function completeSwipe(action) {
  if (state.isAnimating) return;
  state.isAnimating = true;
  
  const email = state.emails[0];
  const note = state.currentNote;
  
  // Animate card away
  const card = document.querySelector('.email-card');
  if (card) {
    const directions = { spam: -1, archive: -1, keep: 1, important: 1 };
    const dir = directions[action] || -1;
    card.style.transform = `translateX(${dir * 100}vw) rotate(${dir * 10}deg)`;
    card.style.opacity = '0';
  }
  
  // Save swipe
  await saveSwipe({
    emailId: email.id,
    sender: email.sender,
    from: email.from,
    subject: email.subject,
    snippet: email.snippet,
    action,
    note: note || '',
    timestamp: new Date().toISOString(),
    features: extractFeatures(email),
  });
  
  state.swipeCount++;
  state.emails.shift();
  state.currentNote = '';  // Reset note for next email
  
  setTimeout(() => {
    updateProgress();
    renderCards();
    state.isAnimating = false;
  }, 300);
}

// ─── Note Modal ──────────────────────────────────────────────

function showNoteModal() {
  if (state.emails.length === 0) return;
  
  const email = state.emails[0];
  const modal = document.getElementById('note-modal');
  const context = document.getElementById('note-context');
  const input = document.getElementById('note-input');
  
  context.textContent = email.subject;
  input.value = state.currentNote;
  input.placeholder = "Why this decision? (e.g., 'Always keep receipts')";
  
  modal.classList.remove('hidden');
  state.editingNote = true;
  input.focus();
}

function hideNoteModal() {
  document.getElementById('note-modal').classList.add('hidden');
  state.editingNote = false;
}

function saveNote() {
  const input = document.getElementById('note-input');
  state.currentNote = input.value.trim();
  hideNoteModal();
  updateNoteButton();
}

// ─── Create Folder ───────────────────────────────────────────

function showCreateFolderModal() {
  const modal = document.getElementById('create-folder-modal');
  const input = document.getElementById('new-folder-name');
  input.value = '';
  modal.classList.remove('hidden');
  input.focus();
}

function hideCreateFolderModal() {
  document.getElementById('create-folder-modal').classList.add('hidden');
}

function requestNewFolder() {
  const name = document.getElementById('new-folder-name').value.trim();
  if (!name) return;
  
  // Store pending folder request
  const pending = JSON.parse(localStorage.getItem('pendingFolders') || '[]');
  pending.push({
    name,
    requestedAt: new Date().toISOString(),
  });
  localStorage.setItem('pendingFolders', JSON.stringify(pending));
  
  // Add to UI temporarily
  const newFolder = {
    id: `custom-${Date.now()}`,
    label: name,
    icon: '📁',
    color: '#6366f1',
    pending: true,
  };
  state.folders.push(newFolder);
  renderFolderZones();
  hideCreateFolderModal();
  
  alert(`Folder "${name}" will be created when you export. The agent will create it in your email account.`);
}

// ─── Event Listeners ─────────────────────────────────────────

function init() {
  loadConfig();
  
  // Simple action buttons
  document.querySelectorAll('#simple-actions .swipe-btn').forEach(btn => {
    btn.addEventListener('click', () => handleAction(btn.dataset.action));
  });
  
  // Advanced toggle
  document.getElementById('btn-advanced').addEventListener('click', () => toggleAdvanced(true));
  document.getElementById('btn-close-advanced').addEventListener('click', () => toggleAdvanced(false));
  
  // Export
  document.getElementById('btn-export').addEventListener('click', exportPreferences);
  
  // Note modal
  document.getElementById('btn-save-note').addEventListener('click', saveNote);
  document.getElementById('btn-cancel-note').addEventListener('click', hideNoteModal);
  
  // Create folder
  document.getElementById('btn-create-folder').addEventListener('click', showCreateFolderModal);
  document.getElementById('btn-cancel-folder').addEventListener('click', hideCreateFolderModal);
  document.getElementById('btn-confirm-folder').addEventListener('click', requestNewFolder);
  document.getElementById('new-folder-name').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') requestNewFolder();
  });
  
  // Keyboard shortcuts
  document.addEventListener('keydown', (e) => {
    if (state.isAnimating || state.emails.length === 0) return;
    if (state.editingNote) return;  // Don't intercept when typing note
    if (document.querySelector('.modal:not(.hidden)')) return;
    
    const keyMap = {
      ArrowLeft: 'archive',
      ArrowUp: 'spam',
      ArrowRight: 'keep',
    };
    if (keyMap[e.key]) {
      e.preventDefault();
      handleAction(keyMap[e.key]);
    }
  });
  
  // Touch/swipe support
  initTouchSupport();
  
  // Load emails
  loadFromFile().then(emails => {
    if (emails.length > 0) loadEmails(emails);
  });
  
  window.EmailSwipe = { loadEmails, exportPreferences, setFolders: (folders) => {
    state.folders = folders;
    saveConfig({ folders });
    if (state.advancedMode) renderFolderZones();
  }};
}

function initTouchSupport() {
  let touchStartX = 0;
  let touchStartY = 0;
  
  document.addEventListener('touchstart', (e) => {
    touchStartX = e.touches[0].clientX;
    touchStartY = e.touches[0].clientY;
  }, { passive: true });
  
  document.addEventListener('touchend', (e) => {
    if (state.isAnimating || state.emails.length === 0) return;
    if (state.advancedMode) return;
    if (state.editingNote) return;
    
    const touchEndX = e.changedTouches[0].clientX;
    const touchEndY = e.changedTouches[0].clientY;
    const deltaX = touchEndX - touchStartX;
    const deltaY = touchEndY - touchStartY;
    
    // Horizontal swipe
    if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > 80) {
      if (deltaX > 0) handleAction('keep');
      else handleAction('archive');
    }
    // Vertical swipe (up for spam)
    else if (deltaY < -80 && Math.abs(deltaY) > Math.abs(deltaX)) {
      handleAction('spam');
    }
  }, { passive: true });
}

document.addEventListener('DOMContentLoaded', init);
