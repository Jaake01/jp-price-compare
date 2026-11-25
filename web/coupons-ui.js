// 優惠券分頁：讀清單（私人 repo，用唯讀權杖）、依類別列出、開原券頁、主頁快選。
// 券圖與條碼不下載，一律在 MATCHA 原頁（或店家券頁）顯示，所以要有網路才打得開。
import {
  CATEGORIES, known, slashDate, expiryState, groupByCategory, categoryCounts, dataStatus,
  resolveQuick, toggleId, couponLinkLabel,
} from './coupons-data.js';

const DATA_CACHE = 'data-v1';
const CACHE_KEY = 'data/coupons.json';         // 快取裡的位置（同一個網址，不管資料從哪裡讀）
const LS_SOURCE = 'coupons.source';            // { repo, token }：只存在這支手機
const LS_QUICK = 'coupons.quick';              // 主頁快選的券 id
const EMBED_HINT_MS = 8000;

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const $ = (s) => document.querySelector(s);

const st = {
  data: null,
  fetchError: '',
  loading: false,
  needsSetup: false,  // 還沒設定資料來源，也沒有本機資料
  cat: '全部',
  editingQuick: false,
  showSettings: false,
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
export const quickIds = () => lsGet(LS_QUICK, []);

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
  if (!res.ok) return null;
  return res;
}

