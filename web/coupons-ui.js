// 優惠券分頁：讀清單（私人 repo，用唯讀權杖）、最愛（預設頁，可排序）、依類別列出、券詳細頁。
// 券圖與條碼不下載，一律開原圖網址、店家券頁或 MATCHA 原頁，所以要有網路才打得開。
import {
  CATEGORIES, known, slashDate, expiryState, groupByCategory, categoryCounts, dataStatus,
  resolveFavs, toggleId, moveId, showTarget, groupCoupons, SOURCE_LABEL,
} from './coupons-data.js';

const DATA_CACHE = 'data-v1';
const CACHE_KEY = 'data/coupons.json';         // 快取裡的位置（同一個網址，不管資料從哪裡讀）
const LS_SOURCE = 'coupons.source';            // { repo, token }：只存在這支手機
const LS_FAVS = 'coupons.favs';                // 最愛的券 id（照使用者排的順序）
const EMBED_HINT_MS = 8000;

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const $ = (s) => document.querySelector(s);

const st = {
  data: null,
  fetchError: '',
  loading: false,
  view: '最愛',       // 最愛／全部／各類別
  sorting: false,     // 最愛的「調整順序」模式
  showSettings: false,
  detail: null,       // 正在看的券 id
  embed: null,        // 正在 App 內顯示的券
};
let rerender = () => {};

function lsGet(key, fallback) {
  try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; } catch (e) { return fallback; }
}
function lsSet(key, val) {
  try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) { /* 私密模式等：這次有效，下次要重設 */ }
}
const source = () => lsGet(LS_SOURCE, null);
const favIds = () => lsGet(LS_FAVS, []);
// 列表與最愛以「店」為單位：同一家店在不同網站的券合併成一組
let groupsCache = { data: null, groups: [] };
function items() {
  if (groupsCache.data !== st.data) groupsCache = { data: st.data, groups: groupCoupons((st.data && st.data.items) || []) };
  return groupsCache.groups;
}
const byId = (id) => items().find((x) => x.id === id);
const couponById = (id) => ((st.data && st.data.items) || []).find((x) => x.id === id);

// ---------- 資料 ----------

async function readCache() {
  try {
    const res = await (await caches.open(DATA_CACHE)).match(CACHE_KEY);
    if (res) st.data = await res.json();
  } catch (e) { /* 沒有快取 */ }
}

async function fetchList() {
  const src = source();
  if (src && src.repo && src.token) {
    // 私人 repo：GitHub API 讀檔，權杖只要「Contents 唯讀」、只開這一個 repo
    const res = await fetch(`https://api.github.com/repos/${src.repo}/contents/coupons.json`, {
      headers: { Authorization: `Bearer ${src.token}`, Accept: 'application/vnd.github.raw+json' },
      cache: 'no-store',
    });
    if (res.status === 401) throw new Error('權杖失效，請重新貼上');
    if (res.status === 403) throw new Error('權杖沒有讀取權限（或 GitHub 暫時限制）');
    if (res.status === 404) throw new Error('找不到清單：請確認 repo 名稱，以及權杖有開這個 repo');
    if (!res.ok) throw new Error(`讀取失敗（${res.status}）`);
    return res;
  }
  // 沒設定權杖：只在本機預覽時讀得到（公開網站上沒有這個檔）
  const res = await fetch(CACHE_KEY, { cache: 'no-cache' });
  return res.ok ? res : null;
}

export async function refreshCoupons() {
  st.loading = true;
  rerender();
  try {
    const res = await fetchList();
    if (!res) {
      st.fetchError = st.data ? '尚未設定資料來源' : '';
    } else {
      const text = await res.text();
      const json = JSON.parse(text);
      if (!Array.isArray(json.items)) throw new Error('清單格式不對');
      st.data = json;
      st.fetchError = '';
      try { await (await caches.open(DATA_CACHE)).put(CACHE_KEY, new Response(text, { headers: { 'Content-Type': 'application/json' } })); } catch (e) { /* ignore */ }
    }
  } catch (e) {
    st.fetchError = e instanceof TypeError ? '連不上網路' : (e.message || '讀取失敗');
  }
  st.loading = false;
  rerender();
}

