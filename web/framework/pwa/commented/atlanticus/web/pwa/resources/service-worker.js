// El nombre incluye application_id y versión para aislar las cachés por aplicación.
const CACHE_NAME = '__CACHE_NAME__';
// Este prefijo identifica exclusivamente las versiones anteriores de la misma aplicación.
const CACHE_PREFIX = CACHE_NAME.slice(0, CACHE_NAME.lastIndexOf(':') + 1);

// La actualización del worker no requiere cerrar previamente las pestañas.
self.addEventListener('install', () => {
    self.skipWaiting();
});

// Conservamos la caché vigente y cualquier caché perteneciente a otra aplicación.
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

// Las navegaciones, operaciones no GET y peticiones especiales siguen directamente a la red.
self.addEventListener('fetch', (event) => {
    const request = event.request;
    if (request.method !== 'GET' || request.mode === 'navigate') {
        return;
    }
    // Evitamos almacenar respuestas de solicitudes con rangos o autorización explícita.
    if (request.headers.has('range') || request.headers.has('authorization')) {
        return;
    }
    // Respetamos la intención del navegador cuando solicita una recarga o evita la caché.
    if (['reload', 'no-store', 'no-cache'].includes(request.cache)) {
        return;
    }

    // Solo /assets/ del mismo origen; nunca callbacks, endpoints Dash, APIs o datos.
    const url = new URL(request.url);
    if (url.origin !== self.location.origin || !url.pathname.startsWith('/assets/')) {
        return;
    }

    // La red conserva sus errores normales; nunca fabricamos respuestas vacías de éxito.
    const fromNetwork = () => fetch(request).then((response) => {
        const cacheControl = response.headers.get('cache-control') || '';
        // Almacenamos únicamente respuestas públicas completas y correctas.
        const store = response.status === 200
            && response.type === 'basic'
            && !/(^|,)\s*(private|no-store)\b/i.test(cacheControl)
            && !response.headers.has('set-cookie');
        if (store) {
            // La escritura es no bloqueante para la respuesta y puede fallar sin romperla.
            event.waitUntil(
                caches.open(CACHE_NAME)
                    .then((cache) => cache.put(request, response.clone()))
                    .catch(() => undefined)
            );
        }
        return response;
    });

    // Cache-first para assets públicos, con red de respaldo y sin respuesta falsa offline.
    event.respondWith(
        caches.open(CACHE_NAME)
            .then((cache) => cache.match(request))
            .catch(() => undefined)
            .then((cached) => cached || fromNetwork())
    );
});
