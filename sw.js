// TSB Parte Diario — Service Worker
// Actualización silenciosa: se aplica al próximo inicio de la app

const CACHE_NAME = 'tsb-v1';

const PRECACHE = [
  '/tsb-parte-diario/',
  '/tsb-parte-diario/index.html',
  '/tsb-parte-diario/dashboard.html',
  '/tsb-parte-diario/manifest.json',
  '/tsb-parte-diario/icons/icon-192x192.png',
  '/tsb-parte-diario/icons/icon-512x512.png'
];

// ── Instalación: pre-cachea los archivos principales ──────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting())   // activa el nuevo SW de inmediato
  );
});

// ── Activación: elimina cachés viejos silenciosamente ─────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(key => key !== CACHE_NAME)
          .map(key => caches.delete(key))
      )
    ).then(() => self.clients.claim())  // toma control de todas las pestañas
  );
});

// ── Fetch: Network First → caché como fallback ────────────────────────────────
// Intenta siempre traer la versión más nueva de la red.
// Si no hay conexión, sirve desde caché.
self.addEventListener('fetch', event => {
  // Solo intercepta GET; ignora Apps Script y externos
  if (event.request.method !== 'GET') return;
  if (event.request.url.includes('script.google.com')) return;
  if (!event.request.url.includes('manolopariente.github.io')) return;

  event.respondWith(
    fetch(event.request)
      .then(networkResponse => {
        // Actualiza el caché con la respuesta fresca
        const clone = networkResponse.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        return networkResponse;
      })
      .catch(() => {
        // Sin conexión → sirve desde caché
        return caches.match(event.request)
          .then(cached => cached || new Response(
            '<h2 style="font-family:sans-serif;text-align:center;margin-top:3rem">Sin conexión — revisá tu red</h2>',
            { headers: { 'Content-Type': 'text/html' } }
          ));
      })
  );
});
