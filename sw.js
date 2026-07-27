/* sw.js — service worker for the NRL Tipping app.
 *
 * Goal: the "Add to Home Screen" app on iOS auto-updates BOTH the shell
 * (index.html + inline CSS/JS) and the data files whenever it's online, and
 * still works offline by falling back to the last cached copy.
 *
 * Strategy: NETWORK-FIRST for every same-origin GET. Each launch we try the
 * network (so the newest deploy wins), update the cache with what we got, and
 * only fall back to the cache when the network is unavailable. This is the
 * opposite of a cache-first worker, which is what usually gets "stuck" serving
 * a stale shell forever — so we deliberately avoid that trap.
 *
 * Lifecycle: skipWaiting() + clients.claim() so a new worker takes over
 * promptly; a versioned cache name (bump CACHE to invalidate everything).
 *
 * Note: service workers only run over http(s). Opening the page as a local
 * file (file://) bypasses this entirely and uses the baked-in data, exactly as
 * before — so the offline-as-a-local-file guarantee is preserved.
 */
const CACHE = 'nrl-tips-v1';
const CORE = ['./', './index.html', './nrl_data.js', './nrl_learned.js', './nrl_players.js'];

self.addEventListener('install', (e) => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(CORE).catch(() => {})));
});

self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;   // only our own files

  // Normalise the cache key so the runtime "?v=<timestamp>" cache-busters don't
  // pile up one cached entry per launch — we keep a single copy per path.
  const key = url.origin + url.pathname;

  e.respondWith((async () => {
    try {
      const fresh = await fetch(req, { cache: 'no-store' });
      if (fresh && fresh.ok) {
        const cache = await caches.open(CACHE);
        cache.put(key, fresh.clone());
      }
      return fresh;
    } catch (err) {
      // Offline: serve the last good copy (ignore the ?v= query when matching).
      const cached = (await caches.match(key)) ||
                     (await caches.match(req, { ignoreSearch: true }));
      if (cached) return cached;
      if (req.mode === 'navigate') {
        const shell = await caches.match(url.origin + url.pathname.replace(/[^/]*$/, 'index.html'));
        if (shell) return shell;
      }
      throw err;
    }
  })());
});
