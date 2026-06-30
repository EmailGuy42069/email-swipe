/* Email Swipe - Agent-driven training UI */

const DB_NAME = 'EmailSwipe';
const DB_VERSION = 1;
const STORE_NAME = 'preferences';
const SWIPE_THRESHOLD = window.matchMedia('(pointer: coarse)').matches ? 60 : 80;

const FOLDER_ACTIONS = ['archive', 'important', 'unsubscribe', 'block'];

const INTRO_CARD = {
  id: '__intro__',
  isIntro: true,
  sender: '',
  from: '',
  subject: '← Spam    Keep →',
  snippet: 'Swipe left for spam. Swipe right for keep.',
};

const state = {
  emails: [],
  trainingTotal: 0,
  swipeCount: 0,
  advancedMode: localStorage.getItem('email-swipe-advanced') === 'true',
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
        db.createObjectStore(STORE_NAME, { keyPath: 'id', autoIncrement: true });
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
    req.onerror = () => reject(req.error);
  });
}

// ─── Email loading (agent injects) ───────────────────────────

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
    isIntro: raw.isIntro || false,
  };
}

function withIntro(emails) {
  return [INTRO_CARD, ...emails];
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
  const normalized = emails.map(normalizeEmail);
  state.trainingTotal = normalized.length;
  state.emails = withIntro(normalized);
  const swipes = await getAllSwipes();
  state.swipeCount = swipes.length;
  updateProgress();
  renderCards();
}

// ─── Feature extraction ──────────────────────────────────────

function extractFeatures(email) {
  const domain = (email.from || '').split('@')[1] || '';
  const text = `${email.subject} ${email.snippet}`.toLowerCase();
  const keywords = [];
  for (const kw of ['unsubscribe', 'receipt', 'newsletter', 'digest', 'promo', 'urgent', 'reminder']) {
    if (text.includes(kw)) keywords.push(kw);
  }
  return { hasAttachment: email.hasAttachment || false, isNewsletter: email.isNewsletter || false, senderDomain: domain, keywords };
}

function extractSenderDomain(from) {
  return (from || '').split('@')[1] || '';
}

// ─── Export ──────────────────────────────────────────────────

