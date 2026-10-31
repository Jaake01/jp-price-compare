"""日本官網價格（給商品頁顯示「日本官網價」）。詳見 docs/recon-3.md。

UNIQLO、GU 日本官網用 Fast Retailing 共用的 commerce API，path=,, 一次列出全站商品。
同一個商品編號的特價顏色會拆成另一筆（priceGroup 不同），和台灣官網一樣要合併。
價格是含稅日圓；有 promo 代表特價中（API 不提供特價前的價格）。
宜得利見下方（分類頁輪流抓）。MUJI 日本擋雲端連線，抓不到。
"""
import json
import re
from datetime import date, timedelta

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


# ---------- 宜得利日本官網 ----------
# 分類頁 HTML 內嵌商品 JSON（每頁 60 筆，含代表 SKU、價格、價格區間），但每頁要約 10 秒，
# 全站約 550 頁。所以每天只輪流抓一部分分類頁，結果存快取，約一週輪完一次。
NITORI = "https://www.nitori-net.jp"
NITORI_SITEMAP = NITORI + "/ecstatic/sitemap/sitemap_item_1.xml"
_NITORI_CAT_RE = re.compile(r"<loc>https://www\.nitori-net\.jp/ec/cat/([A-Za-z]+)/1/</loc>")
_NITORI_CODE_RE = re.compile(r"^(\d{7}|\d{13})s$")  # 組合商品（A-Bs）略過
NITORI_KEEP_DAYS = 21  # 超過這麼久沒在分類頁看到就移除


def nitori_categories():
    xml = http.request(NITORI_SITEMAP).decode("utf-8")
    return sorted(set(_NITORI_CAT_RE.findall(xml)))


def _json_array_after(html, key, start):
    i = html.find(key, start)
    if i < 0:
        raise http.FetchError(f"宜得利日本分類頁找不到 {key}")
    j = html.index("[", i)
    depth = 0
    for n in range(j, len(html)):
        if html[n] == "[":
            depth += 1
        elif html[n] == "]":
            depth -= 1
            if depth == 0:
                return json.loads(html[j:n + 1])
    raise http.FetchError("宜得利日本分類頁 JSON 不完整")


def parse_nitori_page(html):
    """分類頁 HTML → (總頁數, 商品列表)。"""
    i = html.find('"pagination":{"currentPage"')
    if i < 0:
        raise http.FetchError("宜得利日本分類頁找不到 pagination")
    pg = json.loads(html[html.index("{", i + 12):html.index("}", i) + 1])
    return pg["totalPages"], _json_array_after(html, '"products":', i)


def _value(p, *path):
    for k in path:
        p = (p or {}).get(k)
    return p if isinstance(p, (int, float)) else None


def update_nitori_cache(cache, max_pages, today=None):
    """從上次停下的分類頁接著抓 max_pages 頁。回傳 (快取, 這次抓了幾頁)。"""
    today = today or date.today().isoformat()
    items = cache.setdefault("items", {})
    cur = cache.setdefault("cursor", {"cat": "", "page": 1})
    cats = nitori_categories()
    if not cats:
        raise http.FetchError("宜得利日本 sitemap 沒有分類")
    ci = cats.index(cur["cat"]) if cur["cat"] in cats else 0
    page, done = cur["page"] if cur["cat"] in cats else 1, 0
    while done < max_pages:
        try:
            html = http.request(f"{NITORI}/ec/cat/{cats[ci]}/{page}/").decode("utf-8")
            total_pages, products = parse_nitori_page(html)
        except http.FetchError:
            if not done:
                raise
            break  # 已抓到的先保留，下次從這頁接著抓
        done += 1
        for p in products:
            m = _NITORI_CODE_RE.match(p.get("code") or "")
            price = _value(p, "price", "value")
            if not m or price is None:
                continue
            items[m.group(1)] = {
                "name": p.get("name") or "", "url": NITORI + (p.get("url") or ""),
                "price": int(price),
                "min": int(_value(p, "priceRange", "minPrice", "value") or price),
                "max": int(_value(p, "priceRange", "maxPrice", "value") or price),
                "checked": today,
            }
        if page >= total_pages:
            ci, page = (ci + 1) % len(cats), 1
        else:
            page += 1
    cache["cursor"] = {"cat": cats[ci], "page": page}
    cutoff = (date.fromisoformat(today) - timedelta(days=NITORI_KEEP_DAYS)).isoformat()
    cache["items"] = {k: v for k, v in items.items() if v["checked"] >= cutoff}
    return cache, done


def transform_nitori(cache):
    """快取 → 和 UNIQLO、GU 相同的日本價格格式，另加價格區間與確認日期。"""
    out = {}
    for code, c in (cache.get("items") or {}).items():
        out[code] = {"name": c["name"], "url": c["url"],
                     "variants": [{"color": "", "price": c["price"], "sale": False}],
                     "min": c["min"], "max": c["max"], "checkedAt": c["checked"]}
    return out
