const CACHE_NAME = '__CACHE_NAME__';
const CACHE_PREFIX = CACHE_NAME.slice(0, CACHE_NAME.lastIndexOf(':') + 1);

self.addEventListener('install', () => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys()
            .then((keys) => Promise.all(
                keys
                    .filter((key) => key.startsWith(CACHE_PREFIX) && key !== CACHE_NAME)
                    .map((key) => caches.delete(key))
            ))
            .then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (event) => {
    const request = event.request;
    if (request.method !== 'GET' || request.mode === 'navigate') {
        return;
    }
    if (request.headers.has('range') || request.headers.has('authorization')) {
        return;
    }
    if (['reload', 'no-store', 'no-cache'].includes(request.cache)) {
        return;
    }

    const url = new URL(request.url);
    if (url.origin !== self.location.origin || !url.pathname.startsWith('/assets/')) {
        return;
    }

    const fromNetwork = () => fetch(request).then((response) => {
        const cacheControl = response.headers.get('cache-control') || '';
        const store = response.status === 200
            && response.type === 'basic'
            && !/(^|,)\s*(private|no-store)\b/i.test(cacheControl)
            && !response.headers.has('set-cookie');
        if (store) {
            event.waitUntil(
                caches.open(CACHE_NAME)
                    .then((cache) => cache.put(request, response.clone()))
                    .catch(() => undefined)
            );
        }
        return response;
    });

    event.respondWith(
        caches.open(CACHE_NAME)
            .then((cache) => cache.match(request))
            .catch(() => undefined)
            .then((cached) => cached || fromNetwork())
    );
});
