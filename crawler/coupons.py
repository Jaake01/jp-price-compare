"""MATCHA 優惠券清單（給 App 的「優惠券」分頁）。

用法：
  python -m crawler.coupons --prev 上一版/coupons.json --out 新/coupons.json
  python -m crawler.coupons --check 上一版/coupons.json   # 印出 yes／no：這次要不要重新抓

資料只給自己用：輸出檔不能放進公開的 repo、data 分支或 GitHub Pages（見 SPEC.md「優惠券」）。

規則
- 只抓 MATCHA 優惠券總覽頁和上面列出的各券頁，不下載任何圖片。
- 頁面沒寫的欄位一律存 "unknown"（App 顯示「未確認」），不推測、不讀圖片裡的文字。
- 折扣、門檻、使用方式都照原文存，不自己換算。
- 抓取失敗或沒通過健康檢查（網站改版）：保留上一版的券，只記錄這次失敗（lastRun）。
"""
import argparse
import html
import json
import re
import sys
import traceback
from datetime import date, datetime, timedelta, timezone

from . import chictrip, http

INDEX_URL = "https://matcha-jp.com/tw/japan-coupon"
UNKNOWN = "unknown"
UPDATE_DAYS = 90  # 距上次成功抓取滿 90 天就重新抓

# App 的類別（順序即顯示順序）；MATCHA 的分區名稱依關鍵字對應，其餘全部歸「其他」
CATEGORIES = ["藥妝雜貨", "電器行", "百貨店", "運動/戶外用品", "其他"]


def category_of(section):
    s = section or ""
    if "藥妝" in s or "唐吉訶德" in s:
        return "藥妝雜貨"
    if "電器" in s:
        return "電器行"
    if "百貨" in s:
        return "百貨店"
    if "運動" in s or "戶外" in s:
        return "運動/戶外用品"
    return "其他"


# ---------- HTML 小工具（只用標準函式庫） ----------

