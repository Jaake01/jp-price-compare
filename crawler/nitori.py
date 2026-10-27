"""宜得利 NITORI 台灣（www.nitori-net.tw）。詳見 docs/recon-2.md。

商品列表 API 依大分類回傳整棵子分類的商品，所以每個大分類請求一次就能抓完。
7 位數編號和日本宜得利的商品コード相同；13 位數的是台灣店內碼。
"""
import re

from . import http

API = "https://frontendapi-ggazgncacwcqc8bt.z01.azurefd.net/api"
HEADERS = {"Referer": "https://www.nitori-net.tw/", "Origin": "https://www.nitori-net.tw"}
PRODUCT_URL = "https://www.nitori-net.tw/product/{}"
SKIP_CATEGORIES = {"其他費用"}  # 運費、組裝費等，不是商品
THEMED_RE = re.compile(r"優惠|推薦|限定|特價|活動")
_CODE7_RE = re.compile(r"^\d{7}$")


def _post(api_url, query):
    body = {"languageID": 1, "operateAction": "Search",
            "paramData": {"apiUrl": api_url, "queryOption": query, "pageSize": 0, "pageCount": 1,
                          "orderBy": "", "lastID": 0}, "data": {}}
    d = http.get_json(API + api_url, data=body, headers=HEADERS)
    if str(d.get("code")) != "200":
        raise http.FetchError(f"宜得利 API {api_url} 回傳 {d.get('code')} {d.get('message')}")
    return d["data"]


def fetch(max_categories=None):
    """回傳 itemNo → (列表資料, 大分類名稱)。商品同時在多個大分類時，優先用一般商品分類。"""
    cats = [c for c in _post("/Home/GetProductCategories", {})["all"]
            if c["primaryCategoryName"] not in SKIP_CATEGORIES]
    # 一般分類先、行銷分類後，讓 category 盡量是一般分類
    cats.sort(key=lambda c: bool(THEMED_RE.search(c["primaryCategoryName"])))
    if max_categories:
        cats = cats[:max_categories]
    items = {}
    for c in cats:
        for it in _post("/Category/GetCategoryFilter", {"categoryId": c["categoryID"], "Keywords": []})["listItems"]:
            items.setdefault(it["itemNo"], (it, c["primaryCategoryName"]))
    return items


def transform(items):
    records = []
    for item_no, (it, category) in items.items():
        skus = it.get("skunos") or []
        prices = it.get("skusPrice") or []
        colors = it.get("skusColor") or []
        if not skus or len(prices) != len(skus):
            continue
        variants = []
        for i, sku in enumerate(skus):
            p = prices[i]
            names = (colors[i].get("colorName") if i < len(colors) else None) or []
            sale = p["salePrice"] if p["salePrice"] < p["listPrice"] else None
            variants.append({"color": next((n for n in names if n), ""), "price": int(p["listPrice"]),
                             "salePrice": int(sale) if sale is not None else None, "ids": [sku]})
        rid = next((s for s in skus if _CODE7_RE.match(s)), skus[0])
        sales = [v["salePrice"] for v in variants if v["salePrice"] is not None]
        records.append({
            "brand": "NITORI",
            "id": rid,
            "altIds": sorted(set(skus) - {rid}),
            "name": it["name"].strip(),
            "price": max(v["price"] for v in variants),
            "salePrice": min(sales) if sales else None,
            "maxPrice": max(v["salePrice"] if v["salePrice"] is not None else v["price"] for v in variants),
            "image": it.get("imageUrl") or "",
            "url": PRODUCT_URL.format(item_no),
            "category": "" if THEMED_RE.search(category) else category,
            "audience": [],
            "variants": variants,
        })
    records.sort(key=lambda r: r["id"])
    return records