export async function initCoupons(onChange) {
  rerender = onChange;
  await readCache();
  rerender();
  await refreshCoupons();
}

// ---------- 畫面片段 ----------

const unk = '<span class="unk">未確認</span>';
const multiline = (s) => esc(s).replace(/\n/g, '<br>');
const EXT_ICON = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 4h6v6M20 4l-9 9M18 14v6H4V6h6"/></svg>';

// 品牌圖：只用 MATCHA 的圖片網址（瀏覽器看過會快取，不另外下載）；載不到時顯示店名第一個字
function logoHtml(it, cls = 'c-logo') {
  const name = known(it.store) || '?';
  const img = known(it.logo) ? `<img src="${esc(it.logo)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="this.remove()">` : '';
  return `<span class="${cls}" aria-hidden="true"><span class="ph">${esc([...name][0])}</span>${img}</span>`;
}

function expiryHtml(it, short = false) {
  const e = expiryState(it.validUntil);
  if (e.state === 'none') return short ? '<span class="muted">無期限</span>' : '無期限';
  if (e.state === 'unknown') return short ? '<span class="muted">期限未確認</span>' : unk;
  const d = slashDate(it.validUntil);
  if (e.state === 'expired') return `<span class="warn">${d}・已過期${short ? '' : '（等待下次更新）'}</span>`;
  if (e.state === 'soon') return `<span class="warn">${d}・剩 ${e.days} 天</span>`;
  return short ? `<span class="muted">${esc(d)} 到期</span>` : esc(d);
}

function starHtml(it, favs) {
  const on = favs.includes(it.id);
  return `<button type="button" class="c-star" data-fav="${esc(it.id)}" aria-pressed="${on}" aria-label="${on ? '從最愛移除' : '加入最愛'}">
    <svg width="22" height="22" viewBox="0 0 24 24" fill="${on ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" aria-hidden="true"><path d="M12 3.5l2.6 5.3 5.8.8-4.2 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.2-4.1 5.8-.8z"/></svg>
  </button>`;
}

// 列表的一列：品牌圖、店名、有效期限（其他資訊在詳細頁）
function rowHtml(it, favs, sortCtl = '') {
  const ex = expiryState(it.validUntil).state === 'expired';
  return `<div class="c-item${ex ? ' expired' : ''}">
    <button type="button" class="c-open" data-detail="${esc(it.id)}">
      ${logoHtml(it)}
      <span class="c-text"><span class="c-name">${esc(known(it.store) || it.id)}</span>
        <span class="c-exp">${expiryHtml(it, true)}${it.items && it.items.length > 1 ? `<span class="c-count">${it.items.length} 張券</span>` : ''}</span></span>
    </button>
    ${sortCtl || starHtml(it, favs)}
  </div>`;
}

function statusHtml() {
  const s = dataStatus(st.data, st.fetchError);
  const parts = [];
  if (s.hasData && s.failed) {
    parts.push(`<div class="notice">更新失敗，資料日期：${esc(s.date || '未知')}<br><small>${esc(s.reason)}</small></div>`);
  } else if (!s.hasData && st.fetchError) {
    parts.push(`<div class="notice">讀取失敗：${esc(st.fetchError)}</div>`);
  }
  if (s.stale) parts.push(`<div class="notice">優惠券資料已超過 90 天沒更新（資料日期 ${esc(s.date)}），請檢查自動更新是否正常，或到私人 repo 的 Actions 手動執行。</div>`);
  return parts.join('');
}

function settingsHtml(open) {
  const src = source() || {};
  return `<details class="card c-settings"${open ? ' open' : ''}>
    <summary>資料來源設定</summary>
    <p>優惠券清單放在私人 repo，不公開。在這裡貼上 GitHub 唯讀權杖（只開這個 repo 的 Contents 讀取），只會存在這支手機。</p>
    <form id="couponSource" class="c-form">
      <label>私人 repo<input name="repo" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="帳號/repo 名稱" value="${esc(src.repo || '')}"></label>
      <label>唯讀權杖<input name="token" type="password" autocomplete="off" placeholder="${src.token ? '已設定（要更換再貼上）' : 'github_pat_…'}"></label>
      <div class="c-actions"><button type="submit" class="c-btn primary">儲存並讀取</button>
        ${src.token ? '<button type="button" class="c-btn" data-clear-source>清除權杖</button>' : ''}</div>
    </form>
  </details>`;
}

