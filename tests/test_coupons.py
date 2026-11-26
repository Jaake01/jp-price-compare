import unittest
from datetime import date
from email.message import Message

from crawler import coupons as c

INDEX = """
<h2 class="coupon-category">唐吉訶德和藥妝店免稅優惠券</h2>
<div class="shop-logos">
  <a class="shop-item" id="tw-don-quijote" href="https://matcha-jp.com/tw/coupon/11?utm_source=matcha&amp;utm_medium=japan-coupon">
    <img class="shop-item" src="https://resources.matcha-jp.com/coupon/330x2000/dq.png" alt=""><span class="brand">唐吉訶德</span><br><span class="offer">最高17%折扣</span></a>
</div>
<div class="shop-banner">
  <a id="tw-tomods" href="https://matcha-jp.com/tw/coupon/148?code=matcha&amp;utm_source=matcha"><img alt="Tomod's"></a>
</div>
<h2 class="coupon-category">電器行免稅優惠券</h2>
<a class="hot-deal-card" href="https://matcha-jp.com/tw/19016?utm_source=matcha"><div>BicCamera 文章</div></a>
<a class="shop-item" id="tw-bic-camera" href="https://matcha-jp.com/tw/17389?utm_source=matcha"><span class="brand">Bic Camera</span><br><span class="offer">最高17%折扣</span></a>
<!-- a class="shop-item" id="tw-old" href="https://matcha-jp.com/tw/coupon/1"><span class="brand">舊券</span></a -->
<h2 class="coupon-category">實體網卡 / eSIM網卡折扣優惠券</h2>
<a class="shop-item" href="https://esim.matcha-jp.com/?code=matcha"><span class="brand">eSIM</span></a>
<h2 class="coupon-category">東京免稅店折扣優惠券</h2>
<a class="shop-item" id="tw-lotte" href="https://matcha-jp.com/tw/coupon/5"><span class="brand">樂天免稅</span><br><span class="offer">2千日圓折扣</span></a>
"""

COUPON = """
<h1 class="title"><span class="brand-name">日本唐吉訶德免稅折扣優惠券</span><br>
<span class="coupon-name">2026年唐吉訶德折扣優惠券【免稅10%＋7%折扣！】</span></h1>
<div class="price-box"><p class="price"><span class="off">最高</span> 17%<span class="off">折扣</span></p></div>
<div class="coupon-details__usage"><div class="desc"><p>
<div style="x"><a href="https://japanportal.donki-global.com/coupon/?ptcd=1">使用唐吉訶德優惠券</a></div>
<div style="x"><a class="app-cta-button" href="https://japan-coupon.onelink.me/x">下載APP享更多優惠</a></div>
<p>・點選<a href="https://japanportal.donki-global.com/coupon/?ptcd=1">此連結跳轉至優惠券頁面</a><br>
・結帳時請將優惠券畫面出示給收銀員</p>
</p></div></div>
<div class="logo-wrapper"><img class="lazyload logo-image" data-src="https://resources.matcha-jp.com/coupon/330x2000/logo.png"></div>
<div class="type-image"><div class="type-image__wrapper"><a href="//resources.matcha-jp.com/coupon/720x2000/c.jpg">
<img class="lazyload" data-src="//resources.matcha-jp.com/coupon/720x2000/c.jpg" alt=""></a></div></div>
<p class="expiry-date">有效期限 2026-12-31 23:59:59</p>
<div class="terms">
<p>１．本優惠券僅適用於單次結帳未含稅10,000日圓以上，僅限使用一次。</p>
<p>２．以下商品為折扣對象外。<br>【折扣對象外商品】<br>酒、單品100,000日圓（未含稅）以上的商品等</p>
<p>３．不能以螢幕截圖方式使用。</p>
</div>
"""

COUPON_NO_DATES = """
<h1 class="title"><span class="brand-name">某店</span></h1>
<div class="terms"><p>1. 每次結帳僅限使用一張。<br>2. 請於結帳時出示本優惠券。</p></div>
"""

ARTICLE = """
<h1 class="title">【2026年BicCamera17％優惠券】購物攻略</h1>
<div class="em-link-btn"><a class="ejs-btn" href="https://resources.matcha-jp.com/original/2026/10/30-1.webp">Bic Camera退稅折價優惠券</a></div>
<p>現在使用優惠券，只要單日內於同一店家，單筆未稅購物滿5,000日圓以上，就能減免最多17%的折扣喔！</p>
<p>只要單日內於同一店家，單筆未稅購物滿5,000日圓以上，就能減免10%消費稅。</p>
"""


