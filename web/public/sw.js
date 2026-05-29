// Bump on each deploy so old caches are evicted on activate.
const VERSION = "v1";
const SHELL_CACHE = `olune-shell-${VERSION}`;
const RUNTIME_CACHE = `olune-runtime-${VERSION}`;

// The minimal shell. Pages and chunks are added on the fly via the runtime
// cache — pre-caching the App Router HTML by URL is brittle because the
// document URL is the route, not a stable file.
const SHELL_ASSETS = [
  "/",
  "/manifest.webmanifest",
  "/icon.svg",
  "/icon-maskable.svg",
  "/apple-touch-icon.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) =>
      // Use individual adds so a single 404 doesn't poison the whole install.
      Promise.all(
        SHELL_ASSETS.map((url) =>
          cache.add(url).catch(() => undefined),
        ),
      ),
    ),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => k !== SHELL_CACHE && k !== RUNTIME_CACHE)
            .map((k) => caches.delete(k)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

function isApiRequest(url) {
  return url.pathname.startsWith("/api/");
}

function isStaticAsset(url) {
  // Next.js build output + public/ static files.
  return (
    url.pathname.startsWith("/_next/static/") ||
    /\.(?:js|css|woff2?|ttf|png|jpg|jpeg|gif|webp|svg|ico)$/.test(url.pathname)
  );
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Streaming chat surface — never cache. Let the network handle it; if
  // offline, surface the network error so the UI's retry path runs.
  if (isApiRequest(url)) {
    return;
  }

  if (isStaticAsset(url)) {
    event.respondWith(cacheFirst(req, RUNTIME_CACHE));
    return;
  }

  // Documents (navigations): network-first with a shell fallback so an offline
  // launch can still paint chrome.
  if (req.mode === "navigate") {
    event.respondWith(networkFirstDocument(req));
  }
});

async function cacheFirst(req, cacheName) {
  const cache = await caches.open(cacheName);
  const hit = await cache.match(req);
  if (hit) return hit;
  try {
    const res = await fetch(req);
    if (res.ok) cache.put(req, res.clone());
    return res;
  } catch (err) {
    if (hit) return hit;
    throw err;
  }
}

async function networkFirstDocument(req) {
  const cache = await caches.open(SHELL_CACHE);
  try {
    const res = await fetch(req);
    if (res.ok) cache.put(req, res.clone());
    return res;
  } catch (err) {
    const cached = await cache.match(req);
    if (cached) return cached;
    const shell = await cache.match("/");
    if (shell) return shell;
    throw err;
  }
}
