/* ZuZan service worker - keeps the app SHELL available offline (so the app opens with no signal).
   It deliberately never touches the API: no financial or payroll data is cached or replayed, and nothing is saved offline.
   Bump VERSION to force every device to drop old files. */
const VERSION = "zuzan-shell-v1";
const SHELL = ["/", "/index.html", "/manifest.json"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL).catch(() => {})).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k)))).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;                 // the API lives on another origin: never cached

  if (req.mode === "navigate") {                                   // page loads: always try the network first so a deploy shows up at once
    e.respondWith(
      fetch(req).then((res) => {
        if (res.ok) { const copy = res.clone(); caches.open(VERSION).then((c) => c.put("/index.html", copy)); }
        return res;
      }).catch(() => caches.match("/index.html").then((r) => r || caches.match("/")))
    );
    return;
  }

  if (url.pathname.startsWith("/static/") || /\.(?:js|css|png|jpg|svg|ico|woff2?)$/.test(url.pathname)) {
    e.respondWith(                                                 // build files have hashed names: cache first, refresh quietly
      caches.match(req).then((hit) => {
        const net = fetch(req).then((res) => { if (res.ok) { const copy = res.clone(); caches.open(VERSION).then((c) => c.put(req, copy)); } return res; }).catch(() => hit);
        return hit || net;
      })
    );
  }
});
