"""and ST TW（Adastria 台灣，91APP，shop id 36426）：GLOBAL WORK、niko and ...。詳見 docs/recon-2.md。

一個商品頁就是一款（多色多尺寸在同一頁）。品名結尾有 7 位數商品貨號，當作 id；
各色各尺寸的 13 位數條碼從商品頁補齊，存在快取（做法同 MUJI）。
"""
import re

from . import nineyi

SHOP = nineyi.Shop(36426, "https://www.dot-st.tw", "and ST TW")
BRANDS = {
    "GW": {"category": 218807, "prefix": "GLOBAL WORK"},
    "NIKO": {"category": 245719, "prefix": "niko and"},
}

_CODE_RE = re.compile(r"-(\d{7})\s*$")
_COLORS_RE = re.compile(r"-[一二三四五六七八九十\d]+色$")
_AUDIENCE_RE = re.compile(r"^(男女|女童|男童|女|男|童|嬰幼兒|BABY)")
_AUDIENCE = {"男女": ["女", "男"], "女童": ["童"], "男童": ["童"], "女": ["女"], "男": ["男"],
             "童": ["童"], "嬰幼兒": ["嬰"], "BABY": ["嬰"]}


def fetch_listing(brand, max_pages=None):
    """回傳 salePageId → 列表資料。"""
    pages = {}
    for it in SHOP.list_category(BRANDS[brand]["category"], False, max_pages):
        pages[it["salePageId"]] = it
    return pages


def parse_salepage(html):
    return {"barcodes": nineyi.sku_outer_ids(html)}


def update_cache(cache, pages, limit):
    return SHOP.update_cache(cache, pages, limit, parse_salepage)


def split_title(brand, title):
    """「GLOBAL WORK女法蘭絨格紋襯衫上衣-二色-1074909」→（品名, 貨號, 對象）。"""
    t = title.strip()
    m = _CODE_RE.search(t)
    code = m.group(1) if m else None
    if m:
        t = t[: m.start()]
    t = _COLORS_RE.sub("", t).strip(" -")
    prefix = BRANDS[brand]["prefix"]
    if t.startswith(prefix):
        t = t[len(prefix):].lstrip(" .…")
    a = _AUDIENCE_RE.match(t)
    audience = list(_AUDIENCE[a.group(1)]) if a else []
    return t, code, audience


def transform(brand, pages, cache):
    records = []
    for sid, p in pages.items():
        name, code, audience = split_title(brand, p["title"])
        cached = cache.get(str(sid)) or {}
        barcodes = cached.get("barcodes") or ([p["skuOuterId"]] if p.get("skuOuterId") else [])
        rid = code or (barcodes[0] if barcodes else str(sid))
        price = int(round(p["suggestPrice"]))
        current = int(round(p["price"]))
        sale = current if current < price else None
        ids = [rid] + [b for b in barcodes if b != rid]
        pic = p.get("picUrl") or ""
        records.append({
            "brand": brand,
            "id": rid,
            "altIds": sorted(set(ids[1:])),
            "name": name,
            "price": price,
            "salePrice": sale,
            "maxPrice": sale if sale is not None else price,
            "image": ("https:" + pic) if pic.startswith("//") else pic,
            "url": SHOP.salepage_url(sid),
            "category": "",
            "audience": audience,
            "variants": [{"color": "", "price": price, "salePrice": sale, "ids": ids}],
        })
    records.sort(key=lambda r: r["id"])
    return records
