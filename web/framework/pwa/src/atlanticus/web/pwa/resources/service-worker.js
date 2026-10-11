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
                    .filter((key) => key.startsWith(CACHE_PREFIX))
                    .map((key) => caches.delete(key))
            ))
            .then(() => self.clients.claim())
    );
});
