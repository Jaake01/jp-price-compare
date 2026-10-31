"""健康檢查。任一項不通過，該品牌就不覆蓋舊資料。規則見 SPEC.md。"""
MIN_PRICE, MAX_PRICE = 10, 200_000  # 宜得利沙發、床組可到 6 萬以上
MAX_DROP = 0.20        # 商品數比上次少超過 20%
MAX_MISSING = 0.05     # 超過 5% 缺品名、價格或連結
MAX_BAD_PRICE = 0.05   # 超過 5% 價格不合理
FX_RANGE = (0.15, 0.30)
FX_MAX_CHANGE = 0.05


def _bad_price(r):
    prices = [r["price"], r["maxPrice"]] + ([r["salePrice"]] if r["salePrice"] is not None else [])
    if any(not isinstance(p, int) or p < MIN_PRICE or p > MAX_PRICE for p in prices):
        return True
    return any(v["salePrice"] is not None and v["salePrice"] > v["price"] for v in r["variants"])


def check_products(records, prev_count):
    """回傳 (通過?, 失敗原因列表, 剔除價格不合理商品後的資料, 剔除的商品)。"""
    errors = []
    n = len(records)
    if n == 0:
        return False, ["商品數為 0"], records, []
    missing = [r for r in records if not r.get("name") or not r.get("price") or not r.get("url")]
    if len(missing) / n > MAX_MISSING:
        errors.append(f"{len(missing)}/{n} 筆商品缺品名、價格或連結（上限 5%）")
    bad = [r for r in records if _bad_price(r)]
    if len(bad) / n > MAX_BAD_PRICE:
        errors.append(f"{len(bad)}/{n} 筆商品價格不合理（上限 5%），例：" +
                      "、".join(f"{r['id']} {r['price']}/{r['salePrice']}" for r in bad[:5]))
    bad_ids = {id(r) for r in bad}
    kept = [r for r in records if id(r) not in bad_ids]
    if prev_count and len(kept) < prev_count * (1 - MAX_DROP):
        errors.append(f"商品數 {len(kept)} 比上次 {prev_count} 少超過 20%")
    return not errors, errors, kept, bad


def check_fx(fx, prev):
    errors = []
    rate = fx["rate"]
    if not FX_RANGE[0] <= rate <= FX_RANGE[1]:
        errors.append(f"匯率 {rate} 超出 {FX_RANGE[0]}–{FX_RANGE[1]} 的合理範圍")
    if prev and prev.get("rate"):
        change = abs(rate - prev["rate"]) / prev["rate"]
        if change > FX_MAX_CHANGE:
            errors.append(f"匯率單日變動 {change:.1%}（{prev['rate']} → {rate}），超過 5%")
    return not errors, errors


JPY_RANGE = (10, 2_000_000)


def check_jp(records, prev_count):
    """日本官網價格：{編號: {name, url, variants}}。剔除價格不合理的顏色，規則同台灣資料。"""
    n = len(records)
    if n == 0:
        return False, ["商品數為 0"], records
    bad = [k for k, r in records.items()
           if not r["variants"] or any(not JPY_RANGE[0] <= v["price"] <= JPY_RANGE[1] for v in r["variants"])]
    errors = []
    if len(bad) / n > MAX_BAD_PRICE:
        errors.append(f"{len(bad)}/{n} 筆日本官網價格不合理（上限 5%），例：{'、'.join(bad[:5])}")
    kept = {k: r for k, r in records.items() if k not in set(bad)}
    if prev_count and len(kept) < prev_count * (1 - MAX_DROP):
        errors.append(f"商品數 {len(kept)} 比上次 {prev_count} 少超過 20%")
    return not errors, errors, kept
