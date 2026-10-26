"""MUJI 台灣網路商店（91APP，shop id 41566）。詳見 docs/recon.md。

每天用 91APP 的 GraphQL 列表 API 更新價格；列表只給第一個尺寸的 JAN，
所以新出現的商品頁會抓一次商品頁 HTML 補齊所有尺寸的 JAN，存在快取（JAN 不會變）。
"""
import json
import re
from datetime import datetime, timezone

from . import http

SHOP_ID = 41566
GRAPHQL = "https://fts-api.91app.com/pythia-cdn/graphql"
SALEPAGE_URL = "https://shop.muji.tw/SalePage/Index/{}"
FETCH_COUNT = 100  # API 單次上限
HEADERS = {"Referer": "https://shop.muji.tw/", "ny-shop-id": str(SHOP_ID), "ny-market": "TW"}

# 行銷用、和商品分類重疊的頂層分類，不拿來當 category
THEMED_RE = re.compile(r"新商品|期間限定|SALE|話題|提案|推薦|對策|系列|聯名|[\U0001F300-\U0001FAFF☀-➿]")

Q_CATEGORIES = "query cms_shopCategoryList($shopId: Int!) { shopCategoryList(shopId: $shopId) { categoryList { id name } } }"
Q_LIST = (
    "query cms_shopCategory($shopId: Int!, $categoryId: Int!, $startIndex: Int!, $fetchCount: Int!, $group: Boolean) {"
    " shopCategory(shopId: $shopId, categoryId: $categoryId) {"
    " salePageList(startIndex: $startIndex, maxCount: $fetchCount, includeSalePageGroup: $group) {"
    " salePageList { salePageId title picUrl price suggestPrice isSoldOut skuOuterId"
    " salePageGroup { groupItems { salePageId itemTitle } } }"
    " totalSize } } }"
)


def _gql(query, variables):
    d = http.get_json(GRAPHQL, headers=HEADERS, params={
        "shopId": SHOP_ID, "lang": "zh-TW", "query": query,
        "variables": json.dumps(variables, separators=(",", ":")),
    })
    if d.get("errors"):
        raise http.FetchError(f"MUJI GraphQL 錯誤：{d['errors'][0].get('code')}")
    return d["data"]


def _list_category(cat_id, group, max_pages=None):
    items, start, page = [], 0, 0
    while True:
        s = _gql(Q_LIST, {"shopId": SHOP_ID, "categoryId": cat_id, "startIndex": start,
                          "fetchCount": FETCH_COUNT, "group": group})["shopCategory"]["salePageList"]
        if not s:
            break
        batch = s["salePageList"] or []
        items += batch
        start += len(batch)
        page += 1
        if not batch or start >= s["totalSize"] or (max_pages and page >= max_pages):
            break
    return items


def fetch_listing(max_categories=None, max_pages=None):
    """回傳 (pages, groups)。pages: salePageId → 列表資料（含 _category）；groups: salePageId → (群組代表 id, 顏色名)。"""
    cats = _gql(Q_CATEGORIES, {"shopId": SHOP_ID})["shopCategoryList"]["categoryList"]
    if max_categories:
        cats = cats[:max_categories]
    pages, groups = {}, {}
    for c in cats:
        themed = bool(THEMED_RE.search(c["name"]))
        for it in _list_category(c["id"], False, max_pages):
            sid = it["salePageId"]
            prev = pages.get(sid)
            if prev is None or (prev["_themed"] and not themed):
                pages[sid] = dict(it, _category=c["name"], _themed=themed)
        for it in _list_category(c["id"], True, max_pages):
            g = (it.get("salePageGroup") or {}).get("groupItems") or []
            if not g:
                continue
            key = min(x["salePageId"] for x in g)
            for x in g:
                groups[x["salePageId"]] = (key, x["itemTitle"])
    return pages, groups


def _extract_json(html, key):
    i = html.find(f'"{key}":')
    if i < 0:
        return None
    j = i + len(key) + 3
    while j < len(html) and html[j].isspace():
        j += 1
    try:
        val, _ = json.JSONDecoder().raw_decode(html, j)
    except ValueError:
        return None
    return val


def parse_salepage(html):
    """商品頁 HTML → {jans, category, group}。"""
    skus = _extract_json(html, "SKUPropertySetList") or []
    jans = [s["OuterId"] for s in skus if s.get("OuterId")]
    cat = _extract_json(html, "CategoryLevelName") or {}
    category = ""
    for lv in (4, 3, 2, 1):
        name = cat.get(f"Level{lv}_ShopCategory_Name")
        if name:
            category = re.sub(r"^\d+_", "", name)
            break
    grp = _extract_json(html, "SalePageGroup") or {}
    items = grp.get("SalePageItems") or []
    group = [[x["SalePageId"], x.get("GroupItemTitle", "")] for x in items]
    return {"jans": jans, "category": category, "group": group}


def update_cache(cache, pages, limit):
    """對快取裡沒有的商品頁抓 HTML 補 JAN，最多 limit 頁。回傳 (新快取, 本次抓了幾頁, 還剩幾頁)。"""
    cache = {k: v for k, v in cache.items() if int(k) in pages}  # 移除已下架的
    todo = [sid for sid in sorted(pages, reverse=True) if str(sid) not in cache]
    done = 0
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for sid in todo[:limit]:
        try:
            html = http.request(SALEPAGE_URL.format(sid), headers={"Referer": "https://shop.muji.tw/"}).decode("utf-8", "replace")
        except http.FetchError:
            continue  # 下次再試
        cache[str(sid)] = dict(parse_salepage(html), fetched=now)
        done += 1
    return cache, done, max(0, len(todo) - done)


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
            "variants": variants,
        })
    for r in records:  # 顏色連結和商品連結相同時省略，縮小檔案
        for v in r["variants"]:
            if v["url"] == r["url"]:
                del v["url"]
    records.sort(key=lambda r: r["id"])
    return records
