import { test } from 'node:test';
import assert from 'node:assert/strict';
import { known, expiryState, groupByCategory, categoryCounts, dataStatus, resolveFavs, toggleId, moveId, showTarget } from '../coupons-data.js';

const today = new Date(2026, 10, 25); // 2026/11/25

test('unknown 顯示為未確認', () => {
  assert.equal(known('unknown'), null);
  assert.equal(known(''), null);
  assert.equal(known('5%'), '5%');
});

test('有效期限狀態', () => {
  assert.deepEqual(expiryState('2026-11-24', today), { state: 'expired', days: -1 });
  assert.deepEqual(expiryState('2026-11-25', today), { state: 'soon', days: 0 });
  assert.equal(expiryState('2026-12-09', today).state, 'soon');
  assert.equal(expiryState('2026-12-31', today).state, 'ok');
  assert.equal(expiryState('unknown', today).state, 'unknown');
});

test('依類別分組，過期的排最後，未知類別歸其他', () => {
  const items = [
    { id: 'a', category: '電器行', validUntil: '2026-01-01' },
    { id: 'b', category: '電器行', validUntil: '2027-01-01' },
    { id: 'c', category: '藥妝雜貨', validUntil: 'unknown' },
    { id: 'd', category: '奇怪的類別', validUntil: 'unknown' },
  ];
  const g = groupByCategory(items, today);
  assert.deepEqual(g.map((x) => x.name), ['藥妝雜貨', '電器行', '其他']);
  assert.deepEqual(g[1].items.map((x) => x.id), ['b', 'a']);
  assert.equal(categoryCounts(items)['其他'], 1);
});

test('資料狀態：失敗、超過 90 天', () => {
  const ok = { updatedAt: '2026-11-20T00:00:00Z', lastRun: { ok: true }, items: [] };
  assert.equal(dataStatus(ok, '', today).failed, false);
  assert.equal(dataStatus(ok, '', today).stale, false);
  assert.equal(dataStatus(ok, '連不上網路', today).failed, true);
  const run = dataStatus({ ...ok, lastRun: { ok: false, error: '網站改版' } }, '', today);
  assert.equal(run.failed, true);
  assert.equal(run.reason, '網站改版');
  assert.equal(dataStatus({ ...ok, updatedAt: '2026-08-01T00:00:00Z' }, '', today).stale, true);
  assert.equal(dataStatus(null, '', today).hasData, false);
});

test('最愛：順序、下架、排序', () => {
  const q = resolveFavs(['b', 'gone'], [{ id: 'a' }, { id: 'b' }]);
  assert.deepEqual(q.map((x) => [x.id, !!x.item]), [['b', true], ['gone', false]]);
  assert.deepEqual(toggleId(['a'], 'b'), ['a', 'b']);
  assert.deepEqual(toggleId(['a', 'b'], 'a'), ['b']);
  assert.deepEqual(moveId(['a', 'b', 'c'], 'c', -1), ['a', 'c', 'b']);
  assert.deepEqual(moveId(['a', 'b', 'c'], 'a', -1), ['a', 'b', 'c']);
  assert.deepEqual(moveId(['a', 'b', 'c'], 'a', 1), ['b', 'a', 'c']);
});

test('出示券：店家券頁優先，其次券圖', () => {
  assert.equal(showTarget({ couponLink: 'https://donki/x', couponImage: 'https://img/a.jpg' }).url, 'https://donki/x');
  assert.match(showTarget({ couponLink: null, couponImage: 'https://img/a.webp' }).label, /券圖/);
  assert.equal(showTarget({ couponLink: 'unknown', couponImage: null }), null);
});
