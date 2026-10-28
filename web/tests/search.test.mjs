import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildIndex, search, normalize, defaultVariant, hasPriceSpread } from '../search.js';

const rec = (brand, id, name, extra = {}) => ({ brand, id, name, altIds: [], price: 590, salePrice: null,
  maxPrice: 590, category: 'T恤', variants: [{ color: 'A', price: 590, salePrice: null, ids: [id] }], ...extra });

const idx = buildIndex({
  UQ: { items: [
    rec('UQ', '470001', '撥水連帽外套'),
    rec('UQ', '483457', 'AIRism棉質T恤(短袖)', { altIds: ['474405'], salePrice: 190, variants: [
      { color: '00 WHITE', price: 390, salePrice: null, ids: ['483457'] },
      { color: '09 BLACK', price: 390, salePrice: null, ids: ['474405'] },
      { color: '10 PINK', price: 390, salePrice: 190, ids: ['483457'] }] }),
    rec('UQ', '455072', '某商品'),
  ] },
  GU: { items: [rec('GU', '470001', '輕量防風外套'), rec('GU', '352118', '短版鋪棉外套', { category: '外套' })] },
  MUJI: { items: [rec('MUJI', '4550723297400', '女棉保暖T恤', { altIds: ['4550723297417'], category: '保暖內衣' })] },
});

test('normalize：全形轉半形、去空白與連字號', () => {
  assert.equal(normalize('４８３ ４５７'), '483457');
  assert.equal(normalize('483-457'), '483457');
  assert.equal(normalize('AIRism 棉質'), 'airism棉質');
});

test('編號完全吻合 1 件 → 直接打開', () => {
  const r = search(idx, '352118');
  assert.equal(r.mode, 'exact');
  assert.equal(r.jump.entry.rec.name, '短版鋪棉外套');
});

test('編號在兩個品牌都有 → 列出全部並提示', () => {
  const r = search(idx, '470001', 'MUJI'); // 數字不受品牌按鈕影響
  assert.equal(r.items.length, 2);
  assert.equal(r.ambiguous, true);
  assert.equal(r.jump, null);
});

test('顏色編號（altIds）也查得到，並預設選那個顏色', () => {
  const r = search(idx, '474405');
  assert.equal(r.jump.entry.rec.id, '483457');
  assert.equal(defaultVariant(r.jump.entry.rec, r.jump.matchedId).color, '09 BLACK');
});

test('MUJI 其他尺寸 JAN', () => {
  assert.equal(search(idx, '4550723297417').jump.entry.rec.id, '4550723297400');
});

test('還有更長的編號以它開頭時不自動跳轉（打 JAN 打到一半）', () => {
  const r = search(idx, '455072');
  assert.equal(r.mode, 'exact');
  assert.equal(r.jump, null);
});

test('開頭相符，邊打邊縮小', () => {
  const r = search(idx, '4700');
  assert.equal(r.mode, 'prefix');
  assert.equal(r.items.length, 2);
  assert.equal(search(idx, '9999').items.length, 0);
});

test('文字：品名開頭 > 品名包含 > 分類包含，並依品牌篩選', () => {
  const r = search(idx, '外套');
  assert.deepEqual(r.items.map((i) => i.entry.rec.name), ['撥水連帽外套', '輕量防風外套', '短版鋪棉外套']);
  assert.deepEqual(search(idx, '外套', 'GU').items.map((i) => i.entry.rec.id), ['470001', '352118']);
  assert.equal(search(idx, '短版').items[0].entry.rec.name, '短版鋪棉外套'); // 開頭吻合排第一
  assert.equal(search(idx, 'airism').items.length, 1);
});

test('沒有指定顏色時預設多數顏色的價格；判斷是否有價格差異', () => {
  const r = idx.byId.get('483457')[0].rec;
  assert.equal(defaultVariant(r, null).color, '00 WHITE');
  assert.equal(hasPriceSpread(r), true);
  assert.equal(hasPriceSpread(idx.byId.get('352118')[0].rec), false);
});

