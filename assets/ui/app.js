/* Email Swipe — training UI (spam / keep / important) */

const DB_NAME = 'EmailSwipe';
const DB_VERSION = 5;
const STORE_NAME = 'preferences';
const SWIPE_THRESHOLD = window.matchMedia('(pointer: coarse)').matches ? 60 : 80;
const DOUBLE_TAP_MS = 320;
const TAP_MOVE_TOLERANCE = 14;
const SETTINGS_KEY = 'email-swipe-settings';
const INBOX_FP_KEY = 'email-swipe-inbox-fp';
const SESSION_PROGRESS_ROUTE = '/api/session-progress';

const ACTION_LABELS = { spam: "Don't Keep", keep: 'Keep', important: 'Important' };

// Inbox-action route kinds (as opposed to folder-match kinds). A route with one
// of these is a plain training action rather than a folder classifier.
const ACTION_KINDS = new Set(['keep', 'important', 'spam']);

// Advanced mode prefills the editor with these familiar buckets, but they are
// fully editable — the user can rename, retype, remove, or replace them.
const BASE_FOLDER_ROUTES = [
  { id: 'route-dont-keep', name: "Don't Keep", action: 'spam' },
  { id: 'route-important', name: 'Important', action: 'important' },
  { id: 'route-keep', name: 'Keep', action: 'keep' },
];

const DEFAULT_FOLDER_ROUTES = BASE_FOLDER_ROUTES;

function routeKind(route) {
  return route.action || route.matchType || 'descriptor';
}

const DEFAULT_SETTINGS = {
  version: '2.1',
  agent: {
    enabled: false,
    name: '',
    scanFrequency: 'twice_daily',
    autonomyLevel: 'recommend',
  },
  unifiedInbox: {
    enabled: false,
    defaultAccountId: null,
    accounts: [],
  },
  access: {
    exploreRemoteReachability: false,
  },
  folders: {
    advancedRoutingEnabled: false,
    preference: 'minimal',
    routes: [],
    rememberLastFolder: true,
    lastFolderId: null,
  },
  platformRules: {
    mode: 'suggest_only',
    neverRemoveFromInbox: true,
    allowedActions: ['label', 'star'],
    forbiddenActions: ['delete', 'skip_inbox', 'auto_archive', 'block_sender'],
    maxSuggestedRules: 12,
  },
  rhythm: {
    preferredTimes: ['08:00', '17:00'],
    digestStyle: 'short',
    digestSections: ['needs_reply', 'score_trend', 'training_gaps'],
    includeScoreTrend: true,
    quietHours: null,
  },
  context: {
    problemToSolve: '',
    notes: '',
  },
};

const ACCOUNT_JSON_EXAMPLE = [
  {
    id: 'work-gmail',
    label: 'Work Gmail',
    provider: 'gmail',
    role: 'work',
  },
];

const INTRO_CARD = {
  id: '__intro__',
  isIntro: true,
  sender: '',
  from: '',
  subject: "Don't Keep  ·  Keep  ·  Important",
  snippet: "Left = don't keep · Right = keep · Double-tap = important.",
};

const state = {
  emails: [],
  allEmails: [],
  trainingTotal: 0,
  swipeCount: 0,
  swipes: [],
  settings: loadSettings(),
  isAnimating: false,
  pendingBatch: null,
  correctionNotes: {},
  victoryReview: { pile: null, emailId: null },
  sessionMeta: null,
  pendingSwipe: null,
  sessionStatus: null,
  accountsStatus: [],
  intakeSnapshot: null,
  inboxFingerprint: null,
  pendingScoreBars: null,
};

// ─── Settings ────────────────────────────────────────────────

function loadSettings() {
  try {
    const stored = localStorage.getItem(SETTINGS_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      return {
        ...DEFAULT_SETTINGS,
        ...parsed,
        agent: { ...DEFAULT_SETTINGS.agent, ...(parsed.agent || {}) },
        unifiedInbox: { ...DEFAULT_SETTINGS.unifiedInbox, ...(parsed.unifiedInbox || {}) },
        access: { ...DEFAULT_SETTINGS.access, ...(parsed.access || {}) },
        folders: { ...DEFAULT_SETTINGS.folders, ...(parsed.folders || {}) },
        platformRules: { ...DEFAULT_SETTINGS.platformRules, ...(parsed.platformRules || {}) },
        rhythm: { ...DEFAULT_SETTINGS.rhythm, ...(parsed.rhythm || {}) },
        context: { ...DEFAULT_SETTINGS.context, ...(parsed.context || {}) },
      };
    }
  } catch { /* ignore */ }
  return structuredClone(DEFAULT_SETTINGS);
}

function saveSettingsToStorage(settings) {
  state.settings = settings;
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
}

let statusBannerTimer = null;

function showStatusBanner(message, tone = 'info') {
  const el = document.getElementById('status-banner');
  if (!el) return;
  el.textContent = message;
  el.className = `status-banner visible ${tone}`;
  clearTimeout(statusBannerTimer);
  const duration = tone === 'error' ? 12000 : 7000;
  statusBannerTimer = setTimeout(() => el.classList.remove('visible'), duration);
}

function setSettingsSaveStatus(message, tone = 'info') {
  const el = document.getElementById('settings-save-status');
  if (!el) return;
  if (!message) {
    el.classList.add('hidden');
    el.textContent = '';
    return;
  }
  el.textContent = message;
  el.className = `settings-save-status ${tone}`;
}

function renderVictoryCompileStatus(compileResult = {}) {
  const el = document.getElementById('victory-compile-status');
  if (!el) return;
  if (compileResult.ok) {
    el.textContent = 'Saved to your machine and compiled training artifacts.';
    el.className = 'compile-status success';
    return;
  }
  if (compileResult.offline) {
    el.textContent = 'Server not reachable — swipes are not saved or compiled. Start serve-ui.py and export again.';
    el.className = 'compile-status error';
    return;
  }
  if (compileResult.error) {
    el.textContent = `Compile failed: ${compileResult.error}. Your swipes may be saved but rules were not updated.`;
    el.className = 'compile-status error';
    return;
  }
  el.classList.add('hidden');
}

async function fetchSettingsFile() {
  try {
    const res = await fetch(`settings.json?t=${Date.now()}`, { cache: 'no-store' });
    if (!res.ok) return null;
    const data = await res.json();
    saveSettingsToStorage({
      ...DEFAULT_SETTINGS,
      ...data,
      agent: { ...DEFAULT_SETTINGS.agent, ...(data.agent || {}) },
      unifiedInbox: { ...DEFAULT_SETTINGS.unifiedInbox, ...(data.unifiedInbox || {}) },
      access: { ...DEFAULT_SETTINGS.access, ...(data.access || {}) },
      folders: { ...DEFAULT_SETTINGS.folders, ...(data.folders || {}) },
      platformRules: { ...DEFAULT_SETTINGS.platformRules, ...(data.platformRules || {}) },
      rhythm: { ...DEFAULT_SETTINGS.rhythm, ...(data.rhythm || {}) },
      context: { ...DEFAULT_SETTINGS.context, ...(data.context || {}) },
    });
    return data;
  } catch {
    return null;
  }
}

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