class IndexTest(unittest.TestCase):
    def test_parse_index(self):
        es = c.parse_index(INDEX)
        self.assertEqual([e["key"] for e in es], ["don-quijote", "tomods", "bic-camera", "lotte"])
        dq = es[0]
        self.assertEqual((dq["store"], dq["offer"], dq["category"]), ("唐吉訶德", "最高17%折扣", "藥妝雜貨"))
        self.assertEqual(dq["url"], "https://matcha-jp.com/tw/coupon/11")  # 去掉追蹤參數
        self.assertEqual(dq["logo"], "https://resources.matcha-jp.com/coupon/330x2000/dq.png")
        self.assertIsNone(es[1]["logo"])
        self.assertIsNone(es[1]["store"])  # 橫幅沒有店名，之後用券頁的
        self.assertEqual(es[1]["url"], "https://matcha-jp.com/tw/coupon/148")
        self.assertEqual(es[2]["category"], "電器行")
        self.assertEqual(es[3]["category"], "其他")

    def test_categories(self):
        self.assertEqual(c.category_of("各地區藥妝店免稅優惠券"), "藥妝雜貨")
        self.assertEqual(c.category_of("運動,戶外用品免稅優惠券"), "運動/戶外用品")
        self.assertEqual(c.category_of("百貨店免稅優惠券"), "百貨店")
        self.assertEqual(c.category_of("時尚,雜貨免稅優惠券"), "其他")
        self.assertEqual(c.category_of("租車和機場接送折扣優惠券"), "其他")


class PageTest(unittest.TestCase):
    def test_coupon_page(self):
        p = c.parse_coupon_page(COUPON)
        self.assertEqual(p["discount"], "最高 17%折扣")
        self.assertEqual(p["validUntil"], "2026-12-31")
        # 排除條款（10 萬日圓以上的商品不適用）不算門檻
        self.assertEqual(p["threshold"], "本優惠券僅適用於單次結帳未含稅10,000日圓以上，僅限使用一次。")
        self.assertEqual(p["usage"], "點選此連結跳轉至優惠券頁面\n結帳時請將優惠券畫面出示給收銀員")
        self.assertEqual(len(p["terms"]), 3)
        self.assertIn("【折扣對象外商品】", p["terms"][1])
        self.assertEqual(p["couponLinks"], ["https://japanportal.donki-global.com/coupon/?ptcd=1"])
        self.assertEqual(p["couponImage"], "https://resources.matcha-jp.com/coupon/720x2000/c.jpg")
        self.assertEqual(p["logo"], "https://resources.matcha-jp.com/coupon/330x2000/logo.png")

    def test_missing_fields_are_unknown(self):
        p = c.parse_coupon_page(COUPON_NO_DATES)
        item = c.build_item({"key": "x", "store": None, "category": "其他", "url": "u"}, p, "2026-11-25", False)
        for k in ("discount", "threshold", "usage", "validUntil"):
            self.assertEqual(item[k], c.UNKNOWN, k)
        self.assertEqual(item["store"], "某店")
        self.assertEqual(p["terms"], ["1. 每次結帳僅限使用一張。", "2. 請於結帳時出示本優惠券。"])

    def test_threshold_variants(self):
        lines = ["店內商品單筆消費滿10,000日圓、未滿30,000日圓（未稅），再享3%折扣",
                 "店内商品税抜1万円以上のお買い上げで3％OFF",
                 "消費日幣1萬以上，享免稅 10% + 3%折扣",
                 "・每次購物的最高折扣金額為 10,000 日圓",
                 "AIRPORT TAXI ¥500折扣"]
        got = c.threshold_from(lines).split("\n")
        self.assertEqual(got, lines[:3])  # 折扣上限不是門檻

    def test_tax_free_threshold_counts(self):
        self.assertEqual(c.threshold_from(["9. 辦理免稅時，購買金額須達5,000日圓（未稅）以上。"]),
                         "辦理免稅時，購買金額須達5,000日圓（未稅）以上。")

    def test_article_page(self):
        p = c.parse_article_page(ARTICLE)
        item = c.build_item({"key": "bic-camera", "store": "Bic Camera", "offer": "最高17%折扣",
                             "category": "電器行", "url": "https://matcha-jp.com/tw/17389"}, p, "2026-11-25", False)
        self.assertEqual(item["discount"], "最高17%折扣")
        self.assertTrue(item["threshold"].startswith("現在使用優惠券"))
        self.assertNotIn("\n", item["threshold"])  # 文章重複的說明只取一次
        self.assertEqual((item["validUntil"], item["usage"]), (c.UNKNOWN, c.UNKNOWN))  # 只在券圖裡，不推測
        self.assertEqual(item["couponImage"], "https://resources.matcha-jp.com/original/2026/10/30-1.webp")
        self.assertIsNone(item["couponLink"])

    def test_frame_blocked(self):
        def h(**kv):
            m = Message()
            for k, v in kv.items():
                m[k.replace("_", "-")] = v
            return m
        self.assertTrue(c.frame_blocked(h(Content_Security_Policy="frame-ancestors 'self' https://*.matcha-jp.com")))
        self.assertTrue(c.frame_blocked(h(X_Frame_Options="SAMEORIGIN")))
        self.assertFalse(c.frame_blocked(h()))
        self.assertFalse(c.frame_blocked(h(Content_Security_Policy="frame-ancestors *")))


