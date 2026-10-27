"""MUJI 台灣網路商店（91APP，shop id 41566）。詳見 docs/recon.md。

每天用 91APP 的 GraphQL 列表 API 更新價格；列表只給第一個尺寸的 JAN，
所以新出現的商品頁會抓一次商品頁 HTML 補齊所有尺寸的 JAN，存在快取（JAN 不會變）。
"""
import re

from . import nineyi

SHOP = nineyi.Shop(41566, "https://shop.muji.tw", "MUJI")
SALEPAGE_URL = "https://shop.muji.tw/SalePage/Index/{}"

# 行銷用、和商品分類重疊的頂層分類，不拿來當 category
THEMED_RE = re.compile(r"新商品|期間限定|SALE|話題|提案|推薦|對策|系列|聯名|[\U0001F300-\U0001FAFF\u2600-\u27BF]")


def fetch_listing(max_categories=None, max_pages=None):
    """回傳 (pages, groups)。pages: salePageId → 列表資料（含 _category）；groups: salePageId → (群組代表 id, 顏色名)。"""
    cats = SHOP.categories()
    if max_categories:
        cats = cats[:max_categories]
    pages, groups = {}, {}
    for c in cats:
        themed = bool(THEMED_RE.search(c["name"]))
        for it in SHOP.list_category(c["id"], False, max_pages):
            sid = it["salePageId"]
            prev = pages.get(sid)
            if prev is None or (prev["_themed"] and not themed):
                pages[sid] = dict(it, _category=c["name"], _themed=themed)
        for it in SHOP.list_category(c["id"], True, max_pages):
            g = (it.get("salePageGroup") or {}).get("groupItems") or []
            if not g:
                continue
            key = min(x["salePageId"] for x in g)
            for x in g:
                groups[x["salePageId"]] = (key, x["itemTitle"])
    return pages, groups


def parse_salepage(html):
    """商品頁 HTML → {jans, category, group}。"""
    jans = nineyi.sku_outer_ids(html)
    cat = nineyi.extract_json(html, "CategoryLevelName") or {}
    category = ""
    for lv in (4, 3, 2, 1):
        name = cat.get(f"Level{lv}_ShopCategory_Name")
        if name:
            category = re.sub(r"^\d+_", "", name)
            break
    grp = nineyi.extract_json(html, "SalePageGroup") or {}
    items = grp.get("SalePageItems") or []
    group = [[x["SalePageId"], x.get("GroupItemTitle", "")] for x in items]
    return {"jans": jans, "category": category, "group": group}


def update_cache(cache, pages, limit):
    """對快取裡沒有的商品頁抓 HTML 補 JAN，最多 limit 頁。回傳 (新快取, 本次抓了幾頁, 還剩幾頁)。"""
    return SHOP.update_cache(cache, pages, limit, parse_salepage)


_AUDIENCE_RE = re.compile(r"^(男女|女|男|兒童|孩童|幼兒|嬰兒|嬰幼兒)")
_AUDIENCE = {"男女": ["女", "男"], "女": ["女"], "男": ["男"], "兒童": ["童"], "孩童": ["童"],
             "幼兒": ["嬰"], "嬰兒": ["嬰"], "嬰幼兒": ["嬰"]}


def _audience(title):
    """MUJI 服飾品名開頭標示對象（女／男／兒童／幼兒）；家居、文具等沒有。"""
    m = _AUDIENCE_RE.match(title or "")
    return list(_AUDIENCE[m.group(1)]) if m else []


def _strip_color(title, color):
    if color and title.endswith(color) and len(title) > len(color):
        return title[: -len(color)].rstrip(" -－./／・,，、_")
    return title


def transform(pages, groups, cache):
    """列表 + 群組 + JAN 快取 → SPEC 格式。同款不同顏色合併成一筆。"""
    # 快取裡的群組資訊補上列表群組沒涵蓋的
    groups = dict(groups)
    for sid, info in cache.items():
        g = info.get("group") or []
        if g and int(sid) not in groups:
            key = min(x[0] for x in g)
            for gid, color in g:
                groups.setdefault(gid, (key, color))

    def ids_of(sid):
        cached = cache.get(str(sid)) or {}
        p = pages[sid]
        return cached.get("jans") or ([p["skuOuterId"]] if p.get("skuOuterId") else [str(sid)])

    # 顏色群組；共用任何 JAN 的群組也合併（官網偶有同一商品上架兩頁）
    parent = {}

    def find(k):
        while parent.setdefault(k, k) != k:
            k = parent[k]
        return k

    owner = {}
    for sid in sorted(pages):
        key = find(groups.get(sid, (sid, ""))[0])
        for jan in ids_of(sid):
            if jan in owner and find(owner[jan]) != key:
                parent[find(owner[jan])] = key
            owner.setdefault(jan, key)
    buckets = {}
    for sid in pages:
        buckets.setdefault(find(groups.get(sid, (sid, ""))[0]), []).append(sid)
    records = []
    for key, sids in buckets.items():
        sids.sort()
        variants, seen = [], set()
        for sid in sids:
            p = pages[sid]
            ids = ids_of(sid)
            if seen.intersection(ids):
                continue  # 重複上架的同一顏色
            seen.update(ids)
            color = groups.get(sid, (None, ""))[1]
            price = int(round(p["suggestPrice"]))
            current = int(round(p["price"]))
            variants.append({"color": color, "price": price,
                             "salePrice": current if current < price else None,
                             "ids": ids, "url": SALEPAGE_URL.format(sid)})
        rep_sid = sids[0]
        rep = pages[rep_sid]
        all_ids = [i for v in variants for i in v["ids"]]
        sales = [v["salePrice"] for v in variants if v["salePrice"] is not None]
        cached = cache.get(str(rep_sid)) or {}
        pic = rep.get("picUrl") or ""
        records.append({
            "brand": "MUJI",
            "id": all_ids[0],
            "altIds": sorted(set(all_ids[1:]) - {all_ids[0]}),
            "name": _strip_color(rep["title"], variants[0]["color"]),
            "price": max(v["price"] for v in variants),
            "salePrice": min(sales) if sales else None,
            "maxPrice": max(v["salePrice"] if v["salePrice"] is not None else v["price"] for v in variants),
            "image": ("https:" + pic) if pic.startswith("//") else pic,
            "url": SALEPAGE_URL.format(rep_sid),
            "category": cached.get("category") or ("" if rep["_themed"] else rep["_category"]),
            "audience": _audience(rep["title"]),
            "variants": variants,
        })
    for r in records:  # 顏色連結和商品連結相同時省略，縮小檔案
        for v in r["variants"]:
            if v["url"] == r["url"]:
                del v["url"]
    records.sort(key=lambda r: r["id"])
    return records