def _strip(fragment):
    """HTML 片段 → 純文字（保留換行），去掉多餘空白。"""
    t = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
    t = re.sub(r"</(p|div|li|h\d)>", "\n", t, flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    lines = [re.sub(r"[ \t　]+", " ", x).strip() for x in t.split("\n")]
    return "\n".join(x for x in lines if x)


def _one_line(fragment):
    return re.sub(r"\s+", " ", _strip(fragment)).strip()


def _clean(page_html):
    return re.sub(r"<!--.*?-->|<script.*?</script>|<style.*?</style>|<svg.*?</svg>", "", page_html, flags=re.S | re.I)


def _attr(tag, name):
    m = re.search(rf'\b{name}="([^"]*)"', tag)
    return html.unescape(m.group(1)) if m else None


def _block(page_html, class_name):
    """回傳第一個 class 含 class_name 的元素的內容（以同名標籤配對結尾）。"""
    m = re.search(rf'<(\w+)[^>]*class="[^"]*\b{re.escape(class_name)}\b[^"]*"[^>]*>', page_html)
    if not m:
        return None
    tag, pos, depth = m.group(1), m.end(), 1
    pat = re.compile(rf"<(/?){tag}\b[^>]*>", re.I)
    while depth:
        n = pat.search(page_html, pos)
        if not n:
            return page_html[m.end():]
        depth += -1 if n.group(1) else 1
        pos = n.end()
    return page_html[m.end():n.start()]


def clean_url(url):
    """去掉追蹤參數，統一成 https。"""
    url = url.strip()
    if url.startswith("//"):
        url = "https:" + url
    base, _, query = url.partition("?")
    keep = [p for p in query.split("&") if p and not re.match(r"(utm_\w+|tag|code)=", p)]
    return base + ("?" + "&".join(keep) if keep else "")


# ---------- 總覽頁 ----------

def parse_index(page_html):
    """回傳 [{key, store, offer, url, section, category}]，依頁面順序、網址不重複。

    只收店家卡片（shop-item）和券頁橫幅（shop-banner 裡的連結）；
    「hot-deal-card」是介紹文章，不是券，不收。
    """
    t = _clean(page_html)
    tokens = re.finditer(
        r'<h2[^>]*class="[^"]*coupon-category[^"]*"[^>]*>(.*?)</h2>'
        r'|<div[^>]*class="[^"]*shop-banner[^"]*"[^>]*>\s*(<a\b[^>]*>)(.*?)</a>'
        r'|(<a\b[^>]*class="[^"]*shop-item[^"]*"[^>]*>)(.*?)</a>',
        t, flags=re.S)
    section, out, seen, keys = None, [], set(), set()
    for m in tokens:
        if m.group(1) is not None:
            section = _one_line(m.group(1))
            continue
        a_tag, inner = (m.group(2), m.group(3)) if m.group(2) else (m.group(4), m.group(5))
        href = _attr(a_tag, "href")
        # 只收 MATCHA 繁中站的券頁與文章（eSIM 等子網站的推廣連結不是券）
        if not href or not re.match(r"(https:)?//matcha-jp\.com/tw/", href):
            continue
        url = clean_url(href)
        if url in seen:
            continue
        seen.add(url)
        key = (_attr(a_tag, "id") or "").removeprefix("tw-") or re.sub(r"\W+", "-", url.split("matcha-jp.com/")[-1])
        if key in keys:  # 同一個 id 用在好幾張券（例如各地區的鶴羽藥妝）：加上券號區分
            key = f"{key}-{url.rstrip('/').split('/')[-1]}"
        keys.add(key)
        brand = re.search(r'<span class="brand">(.*?)</span>', inner, flags=re.S)
        offer = re.search(r'<span class="offer">(.*?)</span>', inner, flags=re.S)
        out.append({
            "key": key,
            "store": _one_line(brand.group(1)) if brand else None,  # 橫幅沒有店名，用券頁的
            "offer": _one_line(offer.group(1)) if offer else None,
            "logo": _img_src(inner) if not m.group(2) else None,  # 店家卡片的品牌圖（橫幅是宣傳圖，不用）
            "url": url,
            "section": section,
            "category": category_of(section),
        })
    return out


# ---------- 券頁與文章頁 ----------

_AMOUNT_RE = re.compile(r"[0-9０-９][0-9０-９,，]*\s*(?:萬|万)?\s*(?:日圓|日元|円|日幣)"
                        r"|(?:日幣|日圓|[¥￥])\s*[0-9０-９][0-9０-９,，]*\s*(?:萬|万)?")
_MIN_RE = re.compile(r"以上|滿|満|達")
_EXCLUDE_RE = re.compile(r"對象外|不適用|除外|以外的商品|以上的商品")


def threshold_from(lines):
    """找出寫明金額門檻（N 日圓／円以上、滿 N 日圓）的句子，照原文回傳（去掉開頭編號）。沒有就回傳 unknown。

    免稅門檻（例如未稅滿 5,000 日圓）也算。寫「以上的商品不適用」這類排除條款不算。
    """
    found = []
    for line in lines:
        for sent in re.split(r"(?<=[。！!])", line):
            sent = re.sub(r"^\s*[0-9０-９]+\s*[.．、)）]\s*", "", sent).strip()
            if sent and _AMOUNT_RE.search(sent) and _MIN_RE.search(sent) and not _EXCLUDE_RE.search(sent) and sent not in found:
                found.append(sent)
    return "\n".join(found) if found else UNKNOWN


def _expiry(text):
    m = re.search(r"(20\d{2})[-/.年]\s*(\d{1,2})[-/.月]\s*(\d{1,2})", text or "")
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else UNKNOWN


def _img_src(fragment):
    """片段裡第一張圖的網址（lazyload 的 data-src 優先）。只存網址，不下載。"""
    m = re.search(r"<img\b[^>]*>", fragment or "")
    if not m:
        return None
    src = _attr(m.group(0), "data-src") or _attr(m.group(0), "src")
    return clean_url(src) if src else None


def _coupon_links(fragment):
    """說明區裡指向實際券畫面的連結（例如唐吉訶德自己的券頁）；不含下載 App 的連結。"""
    links = []
    for m in re.finditer(r"(<a\b[^>]*>)(.*?)</a>", fragment or "", flags=re.S):
        href, text = _attr(m.group(1), "href"), _one_line(m.group(2))
        if not href or "APP" in text.upper() or "onelink" in href or "優惠券" not in text:
            continue
        url = clean_url(href) if "matcha-jp.com" in href else href.strip()
        if url not in links:
            links.append(url)
    return links


_NUM_RE = re.compile(r"^\s*[0-9０-９]+\s*[.．、)）]")


def _numbered_terms(paragraphs):
    """使用條件：一條一行。同一條裡的換行（例如「【折扣對象外商品】」清單）併回那一條。"""
    terms = []
    for p in paragraphs:
        for line in _strip(p).split("\n"):
            if terms and not _NUM_RE.match(line) and _NUM_RE.match(terms[-1]):
                terms[-1] += " " + line
            else:
                terms.append(line)
    return terms


def parse_coupon_page(page_html):
    """MATCHA 券頁（/tw/coupon/N）。"""
    t = _clean(page_html)
    brand = re.search(r'<span class="brand-name">(.*?)</span>', t, flags=re.S)
    name = re.search(r'<span class="coupon-name">(.*?)</span>', t, flags=re.S)
    price = _block(t, "price-box")
    desc = _block(t, "desc")
    expiry = re.search(r'<p class="expiry-date">(.*?)</p>', t, flags=re.S)
    terms_html = _block(t, "terms")
    terms = _numbered_terms(re.findall(r"<p\b[^>]*>(.*?)</p>", terms_html or "", flags=re.S))
    # 使用方式：說明區（coupon-details__usage）裡的段落文字；按鈕（下載 App 等）不算
    usage_lines = []
    for p in re.findall(r"<p\b[^>]*>(.*?)</p>", re.sub(r"<div\b[^>]*>\s*<a\b.*?</a>\s*</div>", "", desc or "", flags=re.S), flags=re.S):
        usage_lines += [x.lstrip("・").strip() for x in _strip(p).split("\n")]
    usage_lines = [x for x in usage_lines if x]
    return {
        "brand": _one_line(brand.group(1)) if brand else None,
        "title": _one_line(name.group(1)) if name else None,
        "discount": _one_line(price) if price and _one_line(price) else None,
        "usage": "\n".join(usage_lines) if usage_lines else UNKNOWN,
        "validUntil": _expiry(expiry.group(1)) if expiry else UNKNOWN,
        "threshold": threshold_from(terms + usage_lines),
        "terms": terms,
        "couponLinks": _coupon_links(desc),
        "logo": _img_src(_block(t, "logo-wrapper")),
        "couponImage": _img_src(_block(t, "type-image")),  # 券圖（有些有條碼可直接掃，有些只是宣傳圖）
    }


def parse_article_page(page_html):
    """MATCHA 介紹文章（例如 Bic Camera 的券放在文章裡，/tw/17389）。

    券本身是文章裡的一張圖（含條碼與有效期限），文字只寫到門檻與折扣說明；
    圖片裡的內容不讀，所以有效期限、使用方式存 unknown。
    """
    t = _clean(page_html)
    title = re.search(r"<h1[^>]*>(.*?)</h1>", t, flags=re.S)
    paras = [_one_line(p) for p in re.findall(r"<p\b[^>]*>(.*?)</p>", t, flags=re.S)]
    # 門檻只取第一個寫到金額門檻的句子（文章會重複同一段說明）
    first = threshold_from(paras).split("\n")[0]
    links = []
    for m in re.finditer(r'class="[^"]*em-link-btn[^"]*"[^>]*>\s*(<a\b[^>]*>)(.*?)</a>', t, flags=re.S):
        href, text = _attr(m.group(1), "href"), _one_line(m.group(2))
        if href and "優惠券" in text and href not in links:
            links.append(clean_url(href) if href.startswith("//") else href)
    return {
        "brand": None,
        "title": _one_line(title.group(1)) if title else None,
        "discount": None,
        "usage": UNKNOWN,
        "validUntil": UNKNOWN,
        "threshold": first or UNKNOWN,
        "terms": [],
        "couponLinks": [],
        "logo": None,
        "couponImage": links[0] if links else None,  # Bic Camera：券本身就是這張圖（含條碼）
    }


def frame_blocked(headers):
    """依回應標頭判斷能不能在別的網站（App）裡內嵌。看不出來時當作不能。"""
    xfo = (headers.get("X-Frame-Options") or "").strip().upper()
    if xfo in ("DENY", "SAMEORIGIN"):
        return True
    csps = headers.get_all("Content-Security-Policy") if hasattr(headers, "get_all") else [headers.get("Content-Security-Policy")]
    for csp in csps or []:
        m = re.search(r"frame-ancestors([^;]*)", csp or "", flags=re.I)
        if m and "*" not in m.group(1).split():
            return True  # 只允許列出的網域內嵌，App 不在裡面
    return False


def build_item(entry, page, fetched_at, embeddable):
    def val(x):
        return x if x else UNKNOWN
    return {
        "id": entry["key"],
        "source": "matcha",
        "store": val(entry.get("store") or page.get("brand")),
        "category": entry["category"],
        "section": entry.get("section") or UNKNOWN,
        "title": page.get("title"),
        "discount": val(page.get("discount") or entry.get("offer")),
        "threshold": val(page.get("threshold")),
        "usage": val(page.get("usage")),
        "validUntil": val(page.get("validUntil")),
        "url": entry["url"],
        "couponLink": (page.get("couponLinks") or [None])[0],  # 店家自己的券頁（例如唐吉訶德）
        "couponImage": page.get("couponImage"),
        "logo": entry.get("logo") or page.get("logo"),
        "terms": page.get("terms") or [],
        "fetchedAt": fetched_at,
        "embeddable": embeddable,
    }


def fetch(only=None, today=None):
    """抓總覽頁與各券頁。only：只抓這些 key（測試／試做用）。回傳 (items, 錯誤列表)。"""
    today = today or date.today().isoformat()
    entries = parse_index(http.request(INDEX_URL).decode("utf-8", "replace"))
    if not entries:
        raise RuntimeError("總覽頁找不到任何券（網站可能改版）")
    if only:
        entries = [e for e in entries if e["key"] in only]
        missing = set(only) - {e["key"] for e in entries}
        if missing:
            raise RuntimeError(f"總覽頁找不到：{', '.join(sorted(missing))}")
    items, errors, removed = [], [], []
    for e in entries:
        try:
            raw, headers, final = http.request_full(e["url"])
            if clean_url(final).rstrip("/") != e["url"].rstrip("/"):
                # 券已結束：MATCHA 把券頁轉回券列表，總覽頁卻還留著卡片 → 不列入
                removed.append(f"{e['store'] or e['key']}（券頁已轉址，可能已結束）")
                continue
            text = raw.decode("utf-8", "replace")
            page = parse_coupon_page(text) if "/coupon/" in e["url"] else parse_article_page(text)
            items.append(build_item(e, page, today, not frame_blocked(headers)))
        except Exception as ex:  # 單一券頁失敗：記錄，交給健康檢查判斷
            errors.append(f"{e['key']}：{ex}")
    return items, errors, removed


# ---------- 健康檢查、要不要更新 ----------

def health_check(items, prev_items, errors, sample=False):
    """回傳錯誤列表（空 = 通過）。"""
    problems = []
    if not items:
        return ["一張券都沒抓到"]
    if errors and len(errors) > max(1, len(items) // 10):
        problems.append(f"{len(errors)} 張券頁抓取失敗：{errors[:3]}")
    if not sample and prev_items and len(items) < len(prev_items) * 0.7:
        problems.append(f"券數從 {len(prev_items)} 張掉到 {len(items)} 張（少超過 30%）")
    bad = [x["id"] for x in items if x["store"] == UNKNOWN or not x["url"]]
    if len(bad) > len(items) * 0.1:
        problems.append(f"{len(bad)} 張缺店名或網址：{bad[:5]}")
    known = sum(1 for x in items if x["discount"] != UNKNOWN or x["validUntil"] != UNKNOWN)
    if known < len(items) * 0.5:
        problems.append("超過一半的券抓不到折扣和期限（券頁可能改版）")
    return problems


def needs_update(data, today=None):
    """每週檢查用：回傳 (要不要抓, 原因)。"""
    today = today or date.today()
    if not data or not data.get("updatedAt"):
        return True, "還沒有資料"
    last = datetime.fromisoformat(data["updatedAt"]).date()
    if (data.get("lastRun") or {}).get("ok") is False:
        return True, "上次抓取失敗，再試一次"
    if today - last >= timedelta(days=UPDATE_DAYS):
        return True, f"距上次成功抓取已 {(today - last).days} 天"
    # 上次抓取之後才過期的券：MATCHA 通常會在原網址換上新一期，去抓新的
    # （抓完原頁還是舊期限的，期限早於上次抓取，不會每週重抓）
    for x in data.get("items", []):
        v = x.get("validUntil")
        if v and re.match(r"\d{4}-", v) and last.isoformat() <= v < today.isoformat():
            return True, f"{x['store']} 的券已在 {v} 過期"
    return False, "不需要更新"


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, TypeError):
        return None


# ---------- 同一家店合併（App 列表一列，詳細頁列出各來源的券） ----------

# 店名正規化後仍對不上的，手動指定同一家店（左：正規化後的名字，右：合併用的鍵）
ALIASES = {
    "biccamera+salonia": "biccamera",
    "國民藥妝": "國民",
    "sundrug": "尚都樂客",
    "樂購仕": "laox",
    "杏林堂": "杏林堂藥妝",
    "lady藥妝": "lady藥局",
    "takeya多慶屋": "多慶屋",
    "松阪屋百貨": "大丸松坂屋",
    "大丸・松阪屋百貨": "大丸松坂屋",
    "大丸松阪屋百貨": "大丸松坂屋",
    "tobu東武百貨": "東武百貨店",
    "東武百貨": "東武百貨店",
    "京王百貨店新宿店": "京王百貨店",
    "edion愛電王": "edion愛電王",
    "victoria運動用品": "victoria",
    "樂天免稅店銀座": "樂天免稅銀座店",
    "nipponrent-a-car": "日本租車",
}
_GENERIC = {"藥妝", "藥局", "百貨", "百貨店", "免稅店", "運動用品"}


def brand_key(name):
    """店名 → 合併用的鍵。去掉「日本」、括號、空白與符號；中英並列時取中文（例：YAMADA 山田電機 → 山田電機）。"""
    n = re.sub(r"[（(【].*?[）)】]", "", name or "")
    n = re.sub(r"^日本\s*", "", n.strip())
    n = re.sub(r"[\s・･·]+", "", n).lower()
    if n in ALIASES:
        return ALIASES[n]
    cjk = "".join(re.findall(r"[\u3040-\u30ff\u4e00-\u9fff]+", n))
    key = cjk if cjk and cjk not in _GENERIC and re.search(r"[a-z]", n) else n
    return ALIASES.get(key, key)


def assign_groups(items):
    """每張券加上 group（同一家店同一個值）。有 MATCHA 的券時用 MATCHA 的 id，讓舊的最愛設定繼續有效。"""
    by_key = {}
    for it in items:
        by_key.setdefault(brand_key(it["store"]), []).append(it)
    for key, group in by_key.items():
        sources = {x["source"] for x in group}
        if len(sources) < 2:  # 只在不同網站之間合併；同網站同名的券各自一列
            for x in group:
                x["group"] = x["id"]
            continue
        lead = next((x for x in group if x["source"] == "matcha"), group[0])
        for x in group:
            x["group"] = lead["id"]
    return items


# ---------- 執行 ----------

SOURCES = ["matcha", "chictrip"]


def _fetch_source(name, only, today):
    if name == "matcha":
        items, errors, removed = fetch(only, today)
        return items, errors, removed
    items, errors = chictrip.fetch(today)
    return items, errors, []


def run(prev, only=None):
    """回傳要寫出的資料物件。每個來源各自檢查：失敗的來源保留上一版的券，只記錄失敗。"""
    prev = prev or {}
    prev_items = prev.get("items") or []
    prev_src = prev.get("sources") or {}
    today = date.today().isoformat()
    now = _now()
    all_items, status, warnings = [], {}, []
    for name in (["matcha"] if only else SOURCES):
        old = [x for x in prev_items if x.get("source", "matcha") == name]
        try:
            items, errors, removed = _fetch_source(name, only, today)
            problems = health_check(items, old, errors, sample=bool(only))
        except Exception as ex:
            traceback.print_exc()
            problems, errors, removed = [f"{type(ex).__name__}: {ex}"], [], []
        if problems:
            all_items += [{**x, "source": name} for x in old]
            status[name] = {"ok": False, "updatedAt": (prev_src.get(name) or {}).get("updatedAt") or prev.get("updatedAt"),
                            "error": "；".join(problems)[:500], "count": len(old)}
        else:
            all_items += items
            status[name] = {"ok": True, "updatedAt": now, "error": None, "count": len(items)}
            warnings += errors + removed
    ok = all(v["ok"] for v in status.values())
    dates = [v["updatedAt"] for v in status.values() if v["updatedAt"]]
    order = {c: i for i, c in enumerate(CATEGORIES)}
    all_items.sort(key=lambda x: (order.get(x["category"], 99), SOURCES.index(x.get("source", "matcha"))))
    assign_groups(all_items)
    errors_txt = "；".join(f"{k}：{v['error']}" for k, v in status.items() if not v["ok"])
    return {
        "source": "MATCHA、去趣 chicTrip",
        "updatedAt": min(dates) if dates else None,  # 最舊的來源日期（保守）
        "count": len(all_items),
        "sources": status,
        "lastRun": {"at": now, "ok": ok, "error": errors_txt or None, "warnings": warnings or None},
        "items": all_items,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--prev", help="上一版 coupons.json（沒有也可以）")
    ap.add_argument("--out", help="輸出檔")
    ap.add_argument("--only", help="只抓這些券（逗號分隔的 key，例如 don-quijote,bic-camera）")
    ap.add_argument("--check", metavar="FILE", help="只判斷要不要重新抓：印出 yes 或 no")
    args = ap.parse_args(argv)
    if args.check is not None:
        need, why = needs_update(_load(args.check))
        print("yes" if need else "no")
        print(why, file=sys.stderr)
        return 0
    if not args.out:
        ap.error("需要 --out")
    data = run(_load(args.prev), only=set(args.only.split(",")) if args.only else None)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    # 只印數量與狀態，不印券的內容（Actions 紀錄可能是公開的）
    lr = data["lastRun"]
    for name, st in data["sources"].items():
        print(f"{name}：{'成功' if st['ok'] else '失敗（保留上一版）'}，{st['count']} 張" + ("" if st["ok"] else f"：{st['error']}"))
    print(f"優惠券：{'成功' if lr['ok'] else '部分失敗'}，共 {data['count']} 張")
    return 0 if lr["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