def item(i, **kw):
    base = {"id": f"c{i}", "store": f"店{i}", "url": f"u{i}", "discount": "5%", "validUntil": "2027-01-01"}
    base.update(kw)
    return base


class HealthAndScheduleTest(unittest.TestCase):
    def test_health(self):
        good = [item(i) for i in range(10)]
        self.assertEqual(c.health_check(good, good, []), [])
        self.assertTrue(c.health_check(good[:5], good, []))  # 少超過 30%
        self.assertTrue(c.health_check([], good, []))
        broken = [item(i, discount=c.UNKNOWN, validUntil=c.UNKNOWN) for i in range(10)]
        self.assertTrue(c.health_check(broken, good, []))  # 券頁改版

    def test_failed_run_keeps_previous(self):
        prev = {"updatedAt": "2026-08-01T00:00:00+00:00", "items": [item(1)], "count": 1}
        orig = c.fetch
        c.fetch = lambda only=None: (_ for _ in ()).throw(RuntimeError("網站改版"))  # noqa
        try:
            out = c.run(prev)
        finally:
            c.fetch = orig
        self.assertEqual(out["items"], prev["items"])
        self.assertEqual(out["updatedAt"], prev["updatedAt"])
        self.assertFalse(out["lastRun"]["ok"])
        self.assertIn("網站改版", out["lastRun"]["error"])

    def test_needs_update(self):
        d = {"updatedAt": "2026-11-01T00:00:00+00:00", "lastRun": {"ok": True},
             "items": [item(1, validUntil="2027-03-31"), item(2, validUntil=c.UNKNOWN)]}
        self.assertFalse(c.needs_update(d, date(2026, 11, 25))[0])
        self.assertTrue(c.needs_update(d, date(2027, 1, 30))[0])  # 滿 90 天
        d2 = {**d, "items": [item(1, validUntil="2026-12-31")]}
        self.assertTrue(c.needs_update(d2, date(2027, 1, 2))[0])  # 上次抓取後過期
        d3 = {**d, "items": [item(1, validUntil="2026-10-31")]}  # 抓的時候就已過期：不每週重抓
        self.assertFalse(c.needs_update(d3, date(2026, 11, 25))[0])
        self.assertTrue(c.needs_update({**d, "lastRun": {"ok": False}}, date(2026, 11, 2))[0])
        self.assertTrue(c.needs_update(None)[0])


if __name__ == "__main__":
    unittest.main()


class FetchTest(unittest.TestCase):
    def test_redirected_coupon_is_dropped(self):
        pages = {
            "https://matcha-jp.com/tw/coupon/11": (COUPON, "https://matcha-jp.com/tw/coupon/11"),
            "https://matcha-jp.com/tw/coupon/148": ("", "https://matcha-jp.com/tw/coupon"),  # 券已結束
            "https://matcha-jp.com/tw/17389": (ARTICLE, "https://matcha-jp.com/tw/17389"),
            "https://matcha-jp.com/tw/coupon/5": (COUPON, "https://matcha-jp.com/tw/coupon/5"),
        }
        orig = (c.http.request, c.http.request_full)
        c.http.request = lambda url: INDEX.encode()
        c.http.request_full = lambda url: (pages[url][0].encode(), Message(), pages[url][1])
        try:
            items, errors, removed = c.fetch()
        finally:
            c.http.request, c.http.request_full = orig
        self.assertEqual([x["id"] for x in items], ["don-quijote", "bic-camera", "lotte"])
        self.assertEqual(errors, [])
        self.assertEqual(len(removed), 1)
