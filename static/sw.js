// sw.js
const NO_CACHE = true;                    // false en prod
const VERSION  = NO_CACHE
  ? (self.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`)
  : 'v7';

const CACHE = `valtrack-${VERSION}`;

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil((async () => {
  await clients.claim();
  const keys = await caches.keys();
  await Promise.all(keys.map(k => k !== CACHE && caches.delete(k)));
})()));

// (optionnel) en NO_CACHE, on bypass aussi le cache SW
self.addEventListener('fetch', e => {
  if (NO_CACHE) { e.respondWith(fetch(e.request)); }
});
