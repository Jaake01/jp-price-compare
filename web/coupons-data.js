// 優惠券分頁的純邏輯（不碰畫面，方便測試）。資料格式見 SPEC.md「優惠券」。

export const CATEGORIES = ['藥妝雜貨', '電器行', '百貨店', '運動/戶外用品', '其他'];
export const UNKNOWN = 'unknown';
export const UPDATE_DAYS = 90;   // 超過 90 天沒成功更新 → 提醒檢查
export const SOON_DAYS = 14;     // 14 天內到期 → 橘字提醒
const DAY = 24 * 60 * 60 * 1000;

// 頁面沒寫的欄位存 "unknown"：回傳 null，畫面顯示「未確認」
export const known = (v) => (v == null || v === '' || v === UNKNOWN ? null : v);

export function ymd(d) {
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export const slashDate = (s) => (s ? String(s).slice(0, 10).replace(/-/g, '/') : '');

// 有效期限狀態：unknown／expired／soon（14 天內）／ok；days = 還剩幾天（含當天）
export function expiryState(validUntil, today = new Date()) {
  const v = known(validUntil);
  if (!v || !/^\d{4}-\d{2}-\d{2}$/.test(v)) return { state: 'unknown', days: null };
  const t = ymd(today);
  const days = Math.round((Date.parse(v) - Date.parse(t)) / DAY);
  if (days < 0) return { state: 'expired', days };
  return { state: days <= SOON_DAYS ? 'soon' : 'ok', days };
}

// 依類別分組（順序固定），每組內已過期的排最後；空的類別不列
export function groupByCategory(items, today = new Date()) {
  const groups = CATEGORIES.map((name) => ({ name, items: [] }));
  const other = groups[groups.length - 1];
  for (const it of items || []) (groups.find((g) => g.name === it.category) || other).items.push(it);
  for (const g of groups) {
    g.items = g.items
      .map((it, i) => ({ it, i, ex: expiryState(it.validUntil, today).state === 'expired' }))
      .sort((a, b) => a.ex - b.ex || a.i - b.i)
      .map((x) => x.it);
  }
  return groups.filter((g) => g.items.length);
}

export function categoryCounts(items) {
  const n = Object.fromEntries(CATEGORIES.map((c) => [c, 0]));
  for (const it of items || []) n[CATEGORIES.includes(it.category) ? it.category : '其他'] += 1;
  return n;
}

// 資料狀態：資料日期、這次更新有沒有失敗、是不是太久沒更新
// fetchError：App 這次讀清單失敗（離線、權杖失效…）；data.lastRun.ok === false：伺服器端抓取失敗
export function dataStatus(data, fetchError, now = new Date()) {
  const updatedAt = data && data.updatedAt;
  const date = updatedAt ? slashDate(ymd(new Date(updatedAt))) : '';
  const runFailed = !!(data && data.lastRun && data.lastRun.ok === false);
  const failed = !!fetchError || runFailed;
  const reason = fetchError || (runFailed ? data.lastRun.error : '') || '';
  const stale = !!updatedAt && now.getTime() - new Date(updatedAt).getTime() > UPDATE_DAYS * DAY;
  return { date, failed, reason, stale, hasData: !!(data && Array.isArray(data.items)) };
}

// 最愛：照使用者排的順序；清單裡已沒有的券標成已下架
export function resolveFavs(ids, items) {
  const byId = new Map((items || []).map((it) => [it.id, it]));
  return (ids || []).map((id) => ({ id, item: byId.get(id) || null }));
}

export function toggleId(ids, id) {
  return ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id];
}

// 最愛排序：往上（-1）或往下（+1）移一格
export function moveId(ids, id, dir) {
  const i = ids.indexOf(id);
  const j = i + dir;
  if (i < 0 || j < 0 || j >= ids.length) return ids;
  const out = [...ids];
  [out[i], out[j]] = [out[j], out[i]];
  return out;
}

// 「出示券」要開什麼：店家自己的券頁（例如唐吉訶德，不能截圖使用）優先，其次是券圖（例如 Bic Camera、山田電機，圖上有條碼）
export function showTarget(it) {
  if (known(it.couponLink)) return { url: it.couponLink, label: '開啟店家券頁（給店員看）' };
  if (known(it.couponImage)) return { url: it.couponImage, label: '開啟券圖（給店員掃）' };
  return null;
}
