// 搜尋（SPEC「搜尋框」）。純函式，方便測試。

const DASHES = /[\s\-‐‑‒–—―]/g;

// 全形轉半形、轉小寫、去掉空白與連字號
export function normalize(s) {
  return String(s || '').normalize('NFKC').toLowerCase().replace(DASHES, '');
}

export function isNumeric(q) {
  return /^\d+$/.test(q);
}

// 目前售價（有特價用特價）
export const nowPrice = (v) => (v.salePrice != null ? v.salePrice : v.price);

export function buildIndex(datasets) {
  const entries = [];
  const byId = new Map();
  for (const [brand, data] of Object.entries(datasets)) {
    for (const rec of (data && data.items) || []) {
      const ids = new Set([rec.id, ...(rec.altIds || []), ...(rec.variants || []).flatMap((v) => v.ids || [])].map(normalize));
      const e = { brand, rec, ids: [...ids], name: normalize(rec.name), cat: normalize(rec.category) };
      entries.push(e);
      for (const id of ids) {
        if (!byId.has(id)) byId.set(id, []);
        byId.get(id).push(e);
      }
    }
  }
  return { entries, byId };
}

/**
 * 回傳 { mode, q, items: [{entry, matchedId}], ambiguous, jump }
 * mode：empty | exact | prefix | text
 * jump：完全吻合只有 1 件、且沒有更長的編號以它開頭時，直接打開的那件
 */
export function search(index, query, brand = 'ALL') {
  const q = normalize(query);
  if (!q) return { mode: 'empty', q, items: [] };
  if (isNumeric(q)) {
    const exact = index.byId.get(q) || [];
    const prefix = [];
    for (const e of index.entries) {
      const id = e.ids.find((i) => i.startsWith(q) && i !== q);
      if (id && !exact.includes(e)) prefix.push({ entry: e, matchedId: id });
    }
    if (exact.length) {
      const items = exact.map((e) => ({ entry: e, matchedId: q }));
      const ambiguous = new Set(exact.map((e) => e.brand)).size > 1;
      const jump = exact.length === 1 && prefix.length === 0 ? items[0] : null;
      return { mode: 'exact', q, items, ambiguous, jump };
    }
    prefix.sort((a, b) => a.matchedId.length - b.matchedId.length || a.matchedId.localeCompare(b.matchedId));
    return { mode: 'prefix', q, items: prefix };
  }
  const ranked = [];
  for (const e of index.entries) {
    if (brand !== 'ALL' && e.brand !== brand) continue;
    let rank = -1;
    if (e.name.startsWith(q)) rank = 0;
    else if (e.name.includes(q)) rank = 1;
    else if (e.cat.includes(q)) rank = 2;
    if (rank >= 0) ranked.push({ rank, entry: e });
  }
  ranked.sort((a, b) => a.rank - b.rank);
  return { mode: 'text', q, items: ranked.map((r) => ({ entry: r.entry, matchedId: null })) };
}

// 代表價格的顏色：最多顏色共用的售價（少數出清色不會拉低整件商品）；同樣多時取較高價
export function typicalVariant(rec) {
  const vs = rec.variants || [];
  if (!vs.length) return null;
  const count = new Map();
  for (const v of vs) count.set(nowPrice(v), (count.get(nowPrice(v)) || 0) + 1);
  let best = null;
  for (const [p, n] of count) if (!best || n > best.n || (n === best.n && p > best.p)) best = { p, n };
  return vs.find((v) => nowPrice(v) === best.p);
}

// 列表顯示用：代表價格＋其他顏色的最低／最高價。沒有各色資料時用整件商品的價格
export function priceSummary(rec) {
  const t = typicalVariant(rec);
  if (!t) return { now: nowPrice(rec), price: rec.price, sale: rec.salePrice != null, low: null, high: null, lowSale: false };
  const now = nowPrice(t);
  const others = rec.variants.map(nowPrice);
  const low = Math.min(...others), high = Math.max(...others);
  const lowSale = low < now && rec.variants.some((v) => v.salePrice != null && nowPrice(v) === low);
  return { now, price: t.price, sale: t.salePrice != null, low: low < now ? low : null, high: high > now ? high : null, lowSale };
}

// 詳細頁預設選的顏色：搜尋的編號所在的顏色；否則選代表價格的顏色（和列表顯示一致）
export function defaultVariant(rec, matchedId) {
  const vs = rec.variants || [];
  if (!vs.length) return null;
  if (matchedId) {
    const hit = vs.find((v) => (v.ids || []).map(normalize).includes(matchedId));
    if (hit) return hit;
  }
  return typicalVariant(rec);
}

// 顏色之間價格是否不同
export function hasPriceSpread(rec) {
  const set = new Set((rec.variants || []).map((v) => nowPrice(v) + '/' + v.price));
  return set.size > 1;
}

// 篩選與排序（只用在關鍵字搜尋）。opts：{ audience: 'ALL'|'女'|'男'|'童'|'嬰', saleOnly, sort: 'rel'|'price_asc'|'price_desc'|'discount' }
export const DEFAULT_FILTERS = { audience: 'ALL', saleOnly: false, sort: 'rel' };

export function filtersActive(opts) {
  return opts.audience !== 'ALL' || opts.saleOnly || opts.sort !== 'rel';
}

// 排序用代表價格；「只看特價」仍是任一顏色特價就算
const recNow = (rec) => priceSummary(rec).now;
const discount = (rec) => { const s = priceSummary(rec); return s.price ? 1 - s.now / s.price : 0; };

export function applyFilters(items, opts) {
  let out = items;
  if (opts.audience !== 'ALL') out = out.filter(({ entry }) => (entry.rec.audience || []).includes(opts.audience));
  if (opts.saleOnly) out = out.filter(({ entry }) => entry.rec.salePrice != null);
  const by = {
    price_asc: (a, b) => recNow(a.entry.rec) - recNow(b.entry.rec),
    price_desc: (a, b) => recNow(b.entry.rec) - recNow(a.entry.rec),
    discount: (a, b) => discount(b.entry.rec) - discount(a.entry.rec),
  }[opts.sort];
  return by ? [...out].sort(by) : out; // sort 是穩定排序，同價時保留相關度順序
}

// 日本官網價格。jpData：{ items: { 編號: { name, url, variants: [{ color, price, sale }] } } }
// 用台灣商品的編號找；顏色代碼（例如「57 OLIVE」的 57）相同就用該色價格，否則用最多顏色共用的價格
export function findJp(jpData, rec, ids = []) {
  const items = jpData && jpData.items;
  if (!items) return null;
  for (const id of [...ids, rec.id, ...(rec.altIds || [])]) if (items[id]) return items[id];
  return null;
}

export function jpPriceFor(jp, color) {
  const vs = jp.variants || [];
  if (!vs.length) return null;
  const code = (color || '').split(' ')[0];
  const match = code ? vs.find((v) => v.color.split(' ')[0] === code) : null;
  let pick = match;
  if (!pick) {
    const count = new Map();
    for (const v of vs) count.set(v.price, (count.get(v.price) || 0) + 1);
    let best = null;
    for (const [p, n] of count) if (!best || n > best.n || (n === best.n && p > best.p)) best = { p, n };
    pick = vs.find((v) => v.price === best.p);
  }
  const prices = vs.map((v) => v.price);
  const low = Math.min(...prices), high = Math.max(...prices);
  return { price: pick.price, sale: pick.sale, matched: !!match,
    low: low < pick.price ? low : null, high: high > pick.price ? high : null };
}