async function exportPreferences() {
  const swipes = await getAllSwipes();
  const preferences = buildPreferences(swipes);
  const blob = new Blob([JSON.stringify(preferences, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'preferences.json';
  a.click();
  URL.revokeObjectURL(url);
  return preferences;
}

function buildPreferences(swipes) {
  const byAction = { keep: [], spam: [], archive: [], important: [], unsubscribe: [], block: [] };
  for (const swipe of swipes) {
    if (byAction[swipe.action]) byAction[swipe.action].push(swipe);
  }
  return {
    metadata: { generatedAt: new Date().toISOString(), totalSwipes: swipes.length, version: '1.2' },
    patterns: extractPatterns(byAction),
    fewShotExamples: generateFewShotExamples(swipes),
    senderRules: extractSenderRules(swipes),
    folderRules: extractFolderRules(swipes),
  };
}

function extractPatterns(byAction) {
  const patterns = { alwaysKeep: [], alwaysSpam: [], alwaysArchive: [], alwaysImportant: [], alwaysUnsubscribe: [], alwaysBlock: [] };
  const actionMap = { keep: 'alwaysKeep', spam: 'alwaysSpam', archive: 'alwaysArchive', important: 'alwaysImportant', unsubscribe: 'alwaysUnsubscribe', block: 'alwaysBlock' };

  for (const [action, key] of Object.entries(actionMap)) {
    const domainCounts = {};
    const keywordCounts = {};
    for (const swipe of byAction[action] || []) {
      const domain = swipe.features?.senderDomain || extractSenderDomain(swipe.from);
      if (domain) domainCounts[domain] = (domainCounts[domain] || 0) + 1;
      for (const kw of (swipe.features?.keywords || [])) {
        keywordCounts[kw] = (keywordCounts[kw] || 0) + 1;
      }
    }
    patterns[key] = [
      ...Object.entries(domainCounts).filter(([, c]) => c >= 2).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([d, c]) => `Emails from ${d} (${c}x)`),
      ...Object.entries(keywordCounts).filter(([, c]) => c >= 2).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([k, c]) => `Contains "${k}" (${c}x)`),
    ];
  }
  return patterns;
}

function generateFewShotExamples(swipes) {
  const seen = new Set();
  const examples = [];
  for (const swipe of swipes) {
    const key = `${swipe.from}-${swipe.action}`;
    if (seen.has(key)) continue;
    seen.add(key);
    examples.push({
      email: { subject: swipe.subject, sender: swipe.sender, snippet: swipe.snippet || '' },
      decision: swipe.action,
      folder: FOLDER_ACTIONS.includes(swipe.action) ? swipe.action : null,
      reasoning: generateReasoning(swipe),
    });
    if (examples.length >= 10) break;
  }
  return examples;
}

function generateReasoning(swipe) {
  const f = swipe.features || {};
  const parts = [];
  if (f.isNewsletter) parts.push('newsletter');
  if (f.hasAttachment) parts.push('has attachment');
  if (f.senderDomain) parts.push(`from ${f.senderDomain}`);
  return `${swipe.action} — ${parts.length ? parts.join(', ') : 'user preference'}`;
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

function extractFolderRules(swipes) {
  const rules = {};
  for (const swipe of swipes) {
    if (FOLDER_ACTIONS.includes(swipe.action)) rules[swipe.from || swipe.sender] = swipe.action;
  }
  return rules;
}

// ─── Card UI ─────────────────────────────────────────────────

function updateProgress() {
  const goal = state.trainingTotal || 1;
  document.getElementById('progress-count').textContent = `${state.swipeCount} / ${goal}`;
  document.getElementById('progress-fill').style.width = `${Math.min(100, (state.swipeCount / goal) * 100)}%`;
}

function updateAdvancedMode() {
  document.getElementById('folder-actions').classList.toggle('hidden', !state.advancedMode);
}

function renderCards() {
  const stack = document.getElementById('card-stack');
  const empty = document.getElementById('empty-state');
  stack.innerHTML = '';

  if (state.emails.length === 0) {
    empty.classList.remove('hidden');
    stack.style.display = 'none';
    const title = empty.querySelector('.empty-title');
    const hint = empty.querySelector('.empty-hint');
    if (state.trainingTotal > 0) {
      if (title) title.textContent = 'All done!';
      if (hint) hint.style.display = '';
    } else {
      if (title) title.textContent = 'Waiting for emails…';
      if (hint) hint.textContent = 'Your agent will load your inbox, then refresh this page.';
    }
    return;
  }

  empty.classList.add('hidden');
  stack.style.display = 'block';

  const top = state.emails[0];
  const showBehind = !top.isIntro && state.emails.length > 1;

  if (showBehind) {
    const behind = createCard(state.emails[1], true);
    behind.style.zIndex = '1';
    stack.appendChild(behind);
  }

  const front = createCard(top, false);
  front.style.zIndex = '2';
  stack.appendChild(front);
  initCardDrag(front, top);
}

function createCard(email, isBehind) {
  const card = document.createElement('div');
  card.className = `email-card${isBehind ? ' behind' : ' front'}${email.isIntro ? ' intro' : ''}`;
  card.dataset.emailId = email.id;

  if (email.isIntro) {
    card.innerHTML = `
      <div class="swipe-overlay spam">SPAM</div>
      <div class="swipe-overlay keep">KEEP</div>
      <div class="intro-subject">${escapeHtml(email.subject)}</div>
      <div class="intro-snippet">${escapeHtml(email.snippet)}</div>
    `;
    return card;
  }

  const badges = [];
  if (email.hasAttachment) badges.push('<span class="badge attachment">Attachment</span>');
  if (email.isNewsletter) badges.push('<span class="badge newsletter">Newsletter</span>');

  const useHtml = !isBehind && email.html;
  const bodyMarkup = useHtml
    ? '<iframe class="email-html" sandbox="" title="Email body"></iframe>'
    : `<div class="card-snippet">${escapeHtml(email.snippet)}</div>`;

  card.innerHTML = `
    <div class="swipe-overlay spam">SPAM</div>
    <div class="swipe-overlay keep">KEEP</div>
    <div class="card-header">
      <div class="card-sender">${escapeHtml(email.sender)}</div>
      <div class="card-from">${escapeHtml(email.from)}</div>
      <div class="card-subject">${escapeHtml(email.subject)}</div>
      <div class="card-meta">
        <div class="card-badges">${badges.join('')}</div>
        <span>${escapeHtml(email.date || '')}</span>
      </div>
    </div>
    <div class="card-body">${bodyMarkup}</div>
  `;

  if (useHtml) {
    card.querySelector('.email-html').srcdoc = wrapEmailHtml(email.html);
  }

  return card;
}

function wrapEmailHtml(html) {
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 14px; line-height: 1.5; margin: 0; padding: 0; color: #1a1f2e; word-wrap: break-word; }
    img { max-width: 100%; height: auto; }
    a { color: #5b4cdb; pointer-events: none; }
  </style></head><body>${html}</body></html>`;
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function initCardDrag(card, email) {
  if (card.dataset.dragReady) return;
  card.dataset.dragReady = '1';

  let startX = 0;
  let currentX = 0;
  let dragging = false;
  let pointerId = null;

  const setOffset = (x) => {
    currentX = x;
    card.style.transform = `translate3d(${x}px, 0, 0) rotate(${x * 0.04}deg)`;
    card.classList.toggle('show-spam', x < -40);
    card.classList.toggle('show-keep', x > 40);
  };

  const reset = () => {
    card.style.transform = '';
    card.classList.remove('show-spam', 'show-keep', 'dragging');
    document.body.classList.remove('swiping');
    dragging = false;
    pointerId = null;
    currentX = 0;
    startX = 0;
  };

  const onEnd = () => {
    if (!dragging) return;
    card.releasePointerCapture?.(pointerId);
    dragging = false;
    document.body.classList.remove('swiping');
    card.classList.remove('dragging');

    let action = null;
    if (currentX < -SWIPE_THRESHOLD) action = 'spam';
    else if (currentX > SWIPE_THRESHOLD) action = 'keep';

    if (action) swipeCard(card, email, action);
    else reset();
  };

  card.addEventListener('pointerdown', (e) => {
    if (card.style.pointerEvents === 'none') return;
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    if (email.html && e.target.closest('.card-body')) return;

    dragging = true;
    pointerId = e.pointerId;
    startX = e.clientX;
    card.classList.add('dragging');
    document.body.classList.add('swiping');
    card.setPointerCapture(e.pointerId);
  });

  card.addEventListener('pointermove', (e) => {
    if (!dragging || e.pointerId !== pointerId) return;
    e.preventDefault();
    setOffset(e.clientX - startX);
  });

  card.addEventListener('pointerup', onEnd);
  card.addEventListener('pointercancel', reset);
}

function promoteBehindCard(stack) {
  const behind = stack.querySelector('.email-card.behind');
  if (!behind || state.emails.length === 0) return null;

  const email = state.emails[0];
  behind.classList.remove('behind');
  behind.classList.add('front');
  behind.style.zIndex = '2';
  behind.style.transform = '';

  if (email.html) {
    const body = behind.querySelector('.card-body');
    body.innerHTML = '<iframe class="email-html" sandbox="" title="Email body"></iframe>';
    body.querySelector('.email-html').srcdoc = wrapEmailHtml(email.html);
  }

  initCardDrag(behind, email);
  return behind;
}

function replaceBehindCard(stack) {
  stack.querySelector('.email-card.behind')?.remove();

  const top = state.emails[0];
  if (top.isIntro || state.emails.length < 2) return;

  const behind = createCard(state.emails[1], true);
  behind.style.zIndex = '1';
  stack.insertBefore(behind, stack.firstChild);
}

function swipeCard(card, email, action) {
  if (state.isAnimating) return;
  state.isAnimating = true;

  const stack = document.getElementById('card-stack');

  card.classList.remove('dragging', 'show-spam', 'show-keep');
  card.style.pointerEvents = 'none';
  card.style.zIndex = '3';
  card.style.transition = 'transform 0.26s ease-out, opacity 0.26s ease-out';

  const offscreen = (action === 'spam' ? -1 : 1) * window.innerWidth * 0.85;
  const rotation = action === 'spam' ? -16 : 16;
  requestAnimationFrame(() => {
    card.style.transform = `translate3d(${offscreen}px, 0, 0) rotate(${rotation}deg)`;
    card.style.opacity = '0';
  });

  if (!email.isIntro) {
    state.swipeCount++;
    updateProgress();
    saveSwipe({
      emailId: email.id,
      sender: email.sender,
      from: email.from,
      subject: email.subject,
      snippet: email.snippet,
      action,
      timestamp: new Date().toISOString(),
      features: extractFeatures(email),
    });
  }

  state.emails.shift();

  if (state.emails.length === 0) {
    setTimeout(() => {
      card.remove();
      renderCards();
      state.isAnimating = false;
    }, 260);
    return;
  }

  const hadBehind = !!stack.querySelector('.email-card.behind');
  if (hadBehind) {
    promoteBehindCard(stack);
    replaceBehindCard(stack);
  } else {
    renderCards();
  }

  setTimeout(() => {
    card.remove();
    state.isAnimating = false;
  }, 260);
}

function triggerAction(action) {
  const card = document.querySelector('#card-stack .email-card.front');
  if (!card || card.style.pointerEvents === 'none' || state.emails.length === 0) return;
  swipeCard(card, state.emails[0], action);
}

// ─── Init ────────────────────────────────────────────────────

async function boot() {
  updateAdvancedMode();
  const emails = await loadFromFile();
  if (emails.length > 0) {
    await loadEmails(emails);
  } else {
    renderCards();
  }
}

function init() {
  const advancedCheckbox = document.getElementById('advanced-mode');
  advancedCheckbox.checked = state.advancedMode;
  advancedCheckbox.addEventListener('change', () => {
    state.advancedMode = advancedCheckbox.checked;
    localStorage.setItem('email-swipe-advanced', state.advancedMode);
    updateAdvancedMode();
  });

  document.getElementById('btn-export').addEventListener('click', exportPreferences);
  document.querySelectorAll('.action-btn, .folder-btn').forEach(btn => {
    btn.addEventListener('click', () => triggerAction(btn.dataset.action));
  });

  document.addEventListener('keydown', (e) => {
    const keyMap = { ArrowLeft: 'spam', ArrowRight: 'keep' };
    if (keyMap[e.key]) { e.preventDefault(); triggerAction(keyMap[e.key]); }
  });

  window.EmailSwipe = { loadEmails, exportPreferences };
  boot();
}

document.addEventListener('DOMContentLoaded', init);
