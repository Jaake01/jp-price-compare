"""日本官網價格（給商品頁顯示「日本官網價」）。詳見 docs/recon-3.md。

UNIQLO、GU 日本官網用 Fast Retailing 共用的 commerce API，path=,, 一次列出全站商品。
同一個商品編號的特價顏色會拆成另一筆（priceGroup 不同），和台灣官網一樣要合併。
價格是含稅日圓；有 promo 代表特價中（API 不提供特價前的價格）。
"""
from . import http

SITES = {
    "UQ": "https://www.uniqlo.com/jp",
    "GU": "https://www.gu-global.com/jp",
}
PAGE_SIZE = 100


def fetch_fr(brand, max_pages=None):
    """抓日本官網全站商品列表（原始資料）。回傳 (商品列表, 官網說的總數)。"""
    api = SITES[brand] + "/api/commerce/v5/ja/products"
    items, offset, page = [], 0, 0
    while True:
        d = http.get_json(api, params={"path": ",,", "limit": PAGE_SIZE, "offset": offset},
                          headers={"Accept": "application/json", "Accept-Language": "ja"})
        if d.get("status") != "ok":
            raise http.FetchError(f"{brand} 日本官網 API 回傳失敗：{d.get('error') or d.get('status')}")
        result = d["result"]
        batch = result.get("items") or []
        items += batch
        offset += len(batch)
        page += 1
        total = result["pagination"]["total"]
        if not batch or offset >= total or (max_pages and page >= max_pages):
            return items, total


def transform_fr(brand, items):
    """原始列表 → {商品編號: {name, url, variants: [{color, price, sale}]}}。"""
    base = SITES[brand] + "/ja/products/"
    out = {}
    for it in items:
        code = it["productId"].split("-")[0][1:]  # E475367-000 → 475367
        prices = it.get("prices") or {}
        promo = prices.get("promo")
        price = (promo or prices.get("base") or {}).get("value")
        if not isinstance(price, (int, float)):
            continue
        rec = out.setdefault(code, {"name": it.get("name") or "", "url": "", "variants": []})
        url = f"{base}{it['productId']}/{it.get('priceGroup') or '00'}"
        # 原價那一筆當商品連結（特價顏色另外一筆）
        if not rec["url"] or not promo:
            rec["url"] = url
        for c in it.get("colors") or [{"displayCode": "", "name": ""}]:
            rec["variants"].append({
                "color": f"{c.get('displayCode', '')} {c.get('name', '')}".strip(),
                "price": int(price),
                "sale": bool(promo),
            })
    return out


def jp_file(brand, records):
    return {"brand": brand, "count": len(records), "items": records}
