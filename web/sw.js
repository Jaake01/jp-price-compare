// 離線快取：網頁本身先用快取、背景更新；商品圖只快取看過的。
// 商品資料與匯率由 app.js 自己存在 Cache Storage（data-v1）。
const SHELL = 'shell-v5';
const IMAGES = 'img-v1';
const FONTS = 'font-v1';
const MAX_IMAGES = 400;
const SHELL_FILES = ['./', 'index.html', 'styles.css', 'app.js', 'search.js', 'calc.js', 'manifest.webmanifest',
  'icons/icon.svg', 'icons/icon-192.png', 'icons/icon-512.png', 'icons/apple-touch-icon.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(SHELL_FILES)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  const keep = [SHELL, IMAGES, FONTS, 'data-v1'];
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => !keep.includes(k)).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

async function trimImages() {
  const c = await caches.open(IMAGES);
  const keys = await c.keys();
  for (const k of keys.slice(0, Math.max(0, keys.length - MAX_IMAGES))) await c.delete(k);
}

async function cacheFirst(cacheName, req, onStore) {
  const c = await caches.open(cacheName);
  const hit = await c.match(req);
  if (hit) return hit;
  const res = await fetch(req);
  if (res.ok || res.type === 'opaque') {
    await c.put(req, res.clone());
    if (onStore) onStore();
  }
  return res;
}

async function staleWhileRevalidate(req) {
  const c = await caches.open(SHELL);
  const hit = await c.match(req, { ignoreSearch: true });
  const net = fetch(req).then((res) => { if (res.ok) c.put(req, res.clone()); return res; }).catch(() => null);
  return hit || (await net) || new Response('離線中', { status: 503 });
}

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin === location.origin) {
    if (url.pathname.includes('/data/')) return; // 交給 app.js 處理
    if (req.mode === 'navigate') {
      e.respondWith(staleWhileRevalidate(new Request(new URL('index.html', self.registration.scope))));
      return;
    }
    e.respondWith(staleWhileRevalidate(req));
    return;
  }
  if (url.hostname === 'fonts.googleapis.com' || url.hostname === 'fonts.gstatic.com') {
    e.respondWith(cacheFirst(FONTS, req).catch(() => new Response('', { status: 503 })));
    return;
  }
  if (req.destination === 'image') {
    e.respondWith(cacheFirst(IMAGES, req, trimImages).catch(() => new Response('', { status: 503 })));
  }
});
