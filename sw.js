// TSB Parte Diario — Service Worker
// Cambiá CACHE_VERSION cada vez que desplegués una actualización
const CACHE_VERSION = 'tsb-v3';

const PRECACHE = [
  '/tsb-parte-diario/',
  '/tsb-parte-diario/index.html',
  '/tsb-parte-diario/dashboard.html',
  '/tsb-parte-diario/manifest.json',
  '/tsb-parte-diario/icons/icon-192x192.png',
  '/tsb-parte-diario/icons/icon-512x512.png'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_VERSION)
      .then(cache => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(key => key !== CACHE_VERSION)
          .map(key => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  if (event.request.url.includes('script.google.com')) return;
  if (!event.request.url.includes('manolopariente.github.io')) return;

  event.respondWith(
    fetch(event.request)
      .then(networkResponse => {
        const clone = networkResponse.clone();
        caches.open(CACHE_VERSION).then(cache => cache.put(event.request, clone));
        return networkResponse;
      })
      .catch(() => {
        return caches.match(event.request)
          .then(cached => cached || new Response(
            '<h2 style="font-family:sans-serif;text-align:center;margin-top:3rem">Sin conexión — revisá tu red</h2>',
            { headers: { 'Content-Type': 'text/html' } }
          ));
      })
  );
});
