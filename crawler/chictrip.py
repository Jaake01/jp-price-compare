"""去趣 chicTrip 日本優惠券（給 App 的「優惠券」分頁，和 MATCHA 合併顯示）。

來源是去趣網站自己載入的公開 JSON（gcpprodapi.chictrip.com.tw），不需登入、不開瀏覽器。
每張券有店名、折扣摘要、期限文字、品牌小圖網址，以及券圖網址（多半就是可直接給店員掃的完整券）
或店家自己的券頁連結。網站上沒有逐張的券頁，「開啟網站」連到去趣的日本優惠券列表。
"""
import re

from . import http

API = "https://gcpprodapi.chictrip.com.tw/Coupon"
SITE_URL = "https://www.chictrip.com.tw/service/Coupon?language=zh-tw&countryid=7"
JAPAN = 7
UNKNOWN = "unknown"
NO_EXPIRY = "none"  # 頁面寫「無期限」

# 去趣的類別 → App 的類別（一張券可能在好幾類，依這個順序取第一個）
CATEGORY_MAP = [
    ("藥妝", "藥妝雜貨"),
    ("家電", "電器行"),
    ("百貨", "百貨店"),
    ("運動", "運動/戶外用品"),  # 「服飾・運動用品」
]


def parse_deadline(text):
    """「期限 2027/3/31」「期限至 2026/12/31」→ 2027-03-31；「無期限」→ none；其他（兌完為止等）→ unknown。"""
    t = (text or "").strip()
    if "無期限" in t:
        return NO_EXPIRY
    m = re.search(r"(20\d{2})\s*[/.\-年]\s*(\d{1,2})\s*[/.\-月]\s*(\d{1,2})", t)
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else UNKNOWN


def _list(data):
    d = (data or {}).get("data")
    lst = d if isinstance(d, list) else (d or {}).get("couponList")  # GetCouponsV3 直接回傳陣列
    if not isinstance(lst, list):
        raise RuntimeError("去趣 API 回應格式不對（找不到 couponList）")
    return lst


def category_lookup():
    """回傳 {券 id: App 類別}。去趣的分類要一類一類查（每類一次請求）。"""
    data = http.get_json(f"{API}/GetCouponWithFilter", params={"countryIds": JAPAN})
    cats = []
    for c in ((data.get("data") or {}).get("filters") or {}).get("couponCategoryList") or []:
        if c.get("countryId") == JAPAN:
            cats = c.get("categoryList") or []
    found = {}
    for name, ours in CATEGORY_MAP:
        seq = next((c["categorySeqNo"] for c in cats if name in (c.get("categoryName") or "")), None)
        if seq is None:
            continue
        lst = _list(http.get_json(f"{API}/GetCouponsV3", params={"countryIds": JAPAN, "couponCategorySeqNos": seq}))
        for x in lst:
            found.setdefault(x.get("id"), ours)
    return data, found


def to_item(x, category, fetched_at):
    def val(v):
        v = (v or "").strip() if isinstance(v, str) else v
        return v if v else UNKNOWN
    image = (x.get("imgContentUrl") or "").strip() or None
    link = (x.get("redirectUrl") or "").strip() or None
    return {
        "id": "ct-" + (x.get("code") or x.get("id") or "").strip(),
        "source": "chictrip",
        "store": val(x.get("title")),
        "category": category or "其他",
        "section": UNKNOWN,
        "title": None,
        "discount": val(x.get("subTitle")),
        "threshold": UNKNOWN,   # 去趣只有一句摘要，門檻、使用方式都印在券圖上
        "usage": UNKNOWN,
        "validUntil": parse_deadline(x.get("deadlineText")),
        "validText": (x.get("deadlineText") or "").strip() or None,
        "url": SITE_URL,
        "couponLink": link,
        "couponImage": image,
        "terms": [],
        "fetchedAt": fetched_at,
        "embeddable": False,
        "logo": (x.get("imgUrl") or "").strip() or None,
    }


def fetch(today):
    """回傳 (items, 錯誤列表)。"""
    data, cats = category_lookup()
    items, seen = [], set()
    for x in _list(data):
        it = to_item(x, cats.get(x.get("id")), today)
        if it["id"] in seen or it["id"] == "ct-":
            continue
        seen.add(it["id"])
        items.append(it)
    return items, []
