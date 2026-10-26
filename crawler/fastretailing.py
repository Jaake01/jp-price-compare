"""UNIQLO 台灣、GU 台灣（同一套 hmall 平台，共用此模組）。詳見 docs/recon.md。"""
import re

from . import http

SITES = {
    "UQ": {
        "api": "https://d.uniqlo.com/tw/p/search/products/by-category",
        "referer": "https://www.uniqlo.com/",
        "base": "https://www.uniqlo.com/tw",
    },
    "GU": {
        "api": "https://d.gu-global.com/tw/p/search/products/by-category",
        "referer": "https://www.gu-global.com/",
        "base": "https://www.gu-global.com/tw",
    },
}
PAGE_SIZE = 200

_STYLE_RE = re.compile(r"^\s*(\d{6})\s*/\s*(.+?)\s*$")
_TRAILING_CODES_RE = re.compile(r"\s*\d{6}(\s*/\s*\d{6})*\s*$")
_CODE_RE = re.compile(r"(?<!\d)\d{6}(?!\d)")


def _body(page, page_size):
    return {
        "pageInfo": {"page": page, "pageSize": page_size},
        "belongTo": "pc", "rank": "overall",
        "priceRange": {"low": 0, "high": 0},
        "color": [], "size": [], "identity": [], "exist": [],
        "categoryCode": "ALL", "byCateCodeWithLineUp": False,
        "searchFlag": False, "description": "", "stockFilter": "warehouse",
    }


def fetch(brand, max_pages=None):
    """抓全站商品列表（原始資料）。"""
    site = SITES[brand]
    headers = {"Referer": site["referer"], "langcode": "zh_TW", "Accept": "application/json"}
    products, page, total = [], 1, None
    while True:
        d = http.get_json(site["api"], data=_body(page, PAGE_SIZE), headers=headers)
        if not d.get("success"):
            raise http.FetchError(f"{brand} API 回傳失敗：{d.get('msg')}")
        resp = d["resp"][0]
        total = resp["productSum"]
        batch = resp.get("productList") or []
        products += batch
        if not batch or len(products) >= total or (max_pages and page >= max_pages):
            break
        page += 1
    return products, total


def _clean_name(name):
    return _TRAILING_CODES_RE.sub("", name).strip()


def _variants(p, base):
    """一筆列表商品 → 各顏色 variant。"""
    current = p["minPrice"]
    sale = current if current < p["originPrice"] else None
    url = f"{base}/zh_TW/product-detail.html?productCode={p['productCode']}"
    out = []
    for s in p.get("styleText") or []:
        m = _STYLE_RE.match(s)
        code, color = (m.group(1), m.group(2)) if m else (p["code"], s.strip())
        out.append({"color": color, "price": p["originPrice"], "salePrice": sale,
                    "ids": [code], "url": url})
    if not out:
        out.append({"color": "", "price": p["originPrice"], "salePrice": sale,
                    "ids": [p["code"]], "url": url})
    return out


def transform(brand, products):
    """原始列表 → SPEC 格式。同一個 6 位數編號（官網會把特價顏色拆成另一筆）合併成一筆。"""
    base = SITES[brand]["base"]
    groups = {}
    for p in products:
        groups.setdefault(p["code"], []).append(p)
    records = []
    for code, ps in groups.items():
        primary = max(ps, key=lambda p: len(p.get("colorNums") or []))
        variants = [v for p in ps for v in _variants(p, base)]
        alt = set()
        for p in ps:
            alt |= set(_CODE_RE.findall(p.get("name", "")))
        for v in variants:
            alt |= set(v["ids"])
        alt.discard(code)
        price = max(p["originPrice"] for p in ps)
        sales = [v["salePrice"] for v in variants if v["salePrice"] is not None]
        level_one = primary.get("levelOne") or []
        records.append({
            "brand": brand,
            "id": code,
            "altIds": sorted(alt),
            "name": _clean_name(primary.get("name") or ""),
            "price": price,
            "salePrice": min(sales) if sales else None,
            "maxPrice": max(v["salePrice"] if v["salePrice"] is not None else v["price"] for v in variants),
            "image": base + primary["mainPic"] if primary.get("mainPic") else "",
            "url": f"{base}/zh_TW/product-detail.html?productCode={primary['productCode']}",
            "category": level_one[0]["name"] if level_one else "",
            "variants": variants,
        })
    for r in records:  # 顏色連結和商品連結相同時省略，縮小檔案
        for v in r["variants"]:
            if v["url"] == r["url"]:
                del v["url"]
    records.sort(key=lambda r: r["id"])
    return records
