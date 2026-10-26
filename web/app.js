import { buildIndex, search, defaultVariant, hasPriceSpread, nowPrice, normalize } from './search.js';
import { calc, fmtTwd, parseJpy } from './calc.js';

const BRANDS = ['UQ', 'GU', 'MUJI'];
const LABEL = { UQ: 'UNIQLO', GU: 'GU', MUJI: 'MUJI' };
const FILES = { UQ: 'data/uq.json', GU: 'data/gu.json', MUJI: 'data/muji.json', FX: 'data/fx.json' };
const DATA_CACHE = 'data-v1';
const STALE_MS = 3 * 24 * 60 * 60 * 1000; // 超過 3 天未更新 → 資料可能過期
const PAGE = 40;

const state = {
  data: {},            // UQ / GU / MUJI / FX
  index: buildIndex({}),
  loaded: false,
  query: '',
  brand: 'ALL',
  shown: PAGE,
  detail: null,        // { entry, matchedId, variant }
  jpyStr: '',
  taxRate: 10,
};

const $ = (s, el = document) => el.querySelector(s);
const content = $('#content');
const input = $('#q');

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// ---------- 資料：先用手機裡的快取，背景再更新 ----------

async function readCache() {
  if (!('caches' in window)) return;
  try {
    const cache = await caches.open(DATA_CACHE);
    await Promise.all(Object.entries(FILES).map(async ([k, url]) => {
      const res = await cache.match(url);
      if (res) state.data[k] = await res.json();
    }));
  } catch (e) { /* 快取不可用時就只靠網路 */ }
}

async function refresh() {
  let cache = null;
  try { cache = 'caches' in window ? await caches.open(DATA_CACHE) : null; } catch (e) { /* ignore */ }
  let changed = false;
  await Promise.all(Object.entries(FILES).map(async ([k, url]) => {
    try {
      const res = await fetch(url, { cache: 'no-cache' });
      if (!res.ok) return;
      const copy = res.clone();
      const json = await res.json();
      if (!state.data[k] || state.data[k].updatedAt !== json.updatedAt) {
        state.data[k] = json;
        changed = true;
      }
      if (cache) await cache.put(url, copy);
    } catch (e) { /* 離線：沿用快取 */ }
  }));
  return changed;
}

function rebuild() {
  state.index = buildIndex({ UQ: state.data.UQ, GU: state.data.GU, MUJI: state.data.MUJI });
}

// ---------- 格式 ----------

function fmtTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}/${p(d.getMonth() + 1)}/${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
const isStale = (iso) => !iso || Date.now() - new Date(iso).getTime() > STALE_MS;

function rateText() {
  const fx = state.data.FX;
  if (!fx) return '尚無匯率資料';
  return `匯率 ${fx.rate.toFixed(4)}・${fx.source.replace(/（.*）/, '')}・${fx.date.replace(/-/g, '/')}`;
}

function priceHtml(rec, size = 'card') {
  const now = rec.salePrice != null ? rec.salePrice : rec.price;
  const range = rec.salePrice != null && rec.maxPrice > rec.salePrice;
  const nowText = range ? `${fmtTwd(now)}–${rec.maxPrice.toLocaleString('en-US')}` : fmtTwd(now);
  if (rec.salePrice == null) return `<span class="now">${nowText}</span>`;
  const tag = size === 'card' ? '特價' : '特價中';
  return size === 'card'
    ? `<span class="now">${nowText}</span><span class="orig">${fmtTwd(rec.price)}</span><span class="sale-tag">${tag}</span>`
    : `<span class="orig">${fmtTwd(rec.price)}</span><span class="now">${nowText}</span><span class="sale-tag">${tag}</span>`;
}

const PLACEHOLDER_SVG = (size) => `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="#7D8792" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 6a2 2 0 1 1 2-2"/><path d="M12 6v1.5L3 14h18l-9-6.5"/><path d="M4 14v2h16v-2"/></svg>`;

function imgHtml(rec, cls, svgSize) {
  // 圖片載不到時顯示灰色佔位圖（img 失敗就移除，露出底下的佔位）
  const lazy = cls === 'hero' ? '' : ' loading="lazy"';
  const img = rec.image ? `<img src="${esc(rec.image)}" alt=""${lazy} decoding="async" referrerpolicy="no-referrer" onerror="this.remove()">` : '';
  return `<div class="${cls} img-${rec.brand}">${PLACEHOLDER_SVG(svgSize)}<span class="ph-label">商品圖</span>${img}</div>`;
}

// ---------- 畫面 ----------

function render() {
  const inDetail = !!state.detail;
  $('#searchBar').hidden = inDetail;
  $('#clear').hidden = !state.query;
  for (const b of document.querySelectorAll('.chip')) b.setAttribute('aria-pressed', String(b.dataset.brand === state.brand));
  if (inDetail) return renderDetail();
  const q = state.query.trim();
  if (!normalize(q)) return renderHome();
  const r = search(state.index, q, state.brand);
  if (!r.items.length) return renderEmpty(r);
  renderResults(r);
}

function renderHome() {
  const rows = BRANDS.map((b) => {
    const d = state.data[b];
    const stale = isStale(d && d.updatedAt);
    const val = d ? `更新於 ${fmtTime(d.updatedAt)}${stale ? '・資料可能過期' : ''}` : '尚無資料';
    return `<div class="status-row"><span>${LABEL[b]}</span><span class="val${stale ? ' stale' : ''}">${val}</span></div>`;
  }).join('');
  const noData = state.loaded && !BRANDS.some((b) => state.data[b]);
  content.innerHTML = `
    <div class="stack">
      ${noData ? '<div class="notice">手機裡還沒有商品資料。請先連上網路開啟一次，之後在店內沒有訊號也能查。</div>' : ''}
      <div class="card">
        <h2>怎麼查</h2>
        <p>輸入吊牌上的商品編號，會自動判斷品牌並直接打開那件商品。</p>
        <p>也可以輸入關鍵字，例如「外套」，再點上方品牌縮小範圍。</p>
      </div>
      <div class="card status-card">
        <h2>台灣官網資料狀態</h2>
        ${rows}
        <div class="status-row rate"><span>日圓匯率</span><span class="val">${esc(rateText().replace(/^匯率 /, ''))}</span></div>
      </div>
    </div>`;
}

function renderEmpty(r) {
  const num = r.mode !== 'text';
  const q = state.query.trim();
  const tips = num
    ? ['確認吊牌上的編號有沒有輸入正確', '這件可能沒有在台灣販售', '改用關鍵字搜尋，例如「外套」']
    : ['換個說法，例如「夾克」「羽絨」', state.brand === 'ALL' ? '這件可能沒有在台灣販售' : '切換到「全部」，看看其他品牌', '改用吊牌上的商品編號搜尋'];
  content.innerHTML = `
    <div class="empty">
      <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="#8A939D" stroke-width="1.4" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5M8.5 8.5l5 5M13.5 8.5l-5 5"/></svg>
      <h2>${num ? `台灣官網查無編號「${esc(q)}」` : `台灣官網查無「${esc(q)}」`}</h2>
      <div class="card">${tips.map((t) => `<p>・${esc(t)}</p>`).join('')}</div>
      ${state.loaded ? '' : '<p class="result-header">資料載入中…</p>'}
    </div>`;
}

let lastResults = [];

function renderResults(r) {
  lastResults = r.items;
  const q = state.query.trim();
  let header;
  if (r.mode === 'exact' && r.ambiguous) header = `<p class="result-header warn">這個編號在兩個品牌都有，請點選你看到的那件</p>`;
  else if (r.mode !== 'text') header = `<p class="result-header">編號查詢・自動比對三個品牌・${r.items.length} 件</p>`;
  else header = `<p class="result-header">「${esc(q)}」・${state.brand === 'ALL' ? '全部品牌' : LABEL[state.brand]}・${r.items.length} 件</p>`;
  const cards = r.items.slice(0, state.shown).map(({ entry, matchedId }, i) => {
    const rec = entry.rec;
    const id = matchedId || rec.id;
    return `<button type="button" class="item" data-idx="${i}">
      ${imgHtml(rec, 'thumb', 44)}
      <div class="item-body">
        <div class="meta"><span class="tag tag-${rec.brand}">${LABEL[rec.brand]}</span><span class="id">${esc(id)}</span></div>
        <span class="name">${esc(rec.name)}</span>
        <div class="prices">${priceHtml(rec)}</div>
      </div>
    </button>`;
  }).join('');
  const more = r.items.length > state.shown ? '<div class="more" id="more" aria-hidden="true"></div>' : '';
  content.innerHTML = `<div class="results">${header}<div class="grid">${cards}</div>${more}</div>`;
  const sentinel = $('#more');
  if (sentinel && 'IntersectionObserver' in window) {
    const io = new IntersectionObserver((es) => {
      if (es.some((e) => e.isIntersecting)) { io.disconnect(); state.shown += PAGE; renderResults(r); }
    }, { rootMargin: '400px' });
    io.observe(sentinel);
  }
}

function openDetail(entry, matchedId, push = true) {
  state.detail = { entry, matchedId, variant: defaultVariant(entry.rec, matchedId) };
  state.jpyStr = '';
  if (push) history.pushState({ detail: true }, '');
  render();
  window.scrollTo(0, 0);
}

function closeDetail() {
  state.detail = null;
  render();
}

function selected() {
  const { entry, variant } = state.detail;
  const rec = entry.rec;
  if (!variant) return { price: rec.price, salePrice: rec.salePrice, url: rec.url, ids: [rec.id] };
  return { price: variant.price, salePrice: variant.salePrice, url: variant.url || rec.url, ids: variant.ids || [rec.id] };
}

function renderDetail() {
  const { entry, matchedId } = state.detail;
  const rec = entry.rec;
  const brandData = state.data[rec.brand] || {};
  const stale = isStale(brandData.updatedAt);
  const spread = hasPriceSpread(rec);
  const sel = selected();
  const id = matchedId || sel.ids[0] || rec.id;
  const priceRec = spread ? { ...sel, maxPrice: nowPrice(sel), brand: rec.brand } : rec;
  const variants = spread ? `
    <div class="card variants">
      <h3>各顏色價格</h3>
      <p class="hint">這件商品依顏色價格不同，請選你手上的顏色。</p>
      <div class="variant-list">
        ${rec.variants.map((v, i) => `<button type="button" class="variant" data-variant="${i}" aria-pressed="${v === state.detail.variant}">
          <span>${esc(v.color || `款式 ${i + 1}`)}</span>
          <span class="v-price${v.salePrice != null ? ' sale' : ''}">${fmtTwd(nowPrice(v))}${v.salePrice != null ? '（特價）' : ''}</span>
        </button>`).join('')}
      </div>
    </div>` : '';
  content.innerHTML = `
    <div class="detail-top">
      <button type="button" class="icon-btn" id="back" aria-label="返回搜尋結果">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#15191E" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg>
      </button>
      <span>商品比價</span>
    </div>
    <div class="detail">
      ${imgHtml(rec, 'hero', 64)}
      <div class="info">
        <div class="meta"><span class="tag tag-${rec.brand}">${LABEL[rec.brand]}</span><span class="id">編號 ${esc(id)}</span></div>
        <h2>${esc(rec.name)}</h2>
        <div class="tw-price" id="twPrice"><span class="label">台灣售價</span>${priceHtml(priceRec, 'detail')}</div>
        <div class="updated-row">
          <span class="updated${stale ? ' stale' : ''}">台灣資料更新：${fmtTime(brandData.updatedAt)}${stale ? '・資料可能過期' : ''}</span>
          <a class="ext-link" id="extLink" href="${esc(sel.url)}" target="_blank" rel="noopener">在官網查看
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 4h6v6M20 4l-9 9M18 14v6H4V6h6"/></svg>
          </a>
        </div>
      </div>
      ${variants}
      <div class="card">
        <label for="jpy" class="jpy-label">日本吊牌價（含稅）</label>
        <div class="jpy-box"><span class="yen">¥</span>
          <input id="jpy" type="text" inputmode="numeric" pattern="[0-9]*" autocomplete="off" placeholder="例如 3990" value="${esc(state.jpyStr)}">
        </div>
        <div class="tax-row"><span class="label">稅率</span>
          <button type="button" class="tax-chip" data-tax="10" aria-pressed="${state.taxRate === 10}">10% 一般</button>
          <button type="button" class="tax-chip" data-tax="8" aria-pressed="${state.taxRate === 8}">8% 食品</button>
        </div>
      </div>
      <div id="calcOut"></div>
    </div>`;
  renderCalc();
}

// 只更新計算結果，避免輸入日幣時重畫輸入框
function renderCalc() {
  const out = $('#calcOut');
  if (!out) return;
  const fx = state.data.FX;
  const jpy = parseJpy(state.jpyStr);
  if (!jpy) {
    out.innerHTML = '<p class="calc-hint">輸入日幣價格後，會顯示台幣、退稅後價格和價差。</p>';
    return;
  }
  if (!fx) {
    out.innerHTML = '<div class="notice">手機裡還沒有匯率資料，請連上網路後重新開啟。</div>';
    return;
  }
  const tw = nowPrice(selected());
  const c = calc(jpy, state.taxRate, fx.rate, tw);
  const diffText = c.cheaper ? `便宜 ${fmtTwd(c.diff)}（−${c.pct}%）` : `貴 ${fmtTwd(-c.diff)}（+${c.pct}%）`;
  const threshold = c.meetsThreshold
    ? '單件已達退稅門檻（未稅 ¥5,000）。'
    : `單件未達退稅門檻：同店同日合計需滿 ¥${c.thresholdInclTax.toLocaleString('en-US')}（含稅），退稅後價格才成立。`;
  out.innerHTML = `
    <div class="card">
      <div class="calc-row"><span>刷卡當下</span><span style="font-weight:500">${fmtTwd(c.pay)}</span></div>
      <div class="calc-row"><span>退稅後實際成本</span><span style="font-weight:700">${fmtTwd(c.refund)}</span></div>
      <div class="diff-box ${c.cheaper ? 'cheaper' : 'pricier'}">
        <span class="t">退稅後與台灣售價（${fmtTwd(tw)}）相比</span>
        <span class="v">${diffText}</span>
      </div>
      <p class="threshold${c.meetsThreshold ? '' : ' warn'}">${threshold}</p>
      <p class="rate-note">${esc(rateText())}。這是國際參考匯率，實際刷卡金額通常會再多 1–2%（匯差與手續費）。</p>
    </div>`;
}

// ---------- 事件 ----------

let composing = false;
function onQuery() {
  if (composing) return; // 中文輸入法選字中先不搜尋
  state.query = input.value;
  state.shown = PAGE;
  const r = search(state.index, state.query, state.brand);
  if (r.mode === 'exact' && r.jump) return openDetail(r.jump.entry, r.jump.matchedId);
  render();
}
input.addEventListener('compositionstart', () => { composing = true; });
input.addEventListener('compositionend', () => { composing = false; onQuery(); });
input.addEventListener('input', onQuery);
input.addEventListener('keydown', (e) => { if (e.key === 'Enter') input.blur(); });

$('#clear').addEventListener('click', () => {
  input.value = '';
  state.query = '';
  render();
  input.focus();
});

$('#chips').addEventListener('click', (e) => {
  const b = e.target.closest('.chip');
  if (!b) return;
  state.brand = b.dataset.brand;
  state.shown = PAGE;
  render();
});

content.addEventListener('click', (e) => {
  const item = e.target.closest('.item');
  if (item) {
    const hit = lastResults[Number(item.dataset.idx)];
    if (hit) openDetail(hit.entry, hit.matchedId);
    return;
  }
  if (e.target.closest('#back')) {
    if (history.state && history.state.detail) history.back();
    else closeDetail();
    return;
  }
  const v = e.target.closest('.variant');
  if (v && state.detail) {
    state.detail.variant = state.detail.entry.rec.variants[Number(v.dataset.variant)];
    state.detail.matchedId = null;
    const y = window.scrollY;
    renderDetail();
    window.scrollTo(0, y);
    return;
  }
  const t = e.target.closest('.tax-chip');
  if (t) {
    state.taxRate = Number(t.dataset.tax);
    for (const b of document.querySelectorAll('.tax-chip')) b.setAttribute('aria-pressed', String(b === t));
    renderCalc();
  }
});

content.addEventListener('input', (e) => {
  if (e.target.id === 'jpy') {
    state.jpyStr = e.target.value;
    renderCalc();
  }
});

window.addEventListener('popstate', () => {
  if (state.detail) closeDetail();
});

// ---------- 啟動 ----------

(async function start() {
  render();
  await readCache();
  rebuild();
  state.loaded = BRANDS.some((b) => state.data[b]);
  render();
  const changed = await refresh();
  state.loaded = true;
  if (changed) {
    rebuild();
    if (!state.detail) render();
  } else if (!state.detail) {
    render();
  }
})();

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {}));
}