function favsHtml(favs) {
  const list = resolveFavs(favs, items());
  if (!list.length) {
    return `<div class="card c-empty"><h2>還沒有最愛</h2>
      <p>到「全部」或各類別，點券右邊的 ☆ 加入最愛，就會列在這裡。</p>
      <button type="button" class="c-btn primary" data-view="全部">看全部優惠券</button></div>`;
  }
  const rows = list.map(({ id, item }, i) => {
    const ctl = st.sorting ? `<span class="c-sort">
        <button type="button" class="c-move" data-move="${esc(id)}" data-dir="-1" aria-label="上移"${i === 0 ? ' disabled' : ''}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 15l6-6 6 6"/></svg></button>
        <button type="button" class="c-move" data-move="${esc(id)}" data-dir="1" aria-label="下移"${i === list.length - 1 ? ' disabled' : ''}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg></button>
      </span>` : '';
    if (!item) {
      return `<div class="c-item gone"><span class="c-open"><span class="c-logo"><span class="ph">?</span></span>
        <span class="c-text"><span class="c-name">${esc(id)}</span><span class="c-exp muted">此券已下架</span></span></span>
        ${ctl || `<button type="button" class="c-star" data-fav="${esc(id)}" aria-pressed="true" aria-label="從最愛移除">✕</button>`}</div>`;
    }
    return rowHtml(item, favs, ctl);
  }).join('');
  return `<div class="c-list-head"><span>${list.length} 張・依你排的順序</span>
      <button type="button" class="c-link" data-sort>${st.sorting ? '完成' : '調整順序'}</button></div>
    <div class="c-list">${rows}</div>`;
}

function listHtml(favs) {
  const groups = groupByCategory(items()).filter((g) => st.view === '全部' || g.name === st.view);
  return groups.map((g) => `<section class="c-group"><h2 class="c-group-title">${esc(g.name)}<span class="n">${g.items.length} 張</span></h2>
    <div class="c-list">${g.items.map((it) => rowHtml(it, favs)).join('')}</div></section>`).join('');
}

// 券圖判讀（由 Claude 看券圖整理，可能有誤）
function imageInfoHtml(info) {
  if (!info) return '';
  const tiers = (info.tiers || []).map((t) => `<li><b>${esc(t.discount || '')}</b>${t.condition ? `・${esc(t.condition)}` : ''}${t.items ? `<br><span class="muted">${esc(t.items)}</span>` : ''}</li>`).join('');
  const rows = [
    tiers ? `<dt>折扣方式</dt><dd><ul class="c-tiers">${tiers}</ul></dd>` : '',
    info.excludes ? `<dt>不適用</dt><dd>${esc(info.excludes)}</dd>` : '',
    info.notes ? `<dt>其他規則</dt><dd>${esc(info.notes)}</dd>` : '',
  ].join('');
  if (!rows) return '';
  return `<div class="c-vision"><p class="c-vision-head">券圖重點<span>由 Claude 讀券圖整理，可能有誤，以券圖為準</span></p><dl class="c-fields">${rows}</dl></div>`;
}

