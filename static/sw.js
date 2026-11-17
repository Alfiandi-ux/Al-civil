/**
 * AL-CIVIL WMS - Service Worker
 * Optimasi Caching & Kecepatan Akses Mobile Android
 */

// Naikkan versi setiap kali file statis berubah, supaya cache lama
// (terutama app.js & quick_trans.js) otomatis dibuang di perangkat pengguna.
const CACHE_NAME = 'alcivil-wms-v14';
const PRECACHE_ASSETS = [
  '/',
  '/dashboard',
  '/transaksi-cepat',
  '/inventory',
  '/static/css/style.css',
  '/static/css/premium.css',
  '/static/css/brutalist.css',
  '/static/js/app.js',
  '/static/js/quick_trans.js',
  '/static/icons/icon.svg',
  '/static/icons/icon-192.png',
  '/static/manifest.json'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_ASSETS).catch(err => {
        console.warn('Pre-cache partial failure:', err);
      });
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      );
    }).then(() => self.clients.claim())
  );
});

// Network-first strategy for dynamic data, cache-fallback for assets
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Skip non-GET and API calls (always live network)
  if (event.request.method !== 'GET' || url.pathname.startsWith('/api/') || url.pathname.startsWith('/export/')) {
    return;
  }

  // Static assets: cache-first with network refresh
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        if (cached) return cached;
        return fetch(event.request).then((response) => {
          if (response.status === 200) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(event.request, copy));
          }
          return response;
        });
      })
    );
    return;
  }

  // HTML pages: Network first, fallback to cached
  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        if (networkResponse.status === 200) {
          const responseClone = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, responseClone));
        }
        return networkResponse;
      })
      .catch(() => {
        return caches.match(event.request).then(cached => {
          if (cached) return cached;
          return caches.match('/dashboard');
        });
      })
  );
});
