/* Email Swipe — shell-only service worker (no mail data). */
const CACHE = 'email-swipe-shell-v7';

const SHELL_PATHS = new Set([
  '/',
  '/index.html',
  '/styles.css',
  '/app.js',
  '/folder-intent.js',
  '/manifest.json',
  '/autonomy-levels.html',
  '/unified-inbox.html',
  '/remote-access.html',
  '/sw.js',
]);

function isShellRequest(url) {
  if (url.origin !== self.location.origin) return false;
  const path = url.pathname.endsWith('/') ? '/' : url.pathname.replace(/\/$/, '') || '/';
  if (path.startsWith('/api/')) return false;
  if (path.endsWith('emails.json') || path.endsWith('demo-emails.json')) return false;
  if (path.endsWith('session-metadata.json') || path.endsWith('settings.json')) return false;
  if (path.endsWith('preferences.json')) return false;
  if (SHELL_PATHS.has(path)) return true;
  return /\.(html|css|js)$/.test(path);
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(['./index.html', './styles.css', './app.js', './folder-intent.js', './manifest.json']))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET' || !isShellRequest(new URL(event.request.url))) {
    return;
  }
  event.respondWith(
    caches.match(event.request).then((cached) => {
      const network = fetch(event.request).then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(event.request, copy));
        }
        return response;
      });
      return cached || network;
    }),
  );
});