function couponBlock(it) {
  const show = showTarget(it);
  const info = it.imageInfo || null;
  // 網頁沒寫期限、券圖上有寫：用券圖的，並標示來源
  const exp = known(it.validUntil) || !info || !info.validUntil ? expiryHtml(it)
    : `${esc(slashDate(info.validUntil))} <span class="muted">（券圖上的期限）</span>`;
  const terms = (it.terms || []).length ? `<div class="c-terms"><p class="c-terms-head">使用條件原文</p>
      <ul>${it.terms.map((t) => `<li>${esc(t)}</li>`).join('')}</ul></div>` : '';
  const site = it.embeddable
    ? `<button type="button" class="c-btn" data-embed="${esc(it.id)}">在 App 內開啟網站</button>
       <a class="c-btn" href="${esc(it.url)}" target="_blank" rel="noopener">在瀏覽器開啟網站 ${EXT_ICON}</a>`
    : `<a class="c-btn" href="${esc(it.url)}" target="_blank" rel="noopener">開啟網站（${esc(SOURCE_LABEL[it.source] || 'MATCHA')}） ${EXT_ICON}</a>`;
  return `<section class="card c-coupon">
    <div class="c-row"><span class="c-src">${esc(SOURCE_LABEL[it.source] || 'MATCHA')}</span>${it.store !== undefined ? `<span class="muted c-sub">${esc(known(it.store) || '')}</span>` : ''}</div>
    <div class="c-discount">${known(it.discount) ? esc(it.discount) : '折扣未確認'}</div>
    ${known(it.title) ? `<p class="c-title">${esc(it.title)}</p>` : ''}
    <div class="c-actions col">
      ${show ? `<a class="c-btn primary big" href="${esc(show.url)}" target="_blank" rel="noopener">${show.label} ${EXT_ICON}</a>`
        : '<p class="c-title">這張券沒有可以直接出示的券圖，請開啟網站出示。</p>'}
      ${site}
    </div>
    <dl class="c-fields">
      <dt>有效期限</dt><dd>${exp}</dd>
      <dt>門檻</dt><dd>${known(it.threshold) ? multiline(it.threshold) : unk}</dd>
      <dt>使用方式</dt><dd>${known(it.usage) ? multiline(it.usage) : unk}</dd>
    </dl>
    ${imageInfoHtml(info)}
    ${terms}
    <p class="c-foot">抓取日期 ${esc(slashDate(it.fetchedAt))}・券圖與條碼不存在 App 裡，需要網路才打得開。</p>
  </section>`;
}

function detailHtml(g, favs) {
  return `
    <div class="detail-top">
      <button type="button" class="icon-btn" data-detail-back aria-label="返回優惠券列表">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#15191E" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg>
      </button>
      <span>優惠券</span>
      <span class="spacer"></span>${starHtml(g, favs)}
    </div>
    <div class="detail c-detail">
      <div class="c-hero">${logoHtml(g, 'c-logo big')}
        <div><h2 class="c-store">${esc(known(g.store) || '店名未確認')}</h2><span class="c-cat">${esc(g.category)}</span>
        ${g.items.length > 1 ? `<span class="c-count">${g.items.length} 張券，來自不同網站</span>` : ''}</div></div>
      ${g.items.map(couponBlock).join('')}
    </div>`;
}

export function renderCouponsTab(container) {
  const favs = favIds();
  if (st.detail) {
    const it = byId(st.detail);
    if (it) { container.innerHTML = detailHtml(it, favs); return; }
    st.detail = null;
  }
  const s = dataStatus(st.data, st.fetchError);
  const counts = categoryCounts(items());
  const chips = ['最愛', '全部', ...CATEGORIES].map((c) => {
    const n = c === '最愛' ? resolveFavs(favs, items()).length : c === '全部' ? items().length : counts[c];
    const dis = c !== '最愛' && !n;
    return `<button type="button" class="chip" data-view="${esc(c)}" aria-pressed="${st.view === c}"${dis ? ' disabled' : ''}>${c === '最愛' ? '★ ' : ''}${esc(c)} <span class="n">${n}</span></button>`;
  }).join('');
  let body;
  if (!s.hasData) {
    body = st.loading ? '<p class="result-header">讀取中…</p>'
      : `<div class="card"><h2>還沒有優惠券清單</h2><p>請在下方「資料來源設定」貼上私人 repo 名稱與唯讀權杖。</p></div>${settingsHtml(true)}`;
  } else {
    body = (st.view === '最愛' ? favsHtml(favs) : listHtml(favs)) + settingsHtml(st.showSettings);
  }
  container.innerHTML = `
    <header class="c-top">
      <h1 class="title">優惠券</h1>
      <div class="c-meta">
        <span>${s.hasData ? `資料日期 ${esc(s.date)}・共 ${items().length} 張` : ''}</span>
        <button type="button" class="c-reload" data-reload${st.loading ? ' disabled' : ''}>${st.loading ? '讀取中…' : '重新載入'}</button>
      </div>
      ${s.hasData ? `<div class="chips c-chips">${chips}</div>` : ''}
    </header>
    <div class="stack">${statusHtml()}${body}</div>`;
}

