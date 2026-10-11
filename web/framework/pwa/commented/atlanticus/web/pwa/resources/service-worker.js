// Cada versión produce un script diferente y toma el control sin esperar pestañas cerradas.
const CACHE_NAME = '__CACHE_NAME__';
// Sólo limpiamos cachés de esta aplicación, nunca los de otro application_id.
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

// No se registra ningún manejador fetch: navegación, recursos estáticos, Dash,
// autenticación, APIs y datos operacionales siempre siguen la política de red.
