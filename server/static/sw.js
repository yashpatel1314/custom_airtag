// Minimal worker: it exists to make the dashboard installable and to let
// the shell open instantly. Location data is never cached — a stale
// position is worse than no position — so /api is always network-only.
const CACHE = "tracker-shell-v1";
const SHELL = [
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/manifest.webmanifest",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(
    keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  const cacheable = e.request.method === "GET"
    && url.origin === location.origin
    && !url.pathname.startsWith("/api/");
  if (!cacheable) return;  // fall through to the network
  e.respondWith(
    caches.match(e.request).then((hit) => hit || fetch(e.request))
  );
});