export async function refreshCoupons() {
  st.loading = true;
  rerender();
  try {
    const res = await fetchList();
    if (!res) {
      st.needsSetup = !st.data;
      st.fetchError = st.data ? '尚未設定資料來源' : '';
    } else {
      const text = await res.text();
      const json = JSON.parse(text);
      if (!Array.isArray(json.items)) throw new Error('清單格式不對');
      st.data = json;
      st.fetchError = '';
      st.needsSetup = false;
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

function expiryHtml(it) {
  const e = expiryState(it.validUntil);
  if (e.state === 'unknown') return unk;
  const d = slashDate(it.validUntil);
  if (e.state === 'expired') return `<span class="warn">${d}・已過期（等待下次更新）</span>`;
  if (e.state === 'soon') return `<span class="warn">${d}・剩 ${e.days} 天</span>`;
  return esc(d);
}

function openButtons(it) {
  const link = known(it.couponLink);
  const main = it.embeddable
    ? `<button type="button" class="c-btn primary" data-embed="${esc(it.id)}">在 App 內查看</button>
       <a class="c-btn" href="${esc(it.url)}" target="_blank" rel="noopener">在瀏覽器開啟</a>`
    : `<a class="c-btn primary" href="${esc(it.url)}" target="_blank" rel="noopener">在瀏覽器開啟原券頁</a>`;
  const extra = link ? `<a class="c-btn" href="${esc(link)}" target="_blank" rel="noopener">${couponLinkLabel(link)}</a>` : '';
  return main + extra;
}

function couponCard(it) {
  const ex = expiryState(it.validUntil).state === 'expired';
  const terms = (it.terms || []).length
    ? `<details class="c-terms"><summary>使用條件原文（${it.terms.length} 條）</summary>
        <ul>${it.terms.map((t) => `<li>${esc(t)}</li>`).join('')}</ul></details>` : '';
  const discount = known(it.discount);
  return `<article class="coupon${ex ? ' expired' : ''}" id="c-${esc(it.id)}">
    <div class="c-head"><h3 class="c-store">${esc(known(it.store) || '店名未確認')}</h3><span class="c-cat">${esc(it.category)}</span></div>
    <div class="c-discount">${discount ? esc(discount) : '折扣未確認'}</div>
    ${known(it.title) ? `<p class="c-title">${esc(it.title)}</p>` : ''}
    <dl class="c-fields">
      <dt>門檻</dt><dd>${known(it.threshold) ? multiline(it.threshold) : unk}</dd>
      <dt>使用方式</dt><dd>${known(it.usage) ? multiline(it.usage) : unk}</dd>
      <dt>有效期限</dt><dd>${expiryHtml(it)}</dd>
    </dl>
    ${terms}
    <div class="c-actions">${openButtons(it)}</div>
    <p class="c-foot">抓取日期 ${esc(slashDate(it.fetchedAt))}・來源 MATCHA・券圖與條碼請在原頁出示</p>
  </article>`;
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

function quickEditorHtml(items) {
  const ids = quickIds();
  const groups = groupByCategory(items);
  return `<div class="card c-quick-edit">
    <div class="c-row"><h2>主頁快選</h2><button type="button" class="c-btn primary" data-quick-done>完成</button></div>
    <p>勾選的券會顯示在「比價」首頁，點一下就打開。</p>
    ${groups.map((g) => `<fieldset><legend>${esc(g.name)}</legend>
      ${g.items.map((it) => `<label class="c-check"><input type="checkbox" data-quick="${esc(it.id)}"${ids.includes(it.id) ? ' checked' : ''}>
        <span>${esc(known(it.store) || it.id)}</span><span class="d">${esc(known(it.discount) || '')}</span></label>`).join('')}
    </fieldset>`).join('')}
  </div>`;
}

export function renderCouponsTab(container) {
  const items = (st.data && st.data.items) || [];
  const s = dataStatus(st.data, st.fetchError);
  const counts = categoryCounts(items);
  const chips = ['全部', ...CATEGORIES].map((c) => {
    const n = c === '全部' ? items.length : counts[c];
    return `<button type="button" class="chip" data-ccat="${esc(c)}" aria-pressed="${st.cat === c}"${n ? '' : ' disabled'}>${esc(c)} <span class="n">${n}</span></button>`;
  }).join('');
  const groups = groupByCategory(items).filter((g) => st.cat === '全部' || g.name === st.cat);
  const list = groups.map((g) => `<section class="c-group"><h2 class="c-group-title">${esc(g.name)}<span class="n">${g.items.length} 張</span></h2>
    ${g.items.map(couponCard).join('')}</section>`).join('');
  const quickCount = resolveQuick(quickIds(), items).length;
  let body;
  if (!s.hasData) {
    body = st.loading ? '<p class="result-header">讀取中…</p>'
      : `<div class="card"><h2>還沒有優惠券清單</h2><p>請在下方「資料來源設定」貼上私人 repo 名稱與唯讀權杖。</p></div>${settingsHtml(true)}`;
  } else if (st.editingQuick) {
    body = quickEditorHtml(items);
  } else {
    body = `<div class="c-toolbar"><button type="button" class="c-btn" data-quick-edit>編輯主頁快選（${quickCount}）</button></div>
      ${list}${settingsHtml(st.showSettings)}`;
  }
  container.innerHTML = `
    <header class="c-top">
      <h1 class="title">優惠券</h1>
      <div class="c-meta">
        <span>${s.hasData ? `資料日期 ${esc(s.date)}・${items.length} 張` : ''}</span>
        <button type="button" class="c-reload" data-reload${st.loading ? ' disabled' : ''}>${st.loading ? '讀取中…' : '重新載入'}</button>
      </div>
      ${s.hasData && !st.editingQuick ? `<div class="chips">${chips}</div>` : ''}
    </header>
    <div class="stack">${statusHtml()}${body}</div>`;
}

// 比價首頁的快選卡
export function quickCardHtml() {
  const items = (st.data && st.data.items) || [];
  const q = resolveQuick(quickIds(), items);
  if (!q.length) {
    return `<div class="card quick-card"><div class="c-row"><h2>優惠券快選</h2><button type="button" class="c-link" data-goto-coupons>去勾選</button></div>
      <p>在「優惠券」分頁勾選常用的券，會顯示在這裡。</p></div>`;
  }
  const rows = q.map(({ id, item }) => {
    if (!item) return `<div class="quick-row gone"><span>${esc(id)}</span><span class="d">此券已下架</span></div>`;
    const e = expiryState(item.validUntil);
    const warn = e.state === 'expired' ? '已過期' : e.state === 'soon' ? `剩 ${e.days} 天` : '';
    const inner = `<span class="s">${esc(known(item.store) || id)}</span><span class="d">${esc(known(item.discount) || '')}</span>${warn ? `<span class="warn">${warn}</span>` : ''}
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 4h6v6M20 4l-9 9M18 14v6H4V6h6"/></svg>`;
    return item.embeddable
      ? `<button type="button" class="quick-row" data-embed="${esc(id)}">${inner}</button>`
      : `<a class="quick-row" href="${esc(item.url)}" target="_blank" rel="noopener">${inner}</a>`;
  }).join('');
  return `<div class="card quick-card"><div class="c-row"><h2>優惠券快選</h2><button type="button" class="c-link" data-goto-coupons data-edit>修改</button></div>${rows}</div>`;
}

// ---------- App 內嵌顯示（只有 embeddable 的券；MATCHA 目前全部不允許內嵌） ----------

let embedTimer = null;
function openEmbed(id) {
  const it = ((st.data && st.data.items) || []).find((x) => x.id === id);
  if (!it) return;
  st.embed = it;
  const box = $('#embed');
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
  box.hidden = false;
  history.pushState({ couponEmbed: true }, '');
  // 被網站擋住時 App 偵測不到（瀏覽器照樣觸發 load），所以一直顯示「在瀏覽器開啟」，久沒載入再提醒
  clearTimeout(embedTimer);
  embedTimer = setTimeout(() => { if (!loaded) $('#embedHint').hidden = false; }, EMBED_HINT_MS);
}

export function closeEmbed() {
  if (!st.embed) return false;
  st.embed = null;
  clearTimeout(embedTimer);
  $('#embed').hidden = true;
  $('#embedFrame').replaceChildren();
  return true;
}

$('#embedBack').addEventListener('click', () => {
  if (history.state && history.state.couponEmbed) history.back();
  else closeEmbed();
});

// ---------- 事件（app.js 轉交過來；有處理就回傳 true） ----------

export function handleCouponClick(e, { gotoCoupons }) {
  const t = e.target;
  const emb = t.closest('[data-embed]');
  if (emb) { openEmbed(emb.dataset.embed); return true; }
  if (t.closest('[data-goto-coupons]')) {
    st.editingQuick = !!t.closest('[data-edit]') || !quickIds().length;
    gotoCoupons();
    return true;
  }
  if (t.closest('[data-reload]')) { refreshCoupons(); return true; }
  const chip = t.closest('[data-ccat]');
  if (chip) { st.cat = chip.dataset.ccat; rerender(); return true; }
  if (t.closest('[data-quick-edit]')) { st.editingQuick = true; rerender(); window.scrollTo(0, 0); return true; }
  if (t.closest('[data-quick-done]')) { st.editingQuick = false; rerender(); return true; }
  if (t.closest('[data-clear-source]')) {
    const src = source() || {};
    lsSet(LS_SOURCE, { repo: src.repo || '' });
    st.showSettings = true;
    rerender();
    return true;
  }
  return false;
}

export function handleCouponChange(e) {
  const box = e.target.closest('[data-quick]');
  if (!box) return false;
  lsSet(LS_QUICK, toggleId(quickIds(), box.dataset.quick));
  return true; // 勾選框自己會更新，不用重畫
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
