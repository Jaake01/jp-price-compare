import { test } from 'node:test';
import assert from 'node:assert/strict';
import { calc, fmtTwd, parseJpy } from '../calc.js';

test('SPEC 驗收：¥5,990、匯率 0.205 → 刷卡 NT$1,228、退稅後 NT$1,116', () => {
  const c = calc(5990, 10, 0.205, 1490);
  assert.equal(fmtTwd(c.pay), 'NT$1,228');
  assert.equal(fmtTwd(c.refund), 'NT$1,116');
  assert.equal(c.exTax, 5445);
  assert.equal(c.meetsThreshold, true);
});

test('價差與百分比以台灣售價為分母', () => {
  const c = calc(5990, 10, 0.205, 1490);
  assert.equal(c.cheaper, true);
  assert.equal(c.diff, 374); // 1490 - 1116.2
  assert.equal(c.pct, 25);
  const d = calc(5990, 10, 0.205, 990);
  assert.equal(d.cheaper, false);
  assert.equal(d.diff, -126);
});

test('門檻：未稅未滿 ¥5,000；8% 時含稅門檻為 ¥5,400', () => {
  assert.equal(calc(3990, 10, 0.2, 590).meetsThreshold, false);
  assert.equal(calc(3990, 10, 0.2, 590).thresholdInclTax, 5500);
  assert.equal(calc(3990, 8, 0.2, 590).thresholdInclTax, 5400);
  assert.equal(calc(5400, 8, 0.2, 590).meetsThreshold, true);
});

test('日幣輸入：全形與逗號', () => {
  assert.equal(parseJpy('３，９９０'), 3990);
  assert.equal(parseJpy('¥5,990'), 5990);
  assert.equal(parseJpy(''), 0);
});
