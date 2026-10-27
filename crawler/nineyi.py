"""91APP 平台共用工具（MUJI、and ST TW 都建在 91APP 上）。"""
import json
from datetime import datetime, timezone

from . import http

GRAPHQL = "https://fts-api.91app.com/pythia-cdn/graphql"
FETCH_COUNT = 100  # API 單次上限

Q_CATEGORIES = "query cms_shopCategoryList($shopId: Int!) { shopCategoryList(shopId: $shopId) { categoryList { id name } } }"
Q_LIST = (
    "query cms_shopCategory($shopId: Int!, $categoryId: Int!, $startIndex: Int!, $fetchCount: Int!, $group: Boolean) {"
    " shopCategory(shopId: $shopId, categoryId: $categoryId) {"
    " salePageList(startIndex: $startIndex, maxCount: $fetchCount, includeSalePageGroup: $group) {"
    " salePageList { salePageId title picUrl price suggestPrice isSoldOut skuOuterId"
    " salePageGroup { groupItems { salePageId itemTitle } } }"
    " totalSize } } }"
)


class Shop:
    def __init__(self, shop_id, origin, label):
        self.shop_id = shop_id
        self.origin = origin  # 例如 https://shop.muji.tw
        self.label = label
        self.headers = {"Referer": origin + "/", "ny-shop-id": str(shop_id), "ny-market": "TW"}

    def salepage_url(self, sid):
        return f"{self.origin}/SalePage/Index/{sid}"

    def gql(self, query, variables):
        d = http.get_json(GRAPHQL, headers=self.headers, params={
            "shopId": self.shop_id, "lang": "zh-TW", "query": query,
            "variables": json.dumps(variables, separators=(",", ":")),
        })
        if d.get("errors"):
            raise http.FetchError(f"{self.label} GraphQL 錯誤：{d['errors'][0].get('code')}")
        return d["data"]

    def categories(self):
        return self.gql(Q_CATEGORIES, {"shopId": self.shop_id})["shopCategoryList"]["categoryList"]

    def list_category(self, cat_id, group=False, max_pages=None):
        items, start, page = [], 0, 0
        while True:
            s = self.gql(Q_LIST, {"shopId": self.shop_id, "categoryId": cat_id, "startIndex": start,
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

    def update_cache(self, cache, sale_page_ids, limit, parse):
        """對快取裡沒有的商品頁抓 HTML，用 parse(html) 取資料存進快取，最多 limit 頁。
        回傳 (新快取, 本次抓了幾頁, 還剩幾頁)。"""
        ids = set(sale_page_ids)
        cache = {k: v for k, v in cache.items() if int(k) in ids}  # 移除已下架的
        todo = [sid for sid in sorted(ids, reverse=True) if str(sid) not in cache]
        done = 0
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        for sid in todo[:limit]:
            try:
                html = http.request(self.salepage_url(sid), headers={"Referer": self.origin + "/"}).decode("utf-8", "replace")
            except http.FetchError:
                continue  # 下次再試
            cache[str(sid)] = dict(parse(html), fetched=now)
            done += 1
        return cache, done, max(0, len(todo) - done)


def extract_json(html, key):
    """從商品頁 HTML 內嵌的 JSON 取出 "key": 後面的值。"""
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


def sku_outer_ids(html):
    skus = extract_json(html, "SKUPropertySetList") or []
    return [s["OuterId"] for s in skus if s.get("OuterId")]