async function clearSwipes() {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    tx.objectStore(STORE_NAME).clear();
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

let _progressSaveTimer = null;

async function fetchSessionProgress() {
  try {
    const res = await fetch(`${SESSION_PROGRESS_ROUTE}?t=${Date.now()}`, { cache: 'no-store' });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

async function persistSessionProgress({ completed = false, clear = false } = {}) {
  try {
    const payload = clear
      ? { clear: true }
      : {
          inboxFingerprint: state.inboxFingerprint || null,
          swipes: state.swipes || [],
          correctionNotes: state.correctionNotes || {},
          completed: Boolean(completed),
        };
    await fetch(SESSION_PROGRESS_ROUTE, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } catch {
    // Offline — IndexedDB still holds the latest swipe locally.
  }
}

function schedulePersistSessionProgress(opts = {}) {
  clearTimeout(_progressSaveTimer);
  _progressSaveTimer = setTimeout(() => {
    persistSessionProgress(opts);
  }, 200);
}

async function replaceLocalSwipes(swipes) {
  await clearSwipes();
  for (const swipe of swipes || []) {
    await saveSwipe(swipe);
  }
}

// ─── Email loading ───────────────────────────────────────────

function looksLikeHtml(str) {
  if (!str || typeof str !== 'string') return false;
  const trimmed = str.trimStart();
  if (!trimmed) return false;
  if (/^<!doctype\s+html/i.test(trimmed)) return true;
  if (/^<html[\s>]/i.test(trimmed)) return true;
  if (/^<(head|body|div|table|p|span|center|meta|style)\b/i.test(trimmed)) return true;
  return /<[a-z][\s>]/i.test(trimmed) && /<\/[a-z]+>/i.test(trimmed);
}

function stripHtmlTags(str) {
  const tmp = document.createElement('div');
  tmp.innerHTML = str;
  return (tmp.textContent || '').replace(/\s+/g, ' ').trim();
}

function unwrapEmailHtml(html) {
  if (!html || typeof html !== 'string') return '';
  let out = html.trim();
  out = out.replace(/^<!doctype[^>]*>/i, '').trim();
  if (/^<html[\s>]/i.test(out) || /<body[\s>]/i.test(out)) {
    try {
      const doc = new DOMParser().parseFromString(out, 'text/html');
      const inner = doc.body?.innerHTML?.trim();
      if (inner) return inner;
    } catch {
      // keep best-effort trimmed string
    }
  }
  return out;
}

function normalizeEmail(raw, index) {
  let html = String(raw.html || raw.bodyHtml || '').trim();
  let snippet = String(raw.snippet || '').trim();
  const body = String(raw.body || '').trim();

  if (!html && body) {
    if (looksLikeHtml(body)) html = body;
    else if (!snippet) snippet = body;
  }

  if (!html && snippet && looksLikeHtml(snippet)) {
    html = snippet;
    snippet = '';
  }

  if (html) {
    html = unwrapEmailHtml(html);
    if (!snippet) snippet = stripHtmlTags(html).slice(0, 300);
  }

  if (!snippet && body && body !== html) {
    snippet = looksLikeHtml(body) ? stripHtmlTags(body).slice(0, 300) : body.slice(0, 300);
  }

  return {
    id: raw.id || `email-${index}`,
    sender: raw.sender || raw.from?.split('@')[0] || 'Unknown',
    from: raw.from || raw.sender || '',
    subject: raw.subject || '(no subject)',
    snippet,
    html,
    date: raw.date || '',
    hasAttachment: raw.hasAttachment || false,
    isNewsletter: raw.isNewsletter || false,
    isIntro: raw.isIntro || false,
    predictedAction: raw.predictedAction || null,
    predictionConfidence: raw.predictionConfidence ?? null,
    agentNote: raw.agentNote || '',
    folderIntent: raw.folderIntent || null,
    folderHints: raw.folderHints || [],
    folderJudgments: raw.folderJudgments || raw.aiFolderMatches || [],
    aiSuggestedFolderRouteId: raw.aiSuggestedFolderRouteId || null,
    aiSuggestedFolderConfidence: raw.aiSuggestedFolderConfidence ?? null,
    aiSuggestedFolderReason: raw.aiSuggestedFolderReason || '',
  };
}

async function loadSessionMetadata() {
  try {
    const res = await fetch(`session-metadata.json?t=${Date.now()}`, { cache: 'no-store' });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

function sessionAccountMeta() {
  const meta = state.sessionMeta || {};
  const accountId = meta.accountId || null;
  const accountLabel = meta.accountLabel || accountId;
  return { accountId, accountLabel };
}

function attachAccountFields(entry) {
  const { accountId, accountLabel } = sessionAccountMeta();
  if (accountId) {
    entry.accountId = accountId;
    if (accountLabel) entry.accountLabel = accountLabel;
  }
  return entry;
}

function updateAccountBadge() {
  const badge = document.getElementById('account-badge');
  if (!badge) return;
  const { accountId, accountLabel } = sessionAccountMeta();
  const unified = state.settings.unifiedInbox?.enabled;
  if (accountId && (unified || accountLabel)) {
    badge.textContent = accountLabel || accountId;
    badge.classList.remove('hidden');
  } else {
    badge.textContent = '';
    badge.classList.add('hidden');
  }
}

function isExploreRemoteEnabled() {
  return Boolean(state.settings.access?.exploreRemoteReachability);
}

async function fetchSettingsFromApi() {
  try {
    const res = await fetch('/api/settings', { cache: 'no-store' });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

function mergeSettingsFromApi(apiPayload) {
  if (!apiPayload?.settings) return false;
  saveSettingsToStorage({
    ...state.settings,
    ...apiPayload.settings,
    agent: { ...DEFAULT_SETTINGS.agent, ...(apiPayload.settings.agent || {}) },
    unifiedInbox: { ...DEFAULT_SETTINGS.unifiedInbox, ...(apiPayload.settings.unifiedInbox || {}) },
    access: { ...DEFAULT_SETTINGS.access, ...(apiPayload.settings.access || {}) },
    folders: { ...DEFAULT_SETTINGS.folders, ...(apiPayload.settings.folders || {}) },
    platformRules: { ...DEFAULT_SETTINGS.platformRules, ...(apiPayload.settings.platformRules || {}) },
    rhythm: { ...DEFAULT_SETTINGS.rhythm, ...(apiPayload.settings.rhythm || {}) },
    context: { ...DEFAULT_SETTINGS.context, ...(apiPayload.settings.context || {}) },
  });
  if (apiPayload.accountsStatus) state.accountsStatus = apiPayload.accountsStatus;
  if (apiPayload.intake) state.intakeSnapshot = apiPayload.intake;
  return true;
}

async function refreshServerSettings() {
  const apiPayload = await fetchSettingsFromApi();
  if (!mergeSettingsFromApi(apiPayload)) return;
  updateAccountBadge();
}

function renderRuntimeAccessLines(runtime) {
  const statusEl = document.getElementById('settings-runtime-status');
  const desktopEl = document.getElementById('settings-desktop-url');
  const mobileEl = document.getElementById('settings-mobile-url');
  if (!statusEl) return;

  if (!runtime) {
    statusEl.textContent = 'Server API not reachable — settings save locally until compile.';
    if (desktopEl) desktopEl.textContent = '';
    if (mobileEl) mobileEl.textContent = '';
    return;
  }

  statusEl.textContent = `Session ${runtime.status || 'active'} · port ${runtime.port || '?'}`;
  if (desktopEl) {
    desktopEl.textContent = runtime.desktopUrl ? `Desktop: ${runtime.desktopUrl}` : '';
  }
  if (mobileEl) {
    mobileEl.textContent = runtime.lanUrl ? `Mobile (LAN): ${runtime.lanUrl}` : '';
  }
}

const AUTONOMY_LABELS = {
  recommend: 'Recommend',
  approve_batch: 'Approve batch',
  auto_safe: 'Auto safe',
};

function setAutonomyLevelUI(level) {
  document.querySelectorAll('.autonomy-option').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.level === level);
  });
}

function confirmAutonomyLevel(level) {
  if (level === 'recommend') return true;
  return window.confirm(
    'Higher autonomy lets your agent act on more mail without asking each time. Email Swipe still never auto-deletes. Continue?',
  );
}

function readCheckboxGroup(selector) {
  return [...document.querySelectorAll(selector)]
    .filter((el) => el.checked)
    .map((el) => el.value);
}

function setCheckboxGroup(selector, values) {
  const set = new Set(values || []);
  document.querySelectorAll(selector).forEach((el) => {
    el.checked = set.has(el.value);
  });
}

function parsePreferredTimes(raw) {
  return raw
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean);
}

function formatProvider(provider) {
  if (!provider) return '—';
  return provider.replace(/_/g, ' ');
}

function formatRole(role) {
  if (!role) return '—';
  return role.replace(/_/g, ' ');
}

function renderDefaultAccountSelect() {
  const select = document.getElementById('set-default-account');
  if (!select) return;
  const accounts = state.settings.unifiedInbox?.accounts || [];
  const current = state.settings.unifiedInbox?.defaultAccountId || '';
  select.innerHTML = accounts.length
    ? accounts.map((acct) => `
      <option value="${escapeHtml(acct.id)}"${acct.id === current ? ' selected' : ''}>
        ${escapeHtml(acct.label || acct.id)}
      </option>
    `).join('')
    : '<option value="">—</option>';
}

function renderInboxAccountsTable() {
  const wrap = document.getElementById('inbox-accounts-table');
  if (!wrap) return;
  const statusById = new Map((state.accountsStatus || []).map((row) => [row.id, row]));
  const accounts = state.settings.unifiedInbox?.accounts || [];
  if (!accounts.length) {
    wrap.innerHTML = '<p class="muted">No accounts yet — ask your agent to register mailboxes.</p>';
    return;
  }
  const rows = accounts.map((acct) => {
    const status = statusById.get(acct.id) || {};
    const badgeClass = status.trained ? 'trained' : 'pending';
    const statusLabel = status.statusLabel || (status.trained ? 'Trained' : 'Not trained yet');
    return `
    <tr>
      <td>${escapeHtml(acct.label || acct.id || 'Account')}</td>
      <td>${escapeHtml(formatProvider(acct.provider))}</td>
      <td>${escapeHtml(formatRole(acct.role))}</td>
      <td><span class="account-status-badge ${badgeClass}">${escapeHtml(statusLabel)}</span></td>
    </tr>
  `;
  }).join('');
  wrap.innerHTML = `
    <table>
      <thead><tr><th>Label</th><th>Provider</th><th>Role</th><th>Trained?</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

async function renderInboxesTab() {
  const apiPayload = await fetchSettingsFromApi();
  if (apiPayload?.accountsStatus) state.accountsStatus = apiPayload.accountsStatus;
  renderDefaultAccountSelect();
  renderInboxAccountsTable();
}

function renderContextTab(intake = state.intakeSnapshot) {
  const problemEl = document.getElementById('set-problem-to-solve');
  const notesEl = document.getElementById('set-context-notes');
  const snapshotEl = document.getElementById('context-discovery-snapshot');
  if (!snapshotEl) return;

  const context = state.settings.context || DEFAULT_SETTINGS.context;
  if (problemEl) problemEl.value = context.problemToSolve || '';
  if (notesEl) notesEl.value = context.notes || '';

  if (!intake) {
    snapshotEl.innerHTML = '<p class="settings-note">No intake session yet — your agent captures this during setup.</p>';
    return;
  }

  const discovery = intake.discovery || {};
  const lines = [];
  const phase = intake.phase || 'assess';
  lines.push(`<p><strong>Phase:</strong> ${escapeHtml(phase)}</p>`);
  if (intake.selectedPath || intake.recommendedPath) {
    lines.push(`<p><strong>Path:</strong> ${escapeHtml(intake.selectedPath || intake.recommendedPath)}</p>`);
  }
  if (intake.recommendationReason) {
    lines.push(`<p class="muted">${escapeHtml(intake.recommendationReason)}</p>`);
  }

  const fields = [
    ['Email provider', discovery.emailProvider],
    ['Mail access', discovery.mailAccess],
    ['Training goal', discovery.trainingGoal],
    ['Real vs demo', discovery.realOrDemo],
  ].filter(([, value]) => value);

  if (fields.length) {
    lines.push('<dl>');
    fields.forEach(([label, value]) => {
      lines.push(`<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value))}</dd>`);
    });
    lines.push('</dl>');
  } else {
    lines.push('<p class="settings-note">Discovery not recorded yet.</p>');
  }

  snapshotEl.innerHTML = lines.join('');
}

function toggleAccountShapeSample(show) {
  const pre = document.getElementById('inbox-account-shape');
  if (!pre) return;
  if (show) {
    pre.textContent = JSON.stringify(ACCOUNT_JSON_EXAMPLE, null, 2);
    pre.classList.remove('hidden');
    pre.setAttribute('aria-hidden', 'false');
  } else {
    pre.classList.add('hidden');
    pre.setAttribute('aria-hidden', 'true');
  }
}

async function copyAccountJsonShape() {
  const text = JSON.stringify(ACCOUNT_JSON_EXAMPLE, null, 2);
  toggleAccountShapeSample(true);
  try {
    await navigator.clipboard.writeText(text);
    showStatusBanner('Account JSON shape copied — paste into chat for your agent.', 'success');
  } catch {
    showStatusBanner('Copy the JSON sample below for your agent.', 'info');
  }
}

async function renderTrainingTab() {
  const summaryEl = document.getElementById('training-session-summary');
  const agreementEl = document.getElementById('training-agreement');
  const gapsEl = document.getElementById('training-gaps-list');
  const hintEl = document.getElementById('training-compile-hint');
  if (!summaryEl) return;

  const [status, calibration, graph] = await Promise.all([
    fetchSessionStatus(),
    fetchCalibration(),
    fetchPolicyGraph(),
  ]);

  const completion = status?.lastCompletion;
  if (!completion) {
    summaryEl.innerHTML = '<p class="settings-note">No completed session yet. Finish a swipe session to see scores here.</p>';
    agreementEl?.classList.add('hidden');
    if (gapsEl) gapsEl.innerHTML = '';
    if (hintEl) hintEl.textContent = 'Export from here after training — compile status shows in the banner.';
    return;
  }

  const mode = completion.sessionMode || 'session';
  const intake = completion.intakePath || '—';
  const account = state.sessionMeta?.accountLabel || state.sessionMeta?.accountId || 'default';
  const demo = state.sessionMeta?.sessionMode === 'demo' ? 'Demo mail' : 'Training mail';
  summaryEl.innerHTML = `
    <p><strong>Last session:</strong> ${escapeHtml(String(completion.swipeCount || 0))} swipes · ${escapeHtml(mode)}</p>
    <p><strong>Intake path:</strong> ${escapeHtml(intake)}</p>
    <p><strong>Mailbox:</strong> ${escapeHtml(account)} · ${escapeHtml(demo)}</p>
    <p class="muted">Completed ${escapeHtml((completion.completedAt || '').replace('T', ' ').slice(0, 19))}</p>
  `;

  const agreement = calibration?.overall?.agreement ?? completion.scoreSummary?.agreement;
  if (agreementEl) {
    if (typeof agreement === 'number') {
      agreementEl.textContent = `Agreement: ${Math.round(agreement * 100)}%`;
      agreementEl.classList.remove('hidden');
    } else {
      agreementEl.classList.add('hidden');
    }
  }

  const gaps = graph?.trainingGaps || [];
  if (gapsEl) {
    gapsEl.innerHTML = '';
    gaps.slice(0, 8).forEach((gap) => {
      const li = document.createElement('li');
      li.textContent = gap.reason || gap.summary || gap.sender || JSON.stringify(gap);
      gapsEl.appendChild(li);
    });
  }

  if (hintEl) {
    const runtimeStatus = status?.runtime?.status;
    hintEl.textContent = runtimeStatus === 'compile_failed'
      ? 'Last compile failed — export again or check serve-ui.py logs.'
      : 'Use Export to re-save swipes and compile artifacts.';
  }
}

function populateSettingsForm() {
  document.getElementById('set-agent-name').value = state.settings.agent?.name || '';
  document.getElementById('set-agent-enabled').checked = state.settings.agent?.enabled || false;
  setAutonomyLevelUI(state.settings.agent?.autonomyLevel || 'recommend');

  document.getElementById('set-scan-frequency').value =
    state.settings.agent?.scanFrequency || 'twice_daily';
  const rhythm = state.settings.rhythm || DEFAULT_SETTINGS.rhythm;
  document.getElementById('set-preferred-times').value = (rhythm.preferredTimes || []).join(', ');
  document.getElementById('set-digest-style').value = rhythm.digestStyle || 'short';
  document.getElementById('set-include-score-trend').checked = rhythm.includeScoreTrend !== false;
  setCheckboxGroup('.set-digest-section', rhythm.digestSections || DEFAULT_SETTINGS.rhythm.digestSections);

  const rules = state.settings.platformRules || DEFAULT_SETTINGS.platformRules;
  document.getElementById('set-platform-mode').value = rules.mode || 'suggest_only';
  document.getElementById('set-never-remove-inbox').checked = rules.neverRemoveFromInbox !== false;
  document.getElementById('set-max-rules').value = rules.maxSuggestedRules || 12;
  setCheckboxGroup('.set-allowed-action', rules.allowedActions || []);
  setCheckboxGroup('.set-forbidden-action', rules.forbiddenActions || []);

  const unified = isUnifiedInboxEnabled();
  document.getElementById('set-unified-inbox').checked = unified;
  toggleUnifiedInboxSection(unified);
  renderDefaultAccountSelect();
  renderInboxAccountsTable();

  const context = state.settings.context || DEFAULT_SETTINGS.context;
  document.getElementById('set-problem-to-solve').value = context.problemToSolve || '';
  document.getElementById('set-context-notes').value = context.notes || '';
  renderContextTab(state.intakeSnapshot);

  const exploreRemote = isExploreRemoteEnabled();
  document.getElementById('set-explore-remote').checked = exploreRemote;
  toggleRemoteAccessSection(exploreRemote);

  const advanced = isAdvancedRoutingEnabled();
  document.getElementById('set-advanced-routing').checked = advanced;
  document.getElementById('set-folder-preference').value =
    state.settings.folders?.preference || 'minimal';
  toggleAdvancedRoutingSection(advanced);
  if (advanced) renderFolderRoutesEditor();
}

function collectSettingsFromForm() {
  const autonomyLevel = document.querySelector('.autonomy-option.active')?.dataset.level || 'recommend';
  const advanced = document.getElementById('set-advanced-routing').checked;
  const routes = advanced ? collectFolderRoutesFromEditor() : (state.settings.folders?.routes || []);
  return {
    ...state.settings,
    version: '2.1',
    agent: {
      ...state.settings.agent,
      name: document.getElementById('set-agent-name').value.trim(),
      enabled: document.getElementById('set-agent-enabled').checked,
      scanFrequency: document.getElementById('set-scan-frequency').value,
      autonomyLevel,
    },
    unifiedInbox: {
      ...DEFAULT_SETTINGS.unifiedInbox,
      ...(state.settings.unifiedInbox || {}),
      enabled: document.getElementById('set-unified-inbox').checked,
      defaultAccountId: document.getElementById('set-default-account')?.value || null,
    },
    access: {
      ...DEFAULT_SETTINGS.access,
      ...(state.settings.access || {}),
      exploreRemoteReachability: document.getElementById('set-explore-remote').checked,
    },
    folders: {
      ...state.settings.folders,
      advancedRoutingEnabled: advanced,
      preference: document.getElementById('set-folder-preference').value,
      routes,
    },
    rhythm: {
      ...DEFAULT_SETTINGS.rhythm,
      ...(state.settings.rhythm || {}),
      preferredTimes: parsePreferredTimes(document.getElementById('set-preferred-times').value),
      digestStyle: document.getElementById('set-digest-style').value,
      includeScoreTrend: document.getElementById('set-include-score-trend').checked,
      digestSections: readCheckboxGroup('.set-digest-section'),
    },
    platformRules: {
      ...DEFAULT_SETTINGS.platformRules,
      ...(state.settings.platformRules || {}),
      mode: document.getElementById('set-platform-mode').value,
      neverRemoveFromInbox: document.getElementById('set-never-remove-inbox').checked,
      maxSuggestedRules: Number(document.getElementById('set-max-rules').value) || 12,
      allowedActions: readCheckboxGroup('.set-allowed-action'),
      forbiddenActions: readCheckboxGroup('.set-forbidden-action'),
    },
    context: {
      ...DEFAULT_SETTINGS.context,
      ...(state.settings.context || {}),
      problemToSolve: document.getElementById('set-problem-to-solve')?.value.trim() || '',
      notes: document.getElementById('set-context-notes')?.value.trim() || '',
    },
  };
}

async function switchSettingsTab(tabId) {
  document.querySelectorAll('.settings-tab').forEach((btn) => {
    const active = btn.dataset.tab === tabId;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-selected', active ? 'true' : 'false');
  });
  document.querySelectorAll('.settings-tab-panel').forEach((panel) => {
    const active = panel.id === `settings-tab-${tabId}`;
    panel.classList.toggle('active', active);
    panel.hidden = !active;
  });
  if (tabId === 'training') await renderTrainingTab();
  if (tabId === 'inboxes') await renderInboxesTab();
  if (tabId === 'context') renderContextTab(state.intakeSnapshot);
}

function toggleRemoteAccessSection(show) {
  const section = document.getElementById('remote-access-section');
  if (section) section.classList.toggle('hidden', !show);
}

function isAdvancedRoutingEnabled() {
  return Boolean(state.settings.folders?.advancedRoutingEnabled);
}

function getFolderRoutes() {
  const routes = state.settings.folders?.routes || [];
  return routes.length ? routes : DEFAULT_FOLDER_ROUTES;
}

async function fetchEmailList(url) {
  try {
    const res = await fetch(`${url}?t=${Date.now()}`, { cache: 'no-store' });
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

function extractFeatures(email) {
  const domain = (email.from || '').split('@')[1] || '';
  const text = `${email.subject} ${email.snippet}`.toLowerCase();
  const keywords = [];
  for (const kw of ['unsubscribe', 'receipt', 'newsletter', 'digest', 'promo', 'urgent', 'reminder', 'deadline', 'action required']) {
    if (text.includes(kw)) keywords.push(kw);
  }
  return { hasAttachment: email.hasAttachment || false, isNewsletter: email.isNewsletter || false, senderDomain: domain, keywords };
}

function extractSenderDomain(from) {
  return (from || '').split('@')[1] || '';
}

function normalizeAction(action) {
  if (action === 'needs_attention') return 'important';
  return action;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ─── Smart queue (heuristic active learning) ─────────────────

function predictFromSwipes(email, swipes) {
  const domain = extractSenderDomain(email.from);
  const related = swipes.filter((s) => (s.features?.senderDomain || extractSenderDomain(s.from)) === domain);
  if (related.length < 1) return { confidence: 0.35, uncertain: true, hint: null, topAction: null };

  const counts = {};
  related.forEach((s) => { counts[s.action] = (counts[s.action] || 0) + 1; });
  const total = related.length;
  const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const [topAction, topCount] = sorted[0];
  const confidence = topCount / total;
  const uncertain = confidence < 0.75 || sorted.length > 1;

  let hint = null;
  if (!uncertain && topCount >= 2) {
    const label = (topAction === 'needs_attention' || topAction === 'important') ? 'important' : topAction;
    hint = `Similar to ${topCount} you marked ${label}`;
  } else if (uncertain && related.length >= 2) {
    hint = 'Help me learn this one';
  }
  return { confidence, uncertain, hint, topAction };
}

/** Always return a keep / spam / important guess — never leave blank. */
function heuristicGuess(email) {
  const text = `${email.subject || ''} ${email.snippet || ''} ${email.from || ''}`.toLowerCase();
  if (email.isNewsletter) {
    return { action: 'spam', confidence: 0.55 };
  }
  if (
    /\b(unsubscribe|sale|% off|limited time|newsletter|digest|webinar)\b/i.test(text)
    || /noreply@|no-reply@|marketing@|newsletter@/i.test(email.from || '')
  ) {
    return { action: 'spam', confidence: 0.45 };
  }
  if (
    /\b(invoice|receipt|security alert|password reset|verification code|action required|deadline|urgent)\b/i.test(text)
  ) {
    return { action: 'important', confidence: 0.45 };
  }
  return { action: 'keep', confidence: 0.35 };
}

/**
 * Resolve agent guess for scoring. Prefer agent-injected predictedAction,
 * then in-session sender history, then content heuristics. Always guesses.
 */
function resolveGuess(emailOrSwipe, priorSwipes = []) {
  const injected = normalizeAction(emailOrSwipe.predictedAction);
  if (injected === 'spam' || injected === 'keep' || injected === 'important') {
    return {
      action: injected,
      confidence: emailOrSwipe.predictionConfidence ?? 0.5,
      source: 'agent',
    };
  }

  const email = {
    from: emailOrSwipe.from,
    subject: emailOrSwipe.subject,
    snippet: emailOrSwipe.snippet,
    isNewsletter: emailOrSwipe.isNewsletter,
  };
  const fromSession = predictFromSwipes(email, priorSwipes);
  if (fromSession.topAction) {
    return {
      action: normalizeAction(fromSession.topAction),
      confidence: fromSession.confidence,
      source: 'session',
      hint: fromSession.hint,
      uncertain: fromSession.uncertain,
    };
  }

  const cold = heuristicGuess(emailOrSwipe);
  return { action: cold.action, confidence: cold.confidence, source: 'heuristic' };
}

function scoreEmailForQueue(email, swipes) {
  const mode = state.sessionMeta?.sessionMode;
  if ((mode === 'calibrate' || mode === 'refine') && email.predictionConfidence != null) {
    const conf = email.predictionConfidence;
    let score = 1.0 - conf;
    if (email.agentNote) score += 0.1;
    return { email, score, hint: email.agentNote || (conf < 0.75 ? 'Help me learn this one' : null) };
  }

  const pred = predictFromSwipes(email, swipes);
  let score = pred.uncertain ? 1.0 : 0.2;
  if (pred.confidence >= 0.85) score -= 0.3;
  const text = `${email.subject} ${email.snippet}`.toLowerCase();
  if (text.includes('urgent') || text.includes('action required') || text.includes('deadline')) score += 0.4;
  if (email.isNewsletter) score += 0.15;
  return { email, score, hint: pred.hint };
}

function orderEmailQueue(emails, swipes) {
  const scored = emails.map((e) => scoreEmailForQueue(e, swipes));
  scored.sort((a, b) => b.score - a.score);
  return scored.map((s) => ({ ...s.email, _learningHint: s.hint }));
}

function filterUnswiped(emails, swipes) {
  const seen = new Set(swipes.map((s) => s.emailId));
  return emails.filter((e) => !seen.has(e.id));
}

function analyzeSessionPredictions(swipes) {
  const chronological = [...swipes].sort((a, b) => (a.timestamp || '').localeCompare(b.timestamp || ''));
  return chronological.map((swipe, i) => {
    const prior = chronological.slice(0, i);
    const actual = normalizeAction(swipe.action);
    const guess = resolveGuess(swipe, prior);
    const predicted = guess.action;
    // Every email with a guess is scorable (agent must always guess).
    const scorable = predicted === 'spam' || predicted === 'keep' || predicted === 'important';

    return {
      swipe,
      actual,
      predicted,
      confidence: guess.confidence,
      source: guess.source,
      scorable,
      correct: scorable && predicted === actual,
    };
  });
}

function gatherCorrectionNotesFromDOM() {
  const notes = {};
  document.querySelectorAll('.miss-note').forEach((ta) => {
    if (ta.value.trim()) notes[ta.dataset.emailId] = ta.value.trim();
  });
  return notes;
}

function getAgentName() {
  const name = state.settings.agent?.name?.trim();
  return name || 'Agent';
}

function wouldAgentGuessSpam(email, swipes) {
  const domain = extractSenderDomain(email.from);
  const related = swipes.filter(
    (s) => (s.features?.senderDomain || extractSenderDomain(s.from)) === domain,
  );
  if (related.length === 0) return false;
  const spamCount = related.filter((s) => s.action === 'spam').length;
  if (spamCount === 0) return false;
  if (spamCount === related.length) return true;
  const pred = predictFromSwipes(email, swipes);
  return normalizeAction(pred.topAction) === 'spam' && !pred.uncertain;
}

// ─── Batch confirm ───────────────────────────────────────────

function detectBatchOpportunity() {
  const lastSwipe = state.swipes[state.swipes.length - 1];
  if (!lastSwipe || lastSwipe.action !== 'spam') return null;

  const top = state.emails[0];
  if (!top || top.isIntro) return null;

  const domain = extractSenderDomain(top.from);
  const lastDomain = extractSenderDomain(lastSwipe.from);
  if (!domain || domain !== lastDomain) return null;

  if (!wouldAgentGuessSpam(top, state.swipes)) return null;

  const remaining = state.emails.filter(
    (e) => !e.isIntro && extractSenderDomain(e.from) === domain,
  );
  if (remaining.length < 2) return null;

  return { domain, emails: remaining, action: 'spam' };
}

function showBatchModal(batch) {
  state.pendingBatch = batch;
  const modal = document.getElementById('batch-modal');
  const name = getAgentName();
  document.getElementById('batch-message').textContent =
    `${name} thinks you wouldn't keep ${batch.emails.length} more from ${batch.domain} — mark all?`;
  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden', 'false');
}

function hideBatchModal() {
  state.pendingBatch = null;
  const modal = document.getElementById('batch-modal');
  modal.classList.add('hidden');
  modal.setAttribute('aria-hidden', 'true');
}

async function applyBatchSpam(batch) {
  hideBatchModal();
  for (const email of batch.emails) {
    const idx = state.emails.findIndex((e) => e.id === email.id);
    if (idx === -1) continue;
    state.emails.splice(idx, 1);
    state.swipeCount++;
    const swipe = attachAccountFields({
      emailId: email.id,
      sender: email.sender,
      from: email.from,
      subject: email.subject,
      snippet: email.snippet,
      action: 'spam',
      timestamp: new Date().toISOString(),
      features: extractFeatures(email),
      batch: true,
    });
    const guess = resolveGuess(email, state.swipes);
    swipe.predictedAction = guess.action;
    swipe.predictionConfidence = guess.confidence;
    state.swipes.push(swipe);
    await saveSwipe(swipe);
    schedulePersistSessionProgress();
  }
  updateProgress();
  if (state.emails.length === 0) {
    await finishSession();
  } else {
    renderCards();
  }
}

function maybeOfferBatch(lastAction) {
  if (lastAction !== 'spam') return;
  const batch = detectBatchOpportunity();
  if (batch) showBatchModal(batch);
}

// ─── Export (slim — compile happens in analyze-preferences.py) ─

function buildPreferences(swipes) {
  const analysis = analyzeSessionPredictions(swipes);
  const notes = { ...state.correctionNotes, ...gatherCorrectionNotesFromDOM() };
  const enrichedSwipes = swipes.map((s) => {
    const entry = { ...s };
    if (notes[s.emailId]) entry.correctionNote = notes[s.emailId];
    const row = analysis.find((a) => a.swipe.emailId === s.emailId);
    if (row?.predicted) {
      entry.predictedAction = row.predicted;
      entry.predictionConfidence = row.confidence;
    }
    return entry;
  });

  const misses = analysis
    .filter((a) => a.scorable && !a.correct)
    .map((a) => ({
      emailId: a.swipe.emailId,
      subject: a.swipe.subject,
      sender: a.swipe.sender,
      actual: a.actual,
      predicted: a.predicted,
      correctionNote: notes[a.swipe.emailId] || null,
    }));

  return {
    metadata: {
      generatedAt: new Date().toISOString(),
      totalSwipes: swipes.length,
      version: '2.0',
      sessionMode: state.sessionMeta?.sessionMode || null,
      intakePath: state.sessionMeta?.intakePath || null,
      accountId: state.sessionMeta?.accountId || null,
      accountLabel: state.sessionMeta?.accountLabel || null,
      agentReview: {
        scorablePredictions: analysis.filter((a) => a.scorable).length,
        correctPredictions: analysis.filter((a) => a.scorable && a.correct).length,
        misses,
      },
    },
    settings: state.settings,
    swipes: enrichedSwipes,
  };
}

async function savePreferencesLocal(preferences) {
  try {
    const res = await fetch('/api/preferences', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(preferences, null, 2),
    });
    let data = {};
    try {
      data = await res.json();
    } catch {
      data = {};
    }
    if (!res.ok) {
      return {
        ok: false,
        error: data.error || `Server error (${res.status})`,
        status: res.status,
      };
    }
    return { ok: true, ...data };
  } catch {
    return { ok: false, error: 'Server not reachable', offline: true };
  }
}

