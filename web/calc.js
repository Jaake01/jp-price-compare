// 價格計算（SPEC「價格計算」「退稅規則」）。純函式，方便測試。

export const REFUND_MIN_EX_TAX = 5000; // 同店同日未稅滿 ¥5,000

export function calc(jpyInclTax, taxRatePct, rate, twPrice) {
  const exTax = Math.round(jpyInclTax / (1 + taxRatePct / 100));
  const pay = jpyInclTax * rate;     // 刷卡當下台幣
  const refund = exTax * rate;       // 退稅後台幣
  const diff = twPrice - refund;     // 正數 = 日本比較便宜
  const pct = twPrice ? Math.round((Math.abs(diff) / twPrice) * 100) : 0;
  return {
    exTax,
    pay: Math.round(pay),
    refund: Math.round(refund),
    diff: Math.round(diff),
    pct,
    cheaper: diff >= 0,
    meetsThreshold: exTax >= REFUND_MIN_EX_TAX,
    thresholdInclTax: taxRatePct === 10 ? 5500 : 5400,
  };
}

export function fmtTwd(n) {
  return 'NT$' + Math.round(n).toLocaleString('en-US');
}

export function parseJpy(str) {
  const s = String(str).normalize('NFKC').replace(/[^\d]/g, '');
  return s ? parseInt(s, 10) : 0;
}
