const STATIC_CACHE = "sysmantech-static-v2";
const STATIC_ASSETS = [
    "/manifest.webmanifest",
    "/static/css/pwa-ios.css",
    "/static/icons/icon-180.png",
    "/static/icons/icon-192.png",
    "/static/icons/icon-512.png",
    "/static/splash/iphone-se.png",
    "/static/splash/iphone-8.png",
    "/static/splash/iphone-x.png",
    "/static/splash/iphone-xr.png",
    "/static/splash/iphone-max.png",
    "/static/splash/iphone-12.png",
    "/static/splash/iphone-15-pro.png",
    "/static/splash/iphone-15-pro-max.png",
    "/static/css/dashboard-theme.css",
    "/static/css/login.css",
    "/static/css/onsite-calls.css",
    "/static/js/dashboard-layout.js",
    "/static/js/login.js",
    "/static/js/onsite-calls.js"
];

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(STATIC_CACHE)
            .then((cache) => cache.addAll(STATIC_ASSETS))
            .catch(() => null)
            .then(() => self.skipWaiting())
    );
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys().then((keys) => Promise.all(
            keys
                .filter((key) => key !== STATIC_CACHE)
                .map((key) => caches.delete(key))
        )).then(() => self.clients.claim())
    );
});

self.addEventListener("fetch", (event) => {
    if (event.request.method !== "GET") {
        return;
    }

    const requestUrl = new URL(event.request.url);
    if (requestUrl.origin !== self.location.origin) {
        return;
    }

    const isStaticAsset = requestUrl.pathname.startsWith("/static/");
    const isManifestRequest = requestUrl.pathname === "/manifest.webmanifest";

    if (!isStaticAsset && !isManifestRequest) {
        return;
    }

    event.respondWith(
        caches.match(event.request).then((cachedResponse) => {
            if (cachedResponse) {
                return cachedResponse;
            }

            return fetch(event.request).then((networkResponse) => {
                if (!networkResponse || networkResponse.status !== 200) {
                    return networkResponse;
                }

                const responseClone = networkResponse.clone();
                caches.open(STATIC_CACHE).then((cache) => {
                    cache.put(event.request, responseClone);
                });
                return networkResponse;
            });
        })
    );
});

self.addEventListener("notificationclick", (event) => {
    event.notification.close();

    const fallbackUrl = "/onsite-calls";
    const targetUrl = (event.notification && event.notification.data && event.notification.data.url) || fallbackUrl;

    event.waitUntil(
        clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
            for (const client of clientList) {
                if (!client || !client.url) {
                    continue;
                }

                const clientUrl = new URL(client.url);
                const destinationUrl = new URL(targetUrl, self.location.origin);
                if (clientUrl.pathname === destinationUrl.pathname && "focus" in client) {
                    return client.focus();
                }
            }

            if (clients.openWindow) {
                return clients.openWindow(targetUrl);
            }

            return null;
        })
    );
});
