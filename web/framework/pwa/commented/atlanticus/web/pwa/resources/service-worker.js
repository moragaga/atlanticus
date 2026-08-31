// Espejo comentado: cachea sólo assets same-origin y conserva contenido dinámico network-only.
const CACHE_NAME = '__CACHE_NAME__';
const CACHE_PREFIX = 'atlanticus-pwa:';

const isCacheableAsset = (request) => {
    if (request.method !== 'GET') {
        return false;
    }

    const url = new URL(request.url);

    return (
        url.origin === self.location.origin
        && url.pathname.startsWith('/assets/')
    );
};

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
    if (!isCacheableAsset(event.request)) {
        return;
    }

    event.respondWith(
        caches.open(CACHE_NAME).then(async (cache) => {
            const cached = await cache.match(event.request);

            if (cached) {
                return cached;
            }

            const response = await fetch(event.request);

            if (response.ok && response.type === 'basic') {
                await cache.put(event.request, response.clone());
            }

            return response;
        })
    );
});
