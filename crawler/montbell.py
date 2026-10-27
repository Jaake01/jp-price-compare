"""mont-bell 台灣（www.montbell.com.tw，Cyberbiz）。詳見 docs/recon-2.md。

列表頁的價格和商品頁不一致（列表會顯示活動價），所以只用單品 JSON。
單品 JSON 每天輪流抓一部分（沒抓過的優先），一週輪完一次；每款記下確認日期（checkedAt），
前端會顯示，價格最久約一週前（2026-10-27 決定）。
"""
import re
import urllib.parse
from datetime import datetime, timezone

from . import http

BASE = "https://www.montbell.com.tw"
_CODE_RE = re.compile(r"#\s*(\d{7})")
_LOC_RE = re.compile(r"<loc>\s*https://www\.montbell\.com\.tw/products/([^<\s]+)\s*</loc>")
_AUDIENCE = [("男女", ["女", "男"]), ("女款", ["女"]), ("男款", ["男"]), ("女", ["女"]), ("男", ["男"]),
             ("兒童", ["童"]), ("童", ["童"]), ("嬰", ["嬰"]), ("BABY", ["嬰"])]


def fetch_handles():
    xml = http.request(f"{BASE}/sitemap.xml").decode("utf-8", "replace")
    return [urllib.parse.unquote(h) for h in _LOC_RE.findall(xml)]


def parse_product(d):
    """單品 JSON → 快取資料。各色取該色最低售價與最高原價。"""
    colors = {}
    for v in d.get("variants") or []:
        if v.get("price") is None:
            continue
        c = colors.setdefault(v.get("option1") or "", {"price": [], "compare": [], "skus": []})
        c["price"].append(v["price"])
        if v.get("compare_at_price"):
            c["compare"].append(v["compare_at_price"])
        if v.get("sku"):
            c["skus"].append(v["sku"])
    variants = []
    for color, c in colors.items():
        now = int(round(min(c["price"])))
        orig = int(round(max(c["compare"] + c["price"])))
        variants.append({"color": color, "now": now, "original": orig})
    img = (d.get("featured_image") or {}).get("large") or ""
    return {
        "id": d["id"],
        "handle": d["handle"],
        "title": d.get("title", ""),
        "variants": variants,
        "image": ("https:" + img) if img.startswith("//") else img,
    }


def update_cache(cache, handles, limit):
    """快取以 handle 為鍵。沒抓過的先抓，其餘從最舊的開始輪流更新，最多 limit 個。
    回傳 (新快取, 本次抓了幾個, 還沒抓過的剩幾個)。"""
    hs = set(handles)
    cache = {h: v for h, v in cache.items() if h in hs}  # 移除已下架的
    missing = [h for h in handles if h not in cache]
    stale = sorted(cache, key=lambda h: cache[h].get("fetched", ""))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    done = 0
    for h in (missing + stale)[:limit]:
        try:
            d = http.get_json(f"{BASE}/products/{urllib.parse.quote(h)}.json")
        except http.FetchError:
            continue
        cache[h] = dict(parse_product(d), fetched=now)
        done += 1
    return cache, done, max(0, len(missing) - done)


def _audience(name):
    for k, v in _AUDIENCE:
        if k in name:
            return list(v)
    return []


def transform(cache):
    records = {}
    for h, c in cache.items():
        m = _CODE_RE.search(c.get("title", ""))
        if not m or not c.get("variants"):
            continue
        code = m.group(1)
        name = _CODE_RE.sub("", c["title"]).strip()
        variants = [{"color": v["color"], "price": v["original"],
                     "salePrice": v["now"] if v["now"] < v["original"] else None, "ids": [code]}
                    for v in c["variants"]]
        sales = [v["salePrice"] for v in variants if v["salePrice"] is not None]
        rec = {
            "brand": "MB",
            "id": code,
            "altIds": [],
            "name": name,
            "price": max(v["price"] for v in variants),
            "salePrice": min(sales) if sales else None,
            "maxPrice": max(v["salePrice"] if v["salePrice"] is not None else v["price"] for v in variants),
            "image": c.get("image", ""),
            "url": f"{BASE}/products/{urllib.parse.quote(h)}",
            "category": "",
            "audience": _audience(name),
            "checkedAt": c.get("fetched", ""),
            "variants": variants,
        }
        # 同一品番出現在兩個商品頁時，留最近確認的
        if code not in records or rec["checkedAt"] > records[code]["checkedAt"]:
            records[code] = rec
    return sorted(records.values(), key=lambda r: r["id"])