async function saveSettingsToBackend(settings) {
  try {
    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ settings }),
    });
    if (!res.ok) {
      let data = {};
      try {
        data = await res.json();
      } catch { /* ignore */ }
      return { ok: false, error: data.error || `Server error (${res.status})` };
    }
    return { ok: true };
  } catch {
    return { ok: false, error: 'Server not reachable', offline: true };
  }
}

async function fetchPolicyGraph() {
  try {
    const res = await fetch('/api/policy-graph', { cache: 'no-store' });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

async function fetchCalibration() {
  try {
    const res = await fetch('/api/calibration', { cache: 'no-store' });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

async function fetchPolicyBrief() {
  try {
    const res = await fetch('/api/policy-brief');
    if (!res.ok) return null;
    return res.text();
  } catch {
    return null;
  }
}

async function fetchSessionStatus() {
  try {
    const res = await fetch('/api/session-status');
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

function renderPolicyBrief(markdown) {
  const el = document.getElementById('victory-policy-brief');
  if (!el || !markdown) return;
  el.textContent = markdown;
  el.classList.remove('hidden');
}

async function exportPreferences(downloadIfNeeded = true) {
  const swipes = state.swipes.length ? state.swipes : await getAllSwipes();
  const preferences = buildPreferences(swipes);
  const saveResult = await savePreferencesLocal(preferences);
  let downloadedOnly = false;

  if (saveResult.ok) {
    showStatusBanner('Saved to your machine and compiled training artifacts.', 'success');
  } else if (downloadIfNeeded) {
    const blob = new Blob([JSON.stringify(preferences, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'preferences.json';
    a.click();
    URL.revokeObjectURL(url);
    downloadedOnly = true;
    if (saveResult.offline) {
      showStatusBanner(
        'Downloaded preferences.json only — server not reachable, so compile did not run. Start serve-ui.py and export again.',
        'error',
      );
    } else {
      showStatusBanner(
        `Downloaded preferences.json only — compile failed: ${saveResult.error || 'unknown error'}.`,
        'error',
      );
    }
  } else if (saveResult.offline) {
    showStatusBanner('Server not reachable — training was not saved or compiled.', 'error');
  } else {
    showStatusBanner(`Compile failed: ${saveResult.error || 'unknown error'}.`, 'error');
  }

  return {
    preferences,
    savedLocally: saveResult.ok,
    compiled: saveResult.ok,
    downloadedOnly,
    compile: saveResult,
  };
}

// ─── Victory screen ──────────────────────────────────────────

const PILE_CARD_W = 100;
const PILE_CARD_H = 68;
const PILE_STACK_STEP = 2;
const PILE_PAD = 4;

function createVictoryMiniCard(swipe) {
  const el = document.createElement('div');
  el.className = 'victory-mini-card';
  el.dataset.emailId = swipe.emailId;
  el.innerHTML = `
    <div class="mini-sender">${escapeHtml(swipe.sender || swipe.from || 'Unknown')}</div>
    <div class="mini-subject">${escapeHtml(swipe.subject || '(no subject)')}</div>
  `;
  return el;
}

function layoutPileCard(card, index) {
  card.classList.add('stacked');
  card.style.position = 'absolute';
  card.style.left = `${PILE_PAD}px`;
  card.style.top = `${PILE_PAD + index * PILE_STACK_STEP}px`;
  card.style.marginLeft = '0';
  card.style.width = `${PILE_CARD_W}px`;
  card.style.height = `${PILE_CARD_H}px`;
  card.style.transform = 'none';
  card.style.transition = 'none';
  card.style.zIndex = String(index);
}

function pileSlotHeight(cardCount) {
  if (cardCount === 0) return 76;
  return PILE_PAD * 2 + PILE_CARD_H + Math.max(0, cardCount - 1) * PILE_STACK_STEP;
}

function finalizeVictoryPiles(analysis) {
  const missesByPile = { spam: 0, important: 0, keep: 0 };
  analysis.filter((a) => a.scorable && !a.correct).forEach((m) => {
    missesByPile[m.actual] = (missesByPile[m.actual] || 0) + 1;
  });

  ['spam', 'important', 'keep'].forEach((pile) => {
    const root = document.querySelector(`.pile-${pile}`);
    const slot = root?.querySelector('.pile-slot');
    const missEl = root?.querySelector('.pile-miss-count');
    const label = root?.querySelector('.pile-label');
    if (!slot || !missEl) return;

    const count = slot.children.length;
    slot.style.height = `${pileSlotHeight(count)}px`;
    if (label) {
      label.textContent = count ? `${ACTION_LABELS[pile]} (${count})` : ACTION_LABELS[pile];
    }

    const misses = missesByPile[pile];
    if (misses > 0) {
      missEl.textContent = `−${misses}`;
      missEl.hidden = false;
    } else {
      missEl.textContent = '';
      missEl.hidden = true;
    }
  });

  const stage = document.getElementById('victory-stage');
  stage.classList.remove('animating');
  stage.classList.add('settled');
  document.getElementById('victory-review-hint')?.classList.remove('hidden');
}

async function playVictoryAnimation(swipes) {
  const deck = document.getElementById('victory-deck');
  const stage = document.getElementById('victory-stage');
  stage.classList.add('animating');
  stage.classList.remove('settled');
  deck.innerHTML = '';
  document.querySelectorAll('.pile-slot').forEach((slot) => {
    slot.innerHTML = '';
    slot.style.height = '';
  });
  document.querySelectorAll('.pile-miss-count').forEach((el) => {
    el.textContent = '';
    el.hidden = true;
  });

  const analysis = analyzeSessionPredictions(swipes);
  const ordered = [...swipes].sort((a, b) => (a.timestamp || '').localeCompare(b.timestamp || ''));
  const pileSlots = {
    spam: document.querySelector('.pile-spam .pile-slot'),
    important: document.querySelector('.pile-important .pile-slot'),
    keep: document.querySelector('.pile-keep .pile-slot'),
  };
  const pileCounts = { spam: 0, important: 0, keep: 0 };

  const n = ordered.length;
  const staggerMs = Math.max(28, Math.min(52, Math.round(480 / n)));
  const flightMs = Math.max(140, Math.min(210, Math.round(1800 / n)));

  await sleep(80);

  const landings = [];

  for (let i = 0; i < n; i++) {
    const swipe = ordered[i];
    const action = normalizeAction(swipe.action);
    const pileSlot = pileSlots[action];
    const idx = pileCounts[action]++;

    const card = createVictoryMiniCard(swipe);
    card.classList.add('victory-flying');
    pileSlot.style.height = `${pileSlotHeight(idx + 1)}px`;
    pileSlot.appendChild(card);
    layoutPileCard(card, idx);

    const deckRect = deck.getBoundingClientRect();
    const cardRect = card.getBoundingClientRect();
    const dx = deckRect.left + deckRect.width / 2 - cardRect.left - cardRect.width / 2;
    const dy = deckRect.top + deckRect.height / 2 - cardRect.top - cardRect.height / 2;
    const wobble = ((i % 5) - 2) * 3;

    card.style.transform = `translate(${dx}px, ${dy}px) rotate(${wobble}deg) scale(1.04)`;
    card.style.transition = 'none';

    requestAnimationFrame(() => {
      card.style.transition = `transform ${flightMs}ms cubic-bezier(0.2, 1.12, 0.32, 1)`;
      card.style.transform = 'translate(0, 0) rotate(0deg) scale(1)';
    });

    landings.push(
      new Promise((resolve) => {
        setTimeout(() => {
          card.classList.remove('victory-flying');
          card.style.transition = 'none';
          card.style.transform = 'none';
          resolve();
        }, flightMs);
      }),
    );

    if (i < n - 1) await sleep(staggerMs);
  }

  await Promise.all(landings);
  deck.innerHTML = '';
  finalizeVictoryPiles(analysis);
}

function renderScoreHistory(status) {
  const wrap = document.getElementById('victory-scorecard');
  const chart = document.getElementById('victory-score-chart');
  if (!wrap || !chart) return;
  chart.innerHTML = '';
  state.pendingScoreBars = null;

  const history = (status?.recentHistory || []).filter(
    (session) => session.agreement != null || session.scorablePredictions > 0,
  );
  if (!history.length) {
    wrap.classList.add('hidden');
    return;
  }

  wrap.classList.remove('hidden');
  const fills = [];
  history.forEach((session, index) => {
    const pct = Math.round((session.agreement || 0) * 100);
    const target = Math.max(pct, 2);
    const bar = document.createElement('div');
    bar.className = 'score-bar';
    bar.innerHTML = `
      <span class="score-bar-pct" data-target="${pct}">0%</span>
      <div class="score-bar-track" title="Session ${index + 1}: ${pct}%">
        <div class="score-bar-fill" style="height:0%" data-target="${target}"></div>
      </div>
      <span class="score-bar-label">Session ${index + 1}</span>
    `;
    chart.appendChild(bar);
    fills.push({
      fill: bar.querySelector('.score-bar-fill'),
      label: bar.querySelector('.score-bar-pct'),
      target,
      pct,
      delay: index * 140,
    });
  });

  // Animate after insights become visible (see playScoreHistoryAnimation).
  state.pendingScoreBars = fills;
}

function playScoreHistoryAnimation() {
  const fills = state.pendingScoreBars;
  if (!fills?.length) return;
  state.pendingScoreBars = null;
  requestAnimationFrame(() => {
    fills.forEach(({ fill, label, target, pct, delay }) => {
      setTimeout(() => {
        fill.style.height = `${target}%`;
        fill.classList.add('shot');
        label.classList.add('shot');
        animateScoreCount(label, pct);
      }, 120 + delay);
    });
  });
}

function animateScoreCount(el, targetPct) {
  const start = performance.now();
  const duration = 520;
  function tick(now) {
    const t = Math.min(1, (now - start) / duration);
    const eased = 1 - (1 - t) ** 3;
    el.textContent = `${Math.round(targetPct * eased)}%`;
    if (t < 1) requestAnimationFrame(tick);
    else el.textContent = `${targetPct}%`;
  }
  requestAnimationFrame(tick);
}

function renderVictoryInsights(swipes, status = null) {
  const analysis = analyzeSessionPredictions(swipes);
  const summaryEl = document.getElementById('victory-summary');
  const missesEl = document.getElementById('victory-misses');
  const name = getAgentName();
  missesEl.innerHTML = '';

  const scorable = analysis.filter((a) => a.scorable);
  const misses = analysis.filter((a) => a.scorable && !a.correct);

  if (scorable.length === 0) {
    summaryEl.textContent = `Swipe to teach ${name} — every email gets a guess.`;
  } else if (misses.length === 0) {
    summaryEl.textContent = `Perfect score, ${name}`;
  } else {
    summaryEl.textContent = `${name} missed on these guesses`;
  }

  renderScoreHistory(status);

  misses.forEach((m) => {
    const card = document.createElement('div');
    card.className = 'miss-card';
    const saved = state.correctionNotes[m.swipe.emailId] || '';
    card.innerHTML = `
      <div class="miss-head">
        <span class="miss-badge">You: ${ACTION_LABELS[m.actual]}</span>
        <span class="miss-badge muted">${escapeHtml(name)} guessed: ${ACTION_LABELS[m.predicted]}</span>
      </div>
      <div class="miss-subject">${escapeHtml(m.swipe.subject || '(no subject)')}</div>
    `;
    const note = document.createElement('textarea');
    note.className = 'miss-note';
    note.dataset.emailId = m.swipe.emailId;
    note.placeholder = "Hey agent — here's why you got this wrong…";
    note.value = saved;
    note.addEventListener('input', () => {
      if (note.value.trim()) state.correctionNotes[note.dataset.emailId] = note.value.trim();
      else delete state.correctionNotes[note.dataset.emailId];
    });
    card.appendChild(note);
    missesEl.appendChild(card);
  });
}

function getSwipesForPile(pileAction) {
  return state.swipes.filter((s) => normalizeAction(s.action) === pileAction);
}

function relayoutVictoryPile(pileAction) {
  const slot = document.querySelector(`.pile-${pileAction} .pile-slot`);
  if (!slot) return;
  const cards = [...slot.querySelectorAll('.victory-mini-card')];
  cards.forEach((card, idx) => layoutPileCard(card, idx));
  slot.style.height = `${pileSlotHeight(cards.length)}px`;
  const label = slot.closest('.victory-pile')?.querySelector('.pile-label');
  if (label) {
    label.textContent = cards.length
      ? `${ACTION_LABELS[pileAction]} (${cards.length})`
      : ACTION_LABELS[pileAction];
  }
}

function moveVictoryCardToPile(emailId, fromAction, toAction) {
  if (fromAction === toAction) return;
  const slotFrom = document.querySelector(`.pile-${fromAction} .pile-slot`);
  const slotTo = document.querySelector(`.pile-${toAction} .pile-slot`);
  const card = slotFrom?.querySelector(`[data-email-id="${emailId}"]`);
  if (!card || !slotTo) return;
  card.remove();
  const idx = slotTo.children.length;
  slotTo.appendChild(card);
  layoutPileCard(card, idx);
  relayoutVictoryPile(fromAction);
  relayoutVictoryPile(toAction);
  finalizeVictoryPiles(analyzeSessionPredictions(state.swipes));
}

function openPileReviewPanel(pileAction) {
  state.victoryReview.pile = pileAction;
  const panel = document.getElementById('pile-review-panel');
  const list = document.getElementById('pile-review-list');
  const title = document.getElementById('pile-review-title');
  const swipes = getSwipesForPile(pileAction);

  title.textContent = `${ACTION_LABELS[pileAction]} (${swipes.length})`;
  list.innerHTML = '';

  if (swipes.length === 0) {
    list.innerHTML = '<p class="review-list-meta">No emails in this pile.</p>';
  } else {
    swipes.forEach((swipe) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'review-list-item';
      const note = state.correctionNotes[swipe.emailId] || swipe.correctionNote;
      btn.innerHTML = `
        <span class="review-list-subject">${escapeHtml(swipe.subject || '(no subject)')}</span>
        <span class="review-list-meta">${escapeHtml(swipe.sender || swipe.from || 'Unknown')}${note ? ' · has note' : ''}</span>
      `;
      btn.addEventListener('click', () => openEmailReviewPanel(swipe.emailId, pileAction));
      list.appendChild(btn);
    });
  }

  panel.classList.remove('hidden');
  panel.setAttribute('aria-hidden', 'false');
}

function hidePileReviewPanel() {
  document.getElementById('pile-review-panel').classList.add('hidden');
  document.getElementById('pile-review-panel').setAttribute('aria-hidden', 'true');
}

function closePileReviewPanel() {
  hidePileReviewPanel();
  state.victoryReview.pile = null;
}

function openEmailReviewPanel(emailId, fromPile = null) {
  const swipe = state.swipes.find((s) => s.emailId === emailId);
  if (!swipe) return;

  state.victoryReview.emailId = emailId;
  if (fromPile) state.victoryReview.pile = fromPile;
  hidePileReviewPanel();

  document.getElementById('email-review-sender').textContent = swipe.sender || swipe.from || 'Unknown';
  document.getElementById('email-review-subject').textContent = swipe.subject || '(no subject)';
  document.getElementById('email-review-snippet').textContent = swipe.snippet || '';
  document.getElementById('email-review-note').value =
    state.correctionNotes[emailId] || swipe.correctionNote || '';

  const action = normalizeAction(swipe.action);
  document.querySelectorAll('#email-review-actions .review-action-btn').forEach((btn) => {
    btn.classList.toggle('selected', btn.dataset.action === action);
    btn.onclick = () => {
      document.querySelectorAll('#email-review-actions .review-action-btn').forEach((b) => {
        b.classList.remove('selected');
      });
      btn.classList.add('selected');
    };
  });

  document.getElementById('email-review-back').style.visibility =
    state.victoryReview.pile ? 'visible' : 'hidden';

  const panel = document.getElementById('email-review-panel');
  panel.classList.remove('hidden');
  panel.setAttribute('aria-hidden', 'false');
}

function closeEmailReviewPanel() {
  document.getElementById('email-review-panel').classList.add('hidden');
  document.getElementById('email-review-panel').setAttribute('aria-hidden', 'true');
  state.victoryReview.emailId = null;
}

function saveEmailReview() {
  const emailId = state.victoryReview.emailId;
  if (!emailId) return;

  const swipe = state.swipes.find((s) => s.emailId === emailId);
  if (!swipe) return;

  const selected = document.querySelector('#email-review-actions .review-action-btn.selected');
  const newAction = selected?.dataset.action || normalizeAction(swipe.action);
  const note = document.getElementById('email-review-note').value.trim();
  const oldAction = normalizeAction(swipe.action);
  const returnPile = state.victoryReview.pile;

  swipe.action = newAction;
  if (note) {
    swipe.correctionNote = note;
    state.correctionNotes[emailId] = note;
  } else {
    delete swipe.correctionNote;
    delete state.correctionNotes[emailId];
  }
  if (newAction !== oldAction) {
    swipe.reviewEdited = true;
    moveVictoryCardToPile(emailId, oldAction, newAction);
  } else {
    finalizeVictoryPiles(analyzeSessionPredictions(state.swipes));
  }
  renderVictoryInsights(state.swipes, state.sessionStatus);
  playScoreHistoryAnimation();

  closeEmailReviewPanel();
  if (returnPile) openPileReviewPanel(returnPile);
}

function initVictoryReview() {
  document.getElementById('victory-stage')?.addEventListener('click', (e) => {
    if (!document.getElementById('victory-stage').classList.contains('settled')) return;

    const card = e.target.closest('.victory-mini-card');
    if (card?.dataset.emailId) {
      openEmailReviewPanel(card.dataset.emailId);
      return;
    }

    const pile = e.target.closest('.victory-pile');
    if (pile) {
      const pileAction = pile.querySelector('.pile-slot')?.dataset.pile;
      if (pileAction) openPileReviewPanel(pileAction);
    }
  });

  document.getElementById('pile-review-close')?.addEventListener('click', closePileReviewPanel);
  document.getElementById('pile-review-backdrop')?.addEventListener('click', closePileReviewPanel);
  document.getElementById('email-review-close')?.addEventListener('click', closeEmailReviewPanel);
  document.getElementById('email-review-backdrop')?.addEventListener('click', closeEmailReviewPanel);
  document.getElementById('email-review-back')?.addEventListener('click', () => {
    const pile = state.victoryReview.pile;
    closeEmailReviewPanel();
    if (pile) openPileReviewPanel(pile);
  });
  document.getElementById('email-review-save')?.addEventListener('click', saveEmailReview);
}

async function showVictoryScreen(swipes, compileResult = {}) {
  const victory = document.getElementById('victory-screen');
  const insights = document.getElementById('victory-insights');
  insights.classList.add('hidden');
  document.getElementById('victory-policy-brief')?.classList.add('hidden');
  victory.classList.remove('hidden');
  victory.setAttribute('aria-hidden', 'false');
  document.body.classList.add('victory-active');
  document.body.classList.remove('swiping');

  const kicker = document.getElementById('victory-kicker');
  if (compileResult.ok) {
    kicker.textContent = compileResult.briefHeadline || `${swipes.length} emails sorted`;
  } else if (compileResult.offline) {
    kicker.textContent = 'Session done — not saved';
  } else {
    kicker.textContent = 'Session done — compile failed';
  }

  renderVictoryCompileStatus(compileResult);

  if (compileResult.preview) {
    // Land piles instantly so the score bars are the focus.
    document.querySelectorAll('.pile-slot').forEach((slot) => {
      slot.innerHTML = '';
      slot.style.height = '';
    });
    const analysis = analyzeSessionPredictions(swipes);
    const pileCounts = { spam: 0, important: 0, keep: 0 };
    swipes.forEach((swipe) => {
      const action = normalizeAction(swipe.action);
      const pileSlot = document.querySelector(`.pile-${action} .pile-slot`);
      if (!pileSlot) return;
      const idx = pileCounts[action]++;
      const card = createVictoryMiniCard(swipe);
      pileSlot.style.height = `${pileSlotHeight(idx + 1)}px`;
      pileSlot.appendChild(card);
      layoutPileCard(card, idx);
    });
    finalizeVictoryPiles(analysis);
  } else {
    await playVictoryAnimation(swipes);
  }

  const sessionStatus = compileResult.sessionStatus || await fetchSessionStatus();
  state.sessionStatus = sessionStatus;
  renderVictoryInsights(swipes, sessionStatus);
  if (compileResult.ok && !compileResult.preview) {
    const brief = await fetchPolicyBrief();
    if (brief) renderPolicyBrief(brief);
  }
  insights.classList.remove('hidden');
  playScoreHistoryAnimation();
}

function buildVictoryPreviewSwipes() {
  const samples = [
    { id: 'prev-1', sender: 'GitHub', subject: 'New pull request #42', action: 'important', predictedAction: 'keep' },
    { id: 'prev-2', sender: 'LinkedIn', subject: '5 new connection requests', action: 'spam', predictedAction: 'spam' },
    { id: 'prev-3', sender: 'Amazon', subject: 'Your package has been delivered', action: 'keep', predictedAction: 'keep' },
    { id: 'prev-4', sender: 'Substack', subject: 'Weekly digest: 12 new posts', action: 'spam', predictedAction: 'keep' },
    { id: 'prev-5', sender: 'Stripe', subject: 'Payout of $1,240.00 is on the way', action: 'important', predictedAction: 'important' },
    { id: 'prev-6', sender: 'Notion', subject: 'Comments on Product roadmap', action: 'keep', predictedAction: 'important' },
    { id: 'prev-7', sender: 'Chase', subject: 'Your statement is ready', action: 'keep', predictedAction: 'keep' },
    { id: 'prev-8', sender: 'Figma', subject: 'Shared file: Onboarding flow', action: 'important', predictedAction: 'keep' },
    { id: 'prev-9', sender: 'Uber', subject: 'Your Friday trip receipt', action: 'spam', predictedAction: 'spam' },
    { id: 'prev-10', sender: 'Calendar', subject: 'Reminder: Design review at 2pm', action: 'important', predictedAction: 'important' },
    { id: 'prev-11', sender: 'Newsletter', subject: '10 tools that replaced my stack', action: 'spam', predictedAction: 'keep' },
    { id: 'prev-12', sender: 'HR', subject: 'Benefits enrollment closes Friday', action: 'important', predictedAction: 'keep' },
  ];
  const now = Date.now();
  return samples.map((s, i) => ({
    emailId: s.id,
    sender: s.sender,
    from: `${s.sender.toLowerCase().replace(/\s+/g, '')}@example.com`,
    subject: s.subject,
    action: s.action,
    predictedAction: s.predictedAction,
    timestamp: new Date(now - (samples.length - i) * 60000).toISOString(),
  }));
}

function buildVictoryPreviewStatus() {
  // Six prior sessions so the staggered shoot-up animation is easy to judge.
  const scores = [0.38, 0.47, 0.55, 0.64, 0.72, 0.81];
  return {
    status: 'completed',
    scoreTrend: { status: 'improving', latestAgreement: 0.81, previousAgreement: 0.72 },
    recentHistory: scores.map((agreement, i) => ({
      sessionId: `preview-session-${i + 1}`,
      agreement,
      scorablePredictions: 12,
      correctPredictions: Math.round(agreement * 12),
      swipeCount: 12,
    })),
  };
}

async function bootVictoryPreview() {
  document.querySelector('.simple-actions')?.classList.add('hidden');
  document.getElementById('folder-actions')?.classList.add('hidden');
  document.getElementById('folder-actions-hint')?.classList.add('hidden');
  document.getElementById('card-stack').style.display = 'none';
  document.getElementById('empty-state')?.classList.add('hidden');

  const swipes = buildVictoryPreviewSwipes();
  state.swipes = swipes;
  state.swipeCount = swipes.length;
  state.correctionNotes = {};

  await showVictoryScreen(swipes, {
    ok: true,
    preview: true,
    briefHeadline: '12 emails sorted · preview',
    sessionStatus: buildVictoryPreviewStatus(),
  });
}

function hideVictoryScreen() {
  const victory = document.getElementById('victory-screen');
  victory.classList.add('hidden');
  victory.setAttribute('aria-hidden', 'true');
  document.body.classList.remove('victory-active');
  const stage = document.getElementById('victory-stage');
  stage?.classList.remove('settled', 'animating');
  document.getElementById('victory-deck').innerHTML = '';
  document.getElementById('victory-review-hint')?.classList.add('hidden');
  closePileReviewPanel();
  closeEmailReviewPanel();
  document.querySelectorAll('.pile-slot').forEach((slot) => {
    slot.innerHTML = '';
    slot.style.height = '';
  });
  document.querySelectorAll('.pile-miss-count').forEach((el) => {
    el.textContent = '';
    el.hidden = true;
  });
  document.getElementById('victory-insights').classList.add('hidden');
  document.getElementById('victory-compile-status')?.classList.add('hidden');
  document.getElementById('victory-misses').innerHTML = '';
  document.getElementById('victory-scorecard')?.classList.add('hidden');
  document.getElementById('victory-score-chart')?.replaceChildren();
  state.pendingScoreBars = null;
  document.querySelector('.simple-actions')?.classList.remove('hidden');
  document.getElementById('card-stack').style.display = '';
  state.correctionNotes = {};
  updateActionMode();
}

// ─── Session lifecycle ───────────────────────────────────────

async function finishSession() {
  const swipes = state.swipes.length ? [...state.swipes] : await getAllSwipes();
  document.getElementById('card-stack').innerHTML = '';
  document.getElementById('card-stack').style.display = 'none';
  document.getElementById('empty-state').classList.add('hidden');
  document.querySelector('.simple-actions')?.classList.add('hidden');
  document.getElementById('folder-actions')?.classList.add('hidden');
  document.getElementById('folder-actions-hint')?.classList.add('hidden');

  await persistSessionProgress({ completed: true });
  const { compile } = await exportPreferences(false);
  await showVictoryScreen(swipes, compile || {});
}

async function startSession(emails, { resume = false } = {}) {
  hideVictoryScreen();
  const normalized = emails.map(normalizeEmail);
  state.allEmails = normalized;
  state.inboxFingerprint = inboxFingerprint(normalized);

  if (!resume) {
    try {
      state.swipes = await getAllSwipes();
      state.swipeCount = state.swipes.length;
    } catch {
      state.swipes = [];
      state.swipeCount = 0;
    }
  } else {
    state.swipeCount = state.swipes.length;
  }

  const unswiped = filterUnswiped(normalized, state.swipes);
  const ordered = orderEmailQueue(unswiped, state.swipes);
  state.trainingTotal = normalized.length;

  // Skip intro when picking up mid-batch so it doesn't feel like a restart.
  state.emails = state.swipeCount > 0 ? ordered : [INTRO_CARD, ...ordered];
  updateProgress();

  if (ordered.length === 0 && state.swipeCount > 0) {
    await finishSession();
    return;
  }

  renderCards();
  if (state.swipeCount > 0) {
    showStatusBanner(
      `Resumed — ${state.swipeCount} of ${state.trainingTotal} already done`,
      'ok',
    );
  }
  schedulePersistSessionProgress({ completed: false });
}

async function trainAgain() {
  hideVictoryScreen();
  await clearSwipes();
  await persistSessionProgress({ clear: true });
  state.swipes = [];
  state.swipeCount = 0;
  state.correctionNotes = {};
  const emails = state.allEmails.length ? state.allEmails : await loadFromFile();
  if (emails.length) await startSession(emails);
  else renderCards();
}

// ─── Card UI ─────────────────────────────────────────────────

function updateProgress() {
  const goal = state.trainingTotal || 1;
  document.getElementById('progress-count').textContent = `${state.swipeCount} / ${goal}`;
  document.getElementById('progress-fill').style.width = `${Math.min(100, (state.swipeCount / goal) * 100)}%`;
}

function renderCards() {
  const stack = document.getElementById('card-stack');
  const empty = document.getElementById('empty-state');
  stack.innerHTML = '';

  const trainable = state.emails.filter((e) => !e.isIntro);
  if (trainable.length === 0 && state.trainingTotal > 0 && state.swipeCount > 0) {
    stack.style.display = 'none';
    return;
  }

  if (state.emails.length === 0) {
    empty.classList.remove('hidden');
    stack.style.display = 'none';
    const title = empty.querySelector('.empty-title');
    const hint = empty.querySelector('.empty-hint');
    const btn = document.getElementById('btn-train-again');
    if (state.trainingTotal > 0) {
      if (title) title.textContent = 'Session complete';
      if (hint) hint.style.display = '';
      if (btn) btn.style.display = '';
    } else {
      if (title) title.textContent = 'Waiting for emails';
      if (hint) hint.textContent = 'Your agent will load your inbox, then refresh this page.';
      if (btn) btn.style.display = 'none';
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
  updateActionMode();
}

function createCard(email, isBehind) {
  const card = document.createElement('div');
  card.className = `email-card${isBehind ? ' behind' : ' front'}${email.isIntro ? ' intro' : ' drag-header'}`;
  card.dataset.emailId = email.id;

  if (email.isIntro) {
    card.innerHTML = `
      <div class="swipe-overlay spam">Don't Keep</div>
      <div class="swipe-overlay keep">KEEP</div>
      <div class="swipe-overlay important">IMPORTANT</div>
      <div class="intro-subject">${escapeHtml(email.subject)}</div>
      <div class="intro-snippet">${escapeHtml(email.snippet)}</div>
    `;
    return card;
  }

  const badges = [];
  if (email.hasAttachment) badges.push('<span class="badge attachment">Attachment</span>');
  if (email.isNewsletter) badges.push('<span class="badge newsletter">Newsletter</span>');

  const hint = !isBehind && email._learningHint
    ? `<div class="learning-hint">${escapeHtml(email._learningHint)}</div>`
    : '';

  const useHtml = !isBehind && email.html;
  const bodyMarkup = useHtml
    ? '<iframe class="email-html" sandbox="" title="Email body"></iframe>'
    : `<div class="card-snippet">${escapeHtml(email.snippet)}</div>`;

  card.innerHTML = `
    <div class="swipe-overlay spam">Don't Keep</div>
    <div class="swipe-overlay keep">KEEP</div>
    <div class="swipe-overlay important">IMPORTANT</div>
    <div class="card-header">
      <div class="card-sender">${escapeHtml(email.sender)}</div>
      ${hint}
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
  const bodyHtml = unwrapEmailHtml(html);
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 14px; line-height: 1.5; margin: 0; padding: 0; color: #101828; word-wrap: break-word; }
    img { max-width: 100%; height: auto; }
    a { color: #344054; pointer-events: none; }
  </style></head><body>${bodyHtml}</body></html>`;
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
  let lastTapTime = 0;

  const setOffset = (x) => {
    currentX = x;
    const rot = x * 0.04;
    card.style.transform = `translate3d(${x}px, 0, 0) rotate(${rot}deg)`;
    card.classList.toggle('show-spam', x < -40);
    card.classList.toggle('show-keep', x > 40);
  };

  const reset = () => {
    card.style.transform = '';
    card.classList.remove('show-spam', 'show-keep', 'show-important', 'tap-pending', 'dragging');
    document.body.classList.remove('swiping');
    dragging = false;
    pointerId = null;
    currentX = 0;
    startX = 0;
  };

  const onEnd = (e) => {
    if (!dragging) return;
    card.releasePointerCapture?.(pointerId);
    dragging = false;
    document.body.classList.remove('swiping');
    card.classList.remove('dragging');

    let action = null;
    if (currentX < -SWIPE_THRESHOLD) {
      action = 'spam';
    } else if (currentX > SWIPE_THRESHOLD) {
      action = 'keep';
    }

    if (action) {
      lastTapTime = 0;
      swipeCard(card, email, action);
      return;
    }

    const moved = Math.abs(currentX);
    if (moved < TAP_MOVE_TOLERANCE) {
      const now = Date.now();
      if (now - lastTapTime < DOUBLE_TAP_MS) {
        lastTapTime = 0;
        card.classList.remove('tap-pending');
        swipeCard(card, email, 'important');
        return;
      }
      lastTapTime = now;
      card.classList.add('tap-pending');
      card.style.transform = '';
      card.classList.remove('show-spam', 'show-keep', 'dragging');
      document.body.classList.remove('swiping');
      dragging = false;
      pointerId = null;
      currentX = 0;
      startX = 0;
      setTimeout(() => card.classList.remove('tap-pending'), DOUBLE_TAP_MS);
      return;
    }

    reset();
  };

  card.addEventListener('pointerdown', (e) => {
    if (card.style.pointerEvents === 'none') return;
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    if (!email.isIntro && !e.target.closest('.card-header')) return;

    dragging = true;
    pointerId = e.pointerId;
    startX = e.clientX;
    card.classList.remove('tap-pending');
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

  const hintEl = behind.querySelector('.learning-hint');
  if (hintEl && email._learningHint) hintEl.textContent = email._learningHint;
  else if (email._learningHint) {
    const header = behind.querySelector('.card-header');
    const el = document.createElement('div');
    el.className = 'learning-hint';
    el.textContent = email._learningHint;
    header.insertBefore(el, header.querySelector('.card-from'));
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

async function swipeCard(card, email, action, extra = {}) {
  if (state.isAnimating) return;
  state.isAnimating = true;

  const stack = document.getElementById('card-stack');

  card.classList.remove('dragging', 'show-spam', 'show-keep', 'show-important', 'tap-pending');
  card.style.pointerEvents = 'none';
  card.style.zIndex = '3';
  card.style.transition = 'transform 0.26s ease-out, opacity 0.26s ease-out';

  let offX = 0;
  let rotation = 0;
  if (action === 'spam') { offX = -window.innerWidth * 0.85; rotation = -16; }
  else if (action === 'keep') { offX = window.innerWidth * 0.85; rotation = 16; }
  else if (action === 'important') {
    card.classList.add('show-important', 'exiting-important');
  }

  requestAnimationFrame(() => {
    if (action === 'important') {
      card.style.transform = 'scale(1.06)';
    } else {
      card.style.transform = `translate3d(${offX}px, 0, 0) rotate(${rotation}deg)`;
    }
    card.style.opacity = '0';
  });

  if (!email.isIntro) {
    state.swipeCount++;
    updateProgress();
    const swipe = attachAccountFields({
      emailId: email.id,
      sender: email.sender,
      from: email.from,
      subject: email.subject,
      snippet: email.snippet,
      action,
      timestamp: new Date().toISOString(),
      features: extractFeatures(email),
    });
    if (extra.folderRoute) swipe.folderRoute = extra.folderRoute;
    // Always attach a guess for scoring — prefer agent-injected, else session/heuristic.
    const guess = resolveGuess(email, state.swipes);
    swipe.predictedAction = guess.action;
    swipe.predictionConfidence = guess.confidence;
    if (email.agentNote) swipe.agentNote = email.agentNote;
    state.swipes.push(swipe);
    await saveSwipe(swipe);
    schedulePersistSessionProgress();
  }

  state.emails.shift();

  const trainableLeft = state.emails.filter((e) => !e.isIntro).length;
  if (trainableLeft === 0 && state.swipeCount > 0) {
    setTimeout(async () => {
      card.remove();
      await finishSession();
      state.isAnimating = false;
    }, 260);
    return;
  }

  const hadBehind = !!stack.querySelector('.email-card.behind');
  if (hadBehind) {
    promoteBehindCard(stack);
    replaceBehindCard(stack);
    updateActionMode();
  } else {
    renderCards();
  }

  setTimeout(() => {
    card.remove();
    state.isAnimating = false;
    if (action === 'spam') maybeOfferBatch(action);
  }, 260);
}

function triggerAction(action) {
  const card = document.querySelector('#card-stack .email-card.front');
  if (!card || card.style.pointerEvents === 'none' || state.emails.length === 0) return;
  const email = state.emails[0];
  if (action === 'spam' && isAdvancedRoutingEnabled() && !email.isIntro) {
    showFolderPicker(email, card);
    return;
  }
  swipeCard(card, email, action);
}

// ─── Folder routing (advanced) ───────────────────────────────

function folderRoutePayload(route, matchMeta = {}) {
  if (!route) return null;
  const mode = routeMatchMode(route);
  return {
    routeId: route.id,
    folderName: route.name,
    matchType: route.matchType,
    matchMode: mode,
    matchValue: route.matchValue || null,
    intent: route.matchType === 'intent' ? route.matchValue : null,
    aiRule: route.aiRule || route.description || null,
    description: route.description || route.aiRule || null,
    matchScore: matchMeta.score ?? null,
    matchReason: matchMeta.reason || null,
    judgmentSource: matchMeta.judgmentSource || null,
    userSelected: true,
    suggestOnly: true,
  };
}

function showFolderPicker(email, card) {
  state.pendingSwipe = { email, card };
  const modal = document.getElementById('folder-picker-modal');
  const subject = document.getElementById('folder-picker-subject');
  const options = document.getElementById('folder-picker-options');
  subject.textContent = email.subject || '(no subject)';
  options.innerHTML = '';

  const suggestion = suggestRouteForEmail(email);
  const suggested = suggestion?.route;
  const routes = getFolderRoutes();
  const lastId = state.settings.folders?.lastFolderId;

  const scored = routes.map((route) => {
    const result = scoreRouteForEmail(email, route);
    return { route, ...result };
  }).sort((a, b) => b.score - a.score);

  scored.forEach(({ route, score, reason, judgmentSource }) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'folder-picker-btn';
    const isSuggested = suggested && route.id === suggested.id;
    if (isSuggested) btn.classList.add('suggested');
    const mode = routeMatchMode(route);
    const modeLabel = { ai: 'AI rule', smart: 'smart', strict: 'strict' }[mode] || mode;
    let label = `${route.name} (${modeLabel})`;
    if (score >= INTENT_MATCH_THRESHOLD && reason) {
      const src = judgmentSource === 'agent' ? 'agent' : judgmentSource === 'strict' ? 'strict' : 'likely';
      label += ` · ${reason} (${Math.round(score * 100)}% ${src})`;
    } else if (route.matchType === 'descriptor' && route.aiRule) {
      label += ` · ${route.aiRule.slice(0, 50)}${route.aiRule.length > 50 ? '…' : ''}`;
    } else if (route.matchType === 'intent' && FOLDER_INTENTS[route.matchValue]) {
      label += ` · ${FOLDER_INTENTS[route.matchValue].label}`;
    }
    if (isSuggested) label += ' · top pick';
    btn.textContent = label;
    btn.addEventListener('click', () => completeFolderPicker(route, { score, reason, judgmentSource }));
    options.appendChild(btn);
  });

  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden', 'false');
}

function hideFolderPicker() {
  document.getElementById('folder-picker-modal').classList.add('hidden');
  document.getElementById('folder-picker-modal').setAttribute('aria-hidden', 'true');
  state.pendingSwipe = null;
}

function completeFolderPicker(route, matchMeta = {}) {
  const pending = state.pendingSwipe;
  if (!pending) return;
  hideFolderPicker();
  if (route && state.settings.folders?.rememberLastFolder !== false) {
    state.settings.folders.lastFolderId = route.id;
    saveSettingsToStorage(state.settings);
  }
  swipeCard(pending.card, pending.email, 'spam', { folderRoute: folderRoutePayload(route, matchMeta) });
}

function initFolderPicker() {
  document.getElementById('folder-picker-skip')?.addEventListener('click', () => completeFolderPicker(null));
  document.getElementById('folder-picker-backdrop')?.addEventListener('click', hideFolderPicker);
}

// ─── Folder-mode action bar (replaces swipe buttons when advanced) ─

function foldersForActionBar() {
  return getFolderRoutes().map((route) => {
    if (route.action) {
      const cls = route.action === 'keep' ? 'keep' : route.action === 'important' ? 'important' : 'folder';
      return { kind: 'action', action: route.action, name: route.name, cls, route };
    }
    return { kind: 'folder', route, name: route.name, cls: 'folder' };
  });
}

function renderFolderActions() {
  const bar = document.getElementById('folder-actions');
  if (!bar) return;
  bar.innerHTML = '';

  const items = foldersForActionBar();
  const cols = Math.min(5, Math.max(1, items.length));
  bar.style.gridTemplateColumns = `repeat(${cols}, minmax(0, 1fr))`;

  const top = state.emails[0];
  const email = top && !top.isIntro ? top : null;
  const suggestion = email ? suggestRouteForEmail(email) : null;

  items.forEach((item) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `folder-action-btn ${item.cls}`;

    let modeLabel = '';
    if (item.kind === 'folder') {
      const mode = routeMatchMode(item.route);
      modeLabel = { ai: 'AI rule', smart: 'smart', strict: 'strict' }[mode] || '';
      if (suggestion && suggestion.route.id === item.route.id) {
        btn.classList.add('suggested');
        modeLabel = `${Math.round(suggestion.score * 100)}% · ${modeLabel}`;
      }
    }

    btn.innerHTML =
      `<span class="folder-action-name">${escapeHtml(item.name)}</span>` +
      (modeLabel ? `<span class="folder-action-mode">${escapeHtml(modeLabel)}</span>` : '');
    btn.addEventListener('click', () => applyFolderChoice(item));
    bar.appendChild(btn);
  });
}

function applyFolderChoice(item) {
  const card = document.querySelector('#card-stack .email-card.front');
  if (!card || card.style.pointerEvents === 'none' || state.emails.length === 0) return;
  const email = state.emails[0];
  if (email.isIntro) {
    swipeCard(card, email, 'keep');
    return;
  }
  if (item.kind === 'action') {
    swipeCard(card, email, item.action);
    return;
  }
  const meta = scoreRouteForEmail(email, item.route);
  if (state.settings.folders?.rememberLastFolder !== false) {
    state.settings.folders.lastFolderId = item.route.id;
    saveSettingsToStorage(state.settings);
  }
  swipeCard(card, email, 'spam', { folderRoute: folderRoutePayload(item.route, meta) });
}

function updateActionMode() {
  const folderMode = isAdvancedRoutingEnabled();
  const simple = document.querySelector('.simple-actions');
  const folderBar = document.getElementById('folder-actions');
  const hints = document.querySelector('.action-hints');
  const folderHint = document.getElementById('folder-actions-hint');

  if (folderMode) {
    simple?.classList.add('hidden');
    hints?.classList.add('hidden');
    folderBar?.classList.remove('hidden');
    folderHint?.classList.remove('hidden');
    renderFolderActions();
  } else {
    simple?.classList.remove('hidden');
    hints?.classList.remove('hidden');
    folderBar?.classList.add('hidden');
    folderHint?.classList.add('hidden');
  }
}

function buildRouteMatchValueControl(route) {
  if (route.matchType === 'descriptor') {
    return '<span class="route-match-na">Describe below</span>';
  }
  if (route.action) {
    const label = ACTION_LABELS[route.action] || route.action;
    return `<span class="route-match-na">${escapeHtml(label)} action</span>`;
  }
  if (route.matchType === 'intent') {
    const options = Object.entries(FOLDER_INTENTS).map(([id, spec]) =>
      `<option value="${id}" ${route.matchValue === id ? 'selected' : ''}>${escapeHtml(spec.label)}</option>`
    ).join('');
    return `<select class="route-match-value">${options}</select>`;
  }
  return `<input type="text" class="route-match-value" value="${escapeHtml(route.matchValue || '')}" placeholder="Exact match value">`;
}

function buildRouteRuleField(route) {
  if (route.action) {
    return '<p class="route-action-note">Trains this as an inbox action — no folder match needed.</p>';
  }
  if (route.matchType === 'descriptor') {
    const val = route.aiRule || route.description || '';
    return `<textarea class="route-ai-rule" rows="2" placeholder="Describe what belongs here — your agent judges at runtime. E.g. All retail promotions and flash sales, even without the word sale.">${escapeHtml(val)}</textarea>`;
  }
  return `<input type="text" class="route-description" value="${escapeHtml(route.description || '')}" placeholder="Optional note for your agent">`;
}

function renderFolderRoutesEditor() {
  const list = document.getElementById('folder-routes-list');
  if (!list) return;
  list.innerHTML = '';
  const routes = getFolderRoutes().map((route) => ({ ...route }));
  routes.forEach((route, index) => {
    const row = document.createElement('div');
    row.className = 'folder-route-row-wrap';
    const kind = routeKind(route);
    const sel = (v) => (kind === v ? 'selected' : '');

    row.innerHTML = `
      <div class="folder-route-row">
        <input type="text" class="route-name" value="${escapeHtml(route.name)}" placeholder="Folder name">
        <select class="route-match-type">
          <optgroup label="Inbox actions">
            <option value="keep" ${sel('keep')}>Keep in inbox</option>
            <option value="important" ${sel('important')}>Flag important</option>
            <option value="spam" ${sel('spam')}>Don't keep</option>
          </optgroup>
          <optgroup label="AI &amp; judgment">
            <option value="descriptor" ${sel('descriptor')}>AI rule (plain English)</option>
            <option value="intent" ${sel('intent')}>Smart category</option>
          </optgroup>
          <optgroup label="Strict">
            <option value="keyword" ${sel('keyword')}>Keyword (exact)</option>
            <option value="domain" ${sel('domain')}>Domain (exact)</option>
            <option value="sender" ${sel('sender')}>Sender (exact)</option>
          </optgroup>
        </select>
        <span class="route-match-cell">${buildRouteMatchValueControl(route)}</span>
        <button type="button" class="btn-close route-remove" title="Remove">×</button>
      </div>
      <div class="route-rule-field">${buildRouteRuleField(route)}</div>
    `;
    const matchTypeEl = row.querySelector('.route-match-type');
    const matchCell = row.querySelector('.route-match-cell');
    const ruleField = row.querySelector('.route-rule-field');

    matchTypeEl.addEventListener('change', (e) => {
      const value = e.target.value;
      const current = routes[index];
      if (ACTION_KINDS.has(value)) {
        current.action = value;
        delete current.matchType;
        delete current.matchMode;
        delete current.matchValue;
        delete current.aiRule;
        delete current.description;
      } else {
        delete current.action;
        current.matchType = value;
        current.matchMode = value === 'descriptor' ? 'ai' : value === 'intent' ? 'smart' : 'strict';
        if (value === 'intent' && !FOLDER_INTENTS[current.matchValue]) {
          current.matchValue = 'promotions';
        }
      }
      matchCell.innerHTML = buildRouteMatchValueControl(current);
      ruleField.innerHTML = buildRouteRuleField(current);
      bindRouteFieldHandlers(row, routes, index);
      bindMatchValueHandlers(row, routes, index);
    });

    bindMatchValueHandlers(row, routes, index);
    bindRouteFieldHandlers(row, routes, index);

    row.querySelector('.route-remove').addEventListener('click', () => {
      routes.splice(index, 1);
      state.settings.folders.routes = routes;
      renderFolderRoutesEditor();
    });
    row.querySelector('.route-name').addEventListener('input', (e) => { routes[index].name = e.target.value; });
    list.appendChild(row);
  });
  state.settings.folders.routes = routes;
}

function bindRouteFieldHandlers(row, routes, index) {
  const aiRule = row.querySelector('.route-ai-rule');
  const desc = row.querySelector('.route-description');
  if (aiRule) {
    aiRule.addEventListener('input', (e) => {
      routes[index].aiRule = e.target.value;
      routes[index].description = e.target.value;
    });
  }
  if (desc) {
    desc.addEventListener('input', (e) => { routes[index].description = e.target.value; });
  }
}

function bindMatchValueHandlers(row, routes, index) {
  const el = row.querySelector('.route-match-value');
  if (!el) return;
  const handler = (e) => { routes[index].matchValue = e.target.value; };
  el.addEventListener('input', handler);
  el.addEventListener('change', handler);
}

function collectFolderRoutesFromEditor() {
  const rows = document.querySelectorAll('.folder-route-row-wrap');
  const routes = [];
  rows.forEach((row, i) => {
    const name = row.querySelector('.route-name')?.value?.trim();
    if (!name) return;
    const kind = row.querySelector('.route-match-type')?.value || 'descriptor';
    const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, '-');
    if (ACTION_KINDS.has(kind)) {
      routes.push({ id: `route-${i}-${slug}`, name, action: kind });
      return;
    }
    const matchType = kind;
    const matchValue = row.querySelector('.route-match-value')?.value?.trim();
    const aiRule = row.querySelector('.route-ai-rule')?.value?.trim();
    const description = row.querySelector('.route-description')?.value?.trim();
    const entry = {
      id: `route-${i}-${slug}`,
      name,
      matchType,
      matchMode: matchType === 'descriptor' ? 'ai' : matchType === 'intent' ? 'smart' : 'strict',
      matchValue: matchType === 'descriptor' ? '' : (matchValue || (matchType === 'intent' ? 'promotions' : '')),
    };
    if (aiRule) {
      entry.aiRule = aiRule;
      entry.description = aiRule;
    } else if (description) {
      entry.description = description;
    }
    routes.push(entry);
  });
  return routes;
}

function toggleAdvancedRoutingSection(show) {
  const section = document.getElementById('advanced-routing-section');
  if (!section) return;
  section.classList.toggle('hidden', !show);
  if (show && (!state.settings.folders?.routes || state.settings.folders.routes.length === 0)) {
    state.settings.folders = { ...state.settings.folders, routes: structuredClone(BASE_FOLDER_ROUTES) };
    renderFolderRoutesEditor();
  }
}

// ─── Settings UI ─────────────────────────────────────────────

function toggleUnifiedInboxSection(show) {
  const section = document.getElementById('unified-inbox-section');
  if (!section) return;
  section.classList.toggle('hidden', !show);
}

function isUnifiedInboxEnabled() {
  return Boolean(state.settings.unifiedInbox?.enabled);
}

async function openSettingsPanel() {
  setSettingsSaveStatus('');
  const apiPayload = await fetchSettingsFromApi();
  mergeSettingsFromApi(apiPayload);
  renderRuntimeAccessLines(apiPayload?.runtime);
  populateSettingsForm();
  switchSettingsTab('agent');
  const panel = document.getElementById('settings-panel');
  panel.classList.remove('hidden');
  panel.setAttribute('aria-hidden', 'false');
}

function closeSettingsPanel() {
  document.getElementById('settings-panel').classList.add('hidden');
  document.getElementById('settings-panel').setAttribute('aria-hidden', 'true');
}

function initSettingsPanel() {
  document.getElementById('btn-settings').addEventListener('click', openSettingsPanel);
  document.getElementById('settings-close').addEventListener('click', closeSettingsPanel);
  document.getElementById('settings-backdrop').addEventListener('click', closeSettingsPanel);
  document.querySelectorAll('.settings-tab').forEach((btn) => {
    btn.addEventListener('click', () => switchSettingsTab(btn.dataset.tab));
  });
  document.querySelectorAll('.autonomy-option').forEach((btn) => {
    btn.addEventListener('click', () => {
      const level = btn.dataset.level;
      if (!confirmAutonomyLevel(level)) return;
      setAutonomyLevelUI(level);
    });
  });
  document.getElementById('btn-autonomy-docs')?.addEventListener('click', () => {
    window.open('autonomy-levels.html', '_blank', 'noopener');
  });
  document.getElementById('btn-settings-train-again')?.addEventListener('click', () => {
    closeSettingsPanel();
    trainAgain();
  });
  document.getElementById('btn-settings-export')?.addEventListener('click', async () => {
    await exportPreferences(true);
    await renderTrainingTab();
  });
  document.getElementById('set-advanced-routing')?.addEventListener('change', (e) => {
    toggleAdvancedRoutingSection(e.target.checked);
  });
  document.getElementById('set-unified-inbox')?.addEventListener('change', (e) => {
    toggleUnifiedInboxSection(e.target.checked);
    renderDefaultAccountSelect();
    renderInboxAccountsTable();
  });
  document.getElementById('btn-copy-account-shape')?.addEventListener('click', copyAccountJsonShape);
  document.getElementById('set-explore-remote')?.addEventListener('change', (e) => {
    toggleRemoteAccessSection(e.target.checked);
  });
  document.getElementById('btn-unified-inbox-docs')?.addEventListener('click', () => {
    window.open('unified-inbox.html', '_blank', 'noopener');
  });
  document.getElementById('btn-remote-access-docs')?.addEventListener('click', () => {
    window.open('remote-access.html', '_blank', 'noopener');
  });
  document.getElementById('btn-add-folder-route')?.addEventListener('click', () => {
    const routes = collectFolderRoutesFromEditor();
    routes.push({
      id: `route-new-${Date.now()}`,
      name: 'New folder',
      matchType: 'descriptor',
      matchMode: 'ai',
      aiRule: '',
    });
    state.settings.folders.routes = routes;
    renderFolderRoutesEditor();
  });
  document.getElementById('settings-save').addEventListener('click', async () => {
    const nextSettings = collectSettingsFromForm();
    saveSettingsToStorage(nextSettings);
    const backend = await saveSettingsToBackend(nextSettings);
    if (backend.ok) {
      setSettingsSaveStatus('Saved to ~/.config/email-swipe/settings.json', 'success');
      showStatusBanner('Advanced settings saved.', 'success');
    } else if (backend.offline) {
      setSettingsSaveStatus('Saved in browser only — start serve-ui.py to sync settings.json', 'error');
      showStatusBanner('Settings saved locally in browser only. Start serve-ui.py to persist.', 'warning');
    } else {
      setSettingsSaveStatus(backend.error || 'Save failed', 'error');
      showStatusBanner(backend.error || 'Settings save failed', 'error');
    }
    updateAccountBadge();
    updateActionMode();
  });
}

function initVictoryPanel() {
  document.getElementById('btn-victory-done').addEventListener('click', async () => {
    Object.assign(state.correctionNotes, gatherCorrectionNotesFromDOM());
    await exportPreferences(false);
    await clearSwipes();
    await persistSessionProgress({ clear: true });
    showStatusBanner('Notes saved — progress cleared for the next batch', 'ok');
  });
}

function initBatchModal() {
  document.getElementById('batch-confirm').addEventListener('click', () => {
    if (state.pendingBatch) applyBatchSpam(state.pendingBatch);
  });
  document.getElementById('batch-skip').addEventListener('click', hideBatchModal);
  document.getElementById('batch-backdrop').addEventListener('click', hideBatchModal);
}

// ─── Init ────────────────────────────────────────────────────

function inboxFingerprint(emails) {
  return emails.map((e) => e.id).sort().join('|');
}

async function boot() {
  const apiPayload = await fetchSettingsFromApi();
  if (!mergeSettingsFromApi(apiPayload)) {
    await fetchSettingsFile();
  }
  state.sessionMeta = await loadSessionMetadata();
  updateAccountBadge();

  const params = new URLSearchParams(location.search);
  if (params.get('victory') === '1' || params.get('preview') === 'victory') {
    await bootVictoryPreview();
    return;
  }

  if (params.get('reset') === '1') {
    await clearSwipes();
    await persistSessionProgress({ clear: true });
    localStorage.removeItem(INBOX_FP_KEY);
    sessionStorage.removeItem(INBOX_FP_KEY);
    history.replaceState({}, '', location.pathname);
  }

  const emails = await loadFromFile();
  if (emails.length === 0) {
    renderCards();
    return;
  }

  const fp = inboxFingerprint(emails);
  state.inboxFingerprint = fp;

  const serverProgress = await fetchSessionProgress();
  const serverFp = serverProgress?.inboxFingerprint || null;
  const serverSwipes = Array.isArray(serverProgress?.swipes) ? serverProgress.swipes : [];

  const lastFp = localStorage.getItem(INBOX_FP_KEY) || sessionStorage.getItem(INBOX_FP_KEY);
  if ((lastFp && lastFp !== fp) || (serverFp && serverFp !== fp)) {
    await clearSwipes();
    await persistSessionProgress({ clear: true });
    hideVictoryScreen();
    state.swipes = [];
    state.swipeCount = 0;
    state.correctionNotes = {};
  }

  localStorage.setItem(INBOX_FP_KEY, fp);
  sessionStorage.setItem(INBOX_FP_KEY, fp);

  // Prefer server progress so resume survives new ports / closed tabs.
  if (serverFp === fp && serverSwipes.length > 0) {
    state.swipes = serverSwipes;
    state.correctionNotes = serverProgress.correctionNotes || {};
    state.swipeCount = serverSwipes.length;
    await replaceLocalSwipes(serverSwipes);
    await startSession(emails, { resume: true });
    return;
  }

  await startSession(emails);
}

function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) return;
  navigator.serviceWorker.register('sw.js').catch(() => {});
}

function init() {
  registerServiceWorker();
  initSettingsPanel();
  initFolderPicker();
  initVictoryPanel();
  initVictoryReview();
  initBatchModal();
  document.getElementById('btn-export').addEventListener('click', () => exportPreferences(true));
  document.getElementById('btn-train-again')?.addEventListener('click', trainAgain);
  document.querySelectorAll('.action-btn').forEach((btn) => {
    btn.addEventListener('click', () => triggerAction(btn.dataset.action));
  });

  document.addEventListener('keydown', (e) => {
    const keyMap = { ArrowLeft: 'spam', ArrowRight: 'keep', i: 'important', I: 'important' };
    if (keyMap[e.key]) { e.preventDefault(); triggerAction(keyMap[e.key]); }
  });

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') refreshServerSettings();
  });

  window.EmailSwipe = {
    loadEmails: startSession,
    exportPreferences,
    trainAgain,
    getSettings: () => state.settings,
  };
  boot();
}

document.addEventListener('DOMContentLoaded', init);