// ---------- App 內嵌顯示（只有 embeddable 的券；MATCHA 目前全部不允許內嵌） ----------

let embedTimer = null;
function openEmbed(id) {
  const it = couponById(id);
  if (!it) return;
  st.embed = it;
  $('#embedTitle').textContent = known(it.store) || '優惠券';
  $('#embedOpen').href = it.url;
  $('#embedHint').hidden = true;
  const frame = document.createElement('iframe');
  frame.src = it.url;
  frame.title = '原券頁';
  frame.referrerPolicy = 'no-referrer';
  let loaded = false;
  frame.addEventListener('load', () => { loaded = true; });
  $('#embedFrame').replaceChildren(frame);
  $('#embed').hidden = false;
  history.pushState({ couponEmbed: true }, '');
  // 被網站擋住時 App 偵測不到（瀏覽器照樣觸發 load），所以一直顯示「在瀏覽器開啟」，久沒載入再提醒
  clearTimeout(embedTimer);
  embedTimer = setTimeout(() => { if (!loaded) $('#embedHint').hidden = false; }, EMBED_HINT_MS);
}

function closeEmbed() {
  if (!st.embed) return false;
  st.embed = null;
  clearTimeout(embedTimer);
  $('#embed').hidden = true;
  $('#embedFrame').replaceChildren();
  return true;
}

// 返回鍵：先關內嵌，再關券詳細頁。有處理就回傳 true
export function couponsBack() {
  if (closeEmbed()) return true;
  if (st.detail) { st.detail = null; rerender(); restoreScroll(); return true; }
  return false;
}

$('#embedBack').addEventListener('click', () => {
  if (history.state && history.state.couponEmbed) history.back();
  else closeEmbed();
});

let listScroll = 0;
function restoreScroll() { window.scrollTo(0, listScroll); }

// ---------- 事件（app.js 轉交過來；有處理就回傳 true） ----------

export function handleCouponClick(e) {
  const t = e.target;
  const fav = t.closest('[data-fav]');
  if (fav) { lsSet(LS_FAVS, toggleId(favIds(), fav.dataset.fav)); keepScroll(rerender); return true; }
  const mv = t.closest('[data-move]');
  if (mv) { lsSet(LS_FAVS, moveId(favIds(), mv.dataset.move, Number(mv.dataset.dir))); keepScroll(rerender); return true; }
  const det = t.closest('[data-detail]');
  if (det) {
    listScroll = window.scrollY;
    st.detail = det.dataset.detail;
    history.pushState({ couponDetail: true }, '');
    rerender();
    window.scrollTo(0, 0);
    return true;
  }
  if (t.closest('[data-detail-back]')) {
    if (history.state && history.state.couponDetail) history.back();
    else couponsBack();
    return true;
  }
  const emb = t.closest('[data-embed]');
  if (emb) { openEmbed(emb.dataset.embed); return true; }
  if (t.closest('[data-reload]')) { refreshCoupons(); return true; }
  if (t.closest('[data-sort]')) { st.sorting = !st.sorting; rerender(); return true; }
  const v = t.closest('[data-view]');
  if (v) { st.view = v.dataset.view; st.sorting = false; rerender(); window.scrollTo(0, 0); return true; }
  if (t.closest('[data-clear-source]')) {
    const src = source() || {};
    lsSet(LS_SOURCE, { repo: src.repo || '' });
    st.showSettings = true;
    rerender();
    return true;
  }
  return false;
}

function keepScroll(fn) {
  const y = window.scrollY;
  fn();
  window.scrollTo(0, y);
}

export function handleCouponSubmit(e) {
  if (e.target.id !== 'couponSource') return false;
  e.preventDefault();
  const f = new FormData(e.target);
  const old = source() || {};
  const repo = String(f.get('repo') || '').trim().replace(/^https?:\/\/github\.com\//, '').replace(/\/+$/, '');
  const token = String(f.get('token') || '').trim() || old.token || '';
  lsSet(LS_SOURCE, { repo, token });
  st.showSettings = false;
  refreshCoupons();
  return true;
}