import { applyFilters, filtersActive, DEFAULT_FILTERS, typicalVariant, priceSummary } from '../search.js';

test('代表價格：少數出清色不拉低整件商品', () => {
  const v = (color, price, salePrice = null) => ({ color, price, salePrice });
  // 4 色 790、1 色出清 390 → 顯示 790，補充「部分顏色特價 390 起」
  const polo = { price: 790, salePrice: 390, variants: [v('00', 790), v('02', 790), v('08', 790), v('09', 790), v('57', 790, 390)] };
  assert.equal(typicalVariant(polo).color, '00');
  assert.deepEqual(priceSummary(polo), { now: 790, price: 790, sale: false, low: 390, high: null, lowSale: true });
  // 多數顏色特價 → 顯示特價與原價
  const sale = { price: 1990, salePrice: 1490, variants: [v('01', 1990, 1490), v('09', 1990, 1490), v('18', 1990)] };
  assert.deepEqual(priceSummary(sale), { now: 1490, price: 1990, sale: true, low: null, high: 1990, lowSale: false });
  // 同樣多時取較高價
  assert.equal(nowOf(typicalVariant({ variants: [v('a', 790), v('b', 790, 390), v('c', 790), v('d', 790, 390)] })), 790);
  // 沒有各色資料
  assert.deepEqual(priceSummary({ price: 590, salePrice: 390 }), { now: 390, price: 590, sale: true, low: null, high: null, lowSale: false });
  // 排序用代表價格；只看特價仍包含部分顏色特價
  const items = [polo, { price: 500, salePrice: null }].map((rec, i) => ({ entry: { rec: { ...rec, id: String(i) } }, matchedId: null }));
  assert.deepEqual(applyFilters(items, { ...DEFAULT_FILTERS, sort: 'price_asc' }).map((x) => x.entry.rec.id), ['1', '0']);
  assert.deepEqual(applyFilters(items, { ...DEFAULT_FILTERS, saleOnly: true }).map((x) => x.entry.rec.id), ['0']);
});
const nowOf = (v) => (v.salePrice != null ? v.salePrice : v.price);

test('篩選對象、只看特價、排序', () => {
  const mk = (id, price, salePrice, audience) => ({ entry: { rec: { id, price, salePrice, audience } }, matchedId: null });
  const items = [mk('a', 990, null, ['女', '男']), mk('b', 590, 390, ['女']), mk('c', 1290, 990, ['男']), mk('d', 290, null, [])];
  const ids = (xs) => xs.map((x) => x.entry.rec.id);
  assert.deepEqual(ids(applyFilters(items, DEFAULT_FILTERS)), ['a', 'b', 'c', 'd']);
  assert.deepEqual(ids(applyFilters(items, { ...DEFAULT_FILTERS, audience: '女' })), ['a', 'b']);
  assert.deepEqual(ids(applyFilters(items, { ...DEFAULT_FILTERS, audience: '男' })), ['a', 'c']);
  assert.deepEqual(ids(applyFilters(items, { ...DEFAULT_FILTERS, saleOnly: true })), ['b', 'c']);
  assert.deepEqual(ids(applyFilters(items, { ...DEFAULT_FILTERS, sort: 'price_asc' })), ['d', 'b', 'a', 'c']); // 特價用特價比
  assert.deepEqual(ids(applyFilters(items, { ...DEFAULT_FILTERS, sort: 'price_desc' })), ['a', 'c', 'b', 'd']); // a、c 同為 990，保留相關度順序
  assert.deepEqual(ids(applyFilters(items, { ...DEFAULT_FILTERS, sort: 'discount' })), ['b', 'c', 'a', 'd']); // 34% > 23%
  assert.equal(filtersActive(DEFAULT_FILTERS), false);
  assert.equal(filtersActive({ ...DEFAULT_FILTERS, saleOnly: true }), true);
  assert.equal(applyFilters(items, DEFAULT_FILTERS), items); // 沒篩選時不複製
});
