import json
import os
import tempfile
import unittest

from crawler import adastria, fastretailing, health, issues, japan, montbell, muji, nitori


def fr_product(code, pc, name, origin, current, styles, colors=None, pic="/hmall/test/x/1.jpg"):
    return {"code": code, "productCode": pc, "name": name, "originPrice": origin, "minPrice": current,
            "maxPrice": current, "styleText": styles, "colorNums": colors or styles, "mainPic": pic,
            "levelOne": [{"name": "T恤"}]}


class FastRetailingTest(unittest.TestCase):
    def test_merges_split_sale_listing(self):
        ps = [
            fr_product("483457", "u1", "AIRism棉質T恤(短袖) 474405", 390, 390,
                       ["483457 / 00 WHITE", "474405 / 09 BLACK", "38 DARK BROWN"]),
            fr_product("483457", "u2", "AIRism棉質T恤(短袖) 474405", 390, 190, ["483457 / 10 PINK"]),
            fr_product("488298", "u3", "羅紋連帽上衣(長袖)", 590, 590, ["01 OFF WHITE"]),
        ]
        recs = fastretailing.transform("UQ", ps)
        self.assertEqual([r["id"] for r in recs], ["483457", "488298"])
        r = recs[0]
        self.assertEqual(r["name"], "AIRism棉質T恤(短袖)")
        self.assertEqual(r["altIds"], ["474405"])
        self.assertEqual((r["price"], r["salePrice"], r["maxPrice"]), (390, 190, 390))
        self.assertEqual(r["url"], "https://www.uniqlo.com/tw/zh_TW/product-detail.html?productCode=u1")
        self.assertEqual(r["image"], "https://www.uniqlo.com/tw/hmall/test/x/1.jpg")
        black = [v for v in r["variants"] if v["color"] == "09 BLACK"][0]
        self.assertEqual(black["ids"], ["474405"])
        brown = [v for v in r["variants"] if v["color"] == "38 DARK BROWN"][0]
        self.assertEqual(brown["ids"], ["483457"])
        pink = [v for v in r["variants"] if v["color"] == "10 PINK"][0]
        self.assertEqual((pink["salePrice"], pink["url"][-2:]), (190, "u2"))
        self.assertNotIn("url", black)  # 和商品連結相同就省略
        self.assertIsNone(recs[1]["salePrice"])

    def test_audience_from_top_categories(self):
        p = fr_product("488298", "u1", "羅紋連帽上衣", 590, 590, ["01 OFF WHITE"])
        p["topCategories"] = [{"name": "全商品"}, {"name": "女裝"}, {"name": "男裝"}]
        kid = fr_product("123456", "u2", "童裝T恤", 290, 290, ["01 WHITE"])
        kid["gender"] = "女童"
        recs = {r["id"]: r for r in fastretailing.transform("UQ", [p, kid])}
        self.assertEqual(recs["488298"]["audience"], ["女", "男"])
        self.assertEqual(recs["123456"]["audience"], ["童"])
        g = fr_product("361311", "u3", "男女適穿 拉鍊針織外套", 1290, 1290, ["09 BLACK"])
        g["topCategories"] = [{"name": "WOMEN"}, {"name": "MEN"}]
        self.assertEqual(fastretailing.transform("GU", [g])[0]["audience"], ["女", "男"])

    def test_gu_uses_gu_domain(self):
        r = fastretailing.transform("GU", [fr_product("362202", "u9", "透膚圓點T恤(長袖)", 290, 290, ["09 BLACK"])])[0]
        self.assertEqual(r["brand"], "GU")
        self.assertTrue(r["url"].startswith("https://www.gu-global.com/tw/"))


PDP_HTML = (
    '<script>var x = {"SKUPropertySetList":[{"PropertyNameSet":"尺寸:S","OuterId":"4550723297400"},'
    '{"PropertyNameSet":"尺寸:M","OuterId":"4550723297417"}],"CategoryLevelName": {"Level1_ShopCategory_Name":"1_衣料雜貨",'
    '"Level3_ShopCategory_Name":"18_女襪","Level4_ShopCategory_Name":null},'
    '"SalePageGroup":{"GroupTitle":"顏色","SalePageItems":[{"SalePageId":101,"GroupItemTitle":"柔白"},'
    '{"SalePageId":102,"GroupItemTitle":"淺粉"}]}};</script>'
)


def muji_page(sid, title, price, suggest, jan, cat="女裝", themed=False):
    return {"salePageId": sid, "title": title, "picUrl": f"//img.91app.com/{sid}", "price": price,
            "suggestPrice": suggest, "skuOuterId": jan, "_category": cat, "_themed": themed}


class MujiTest(unittest.TestCase):
    def test_parse_salepage(self):
        info = muji.parse_salepage(PDP_HTML)
        self.assertEqual(info["jans"], ["4550723297400", "4550723297417"])
        self.assertEqual(info["category"], "女襪")
        self.assertEqual(info["group"], [[101, "柔白"], [102, "淺粉"]])

    def test_transform_merges_colors_and_uses_cache(self):
        pages = {
            101: muji_page(101, "女T恤柔白", 490.0, 490.0, "4550000000001"),
            102: muji_page(102, "女T恤淺粉", 392.0, 490.0, "4550000000101"),
            200: muji_page(200, "原子筆", 15.0, 15.0, None, cat="SALE｜生活雜貨", themed=True),
        }
        groups = {101: (101, "柔白"), 102: (101, "淺粉")}
        cache = {"102": {"jans": ["4550000000101", "4550000000118"], "category": "女上衣", "group": []}}
        recs = {r["url"][-3:]: r for r in muji.transform(pages, groups, cache)}
        t = recs["101"]
        self.assertEqual(t["id"], "4550000000001")
        self.assertEqual(t["altIds"], ["4550000000101", "4550000000118"])
        self.assertEqual(t["name"], "女T恤")
        self.assertEqual((t["price"], t["salePrice"], t["maxPrice"]), (490, 392, 490))
        self.assertEqual(t["category"], "女裝")
        self.assertEqual(t["image"], "https://img.91app.com/101")
        self.assertEqual(len(t["variants"]), 2)
        pen = recs["200"]
        self.assertEqual(pen["id"], "200")  # 沒有 JAN 就用商品頁 ID
        self.assertEqual(pen["category"], "")  # 行銷分類不當 category

    def test_duplicate_listing_merged(self):
        pages = {300: muji_page(300, "女針織衫", 1190.0, 1190.0, "9"), 301: muji_page(301, "女針織衫", 1190.0, 1190.0, "9")}
        recs = muji.transform(pages, {}, {"300": {"jans": ["9", "10"]}, "301": {"jans": ["9", "10"]}})
        self.assertEqual(len(recs), 1)
        self.assertEqual(len(recs[0]["variants"]), 1)
        self.assertEqual(recs[0]["url"], "https://shop.muji.tw/SalePage/Index/300")

    def test_audience_from_title(self):
        self.assertEqual(muji._audience("女棉保暖厚織U領八分袖T恤"), ["女"])
        self.assertEqual(muji._audience("男抗撕裂工作短褲"), ["男"])
        self.assertEqual(muji._audience("兒童棉保暖圓領長袖T恤"), ["童"])
        self.assertEqual(muji._audience("幼兒棉混圓領T恤"), ["嬰"])
        self.assertEqual(muji._audience("聚丙烯檔案盒"), [])

    def test_strip_color_separator(self):
        self.assertEqual(muji._strip_color("手工茶香豆干-辣味", "辣味"), "手工茶香豆干")

    def test_group_from_cache_when_listing_lacks_it(self):
        pages = {101: muji_page(101, "女T恤柔白", 490.0, 490.0, "1"), 102: muji_page(102, "女T恤淺粉", 490.0, 490.0, "2")}
        cache = {"101": {"jans": ["1"], "category": "", "group": [[101, "柔白"], [102, "淺粉"]]}}
        recs = muji.transform(pages, {}, cache)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["name"], "女T恤")


def rec(i, price=500, sale=None):
    return {"id": str(i), "name": "x", "price": price, "salePrice": sale,
            "maxPrice": sale if sale is not None else price, "url": "u",
            "variants": [{"price": price, "salePrice": sale}]}


class HealthTest(unittest.TestCase):
    def test_ok_and_drops_few_bad_prices(self):
        records = [rec(i) for i in range(99)] + [rec(99, price=5)]
        ok, errors, kept, bad = health.check_products(records, 100)
        self.assertTrue(ok, errors)
        self.assertEqual(len(kept), 99)
        self.assertEqual([r["id"] for r in bad], ["99"])

    def test_too_many_bad_prices(self):
        records = [rec(i) for i in range(90)] + [rec(i, price=600, sale=700) for i in range(90, 100)]
        ok, errors, _, _ = health.check_products(records, None)
        self.assertFalse(ok)
        self.assertIn("價格不合理", errors[0])

    def test_count_drop(self):
        ok, errors, _, _ = health.check_products([rec(i) for i in range(79)], 100)
        self.assertFalse(ok)
        self.assertIn("少超過 20%", errors[0])
        self.assertTrue(health.check_products([rec(i) for i in range(80)], 100)[0])

    def test_missing_fields(self):
        records = [rec(i) for i in range(94)] + [dict(rec(i), name="") for i in range(94, 100)]
        self.assertFalse(health.check_products(records, None)[0])

    def test_empty(self):
        self.assertFalse(health.check_products([], None)[0])

    def test_fx(self):
        self.assertTrue(health.check_fx({"rate": 0.205}, {"rate": 0.204})[0])
        self.assertFalse(health.check_fx({"rate": 0.31}, None)[0])
        self.assertFalse(health.check_fx({"rate": 0.22}, {"rate": 0.205})[0])  # +7.3%


class IssuesTest(unittest.TestCase):
    def test_write_output_for_actions(self):
        with tempfile.NamedTemporaryFile("r+", encoding="utf-8", delete=False) as f:
            path = f.name
        os.environ["GITHUB_OUTPUT"] = path
        try:
            issues.write_output("new_issues", [{"brand": "GU", "number": 3, "errors": ["壞了"]}])
            with open(path, encoding="utf-8") as f:
                line = f.read().strip()
        finally:
            del os.environ["GITHUB_OUTPUT"]
            os.remove(path)
        name, value = line.split("=", 1)
        self.assertEqual(name, "new_issues")
        self.assertEqual(json.loads(value)[0]["number"], 3)

    def test_write_output_noop_locally(self):
        os.environ.pop("GITHUB_OUTPUT", None)
        issues.write_output("new_issues", [])  # 不應出錯


class NitoriTest(unittest.TestCase):
    def test_transform_per_sku_prices(self):
        items = {"7950285s": ({
            "itemNo": "7950285s", "skunos": ["7950285", "7950283"], "name": "巧拼地墊 N VT01-N ",
            "skusPrice": [{"listPrice": 199, "salePrice": 179}, {"listPrice": 299, "salePrice": 299}],
            "skusColor": [{"colorName": ["淺棕", ""]}, {"colorName": ["中灰色", ""]}],
            "imageUrl": "https://x/7950285_01.jpg"}, "地毯．地墊"),
            "2116100000043s": ({"itemNo": "2116100000043s", "skunos": ["2116100000043"], "name": "幼兒枕",
                                "skusPrice": [{"listPrice": 399, "salePrice": 399}], "skusColor": [], "imageUrl": ""}, "網購限定")}
        recs = {r["id"]: r for r in nitori.transform(items)}
        r = recs["7950285"]
        self.assertEqual(r["altIds"], ["7950283"])
        self.assertEqual((r["price"], r["salePrice"], r["maxPrice"]), (299, 179, 299))
        self.assertEqual([v["color"] for v in r["variants"]], ["淺棕", "中灰色"])
        self.assertEqual(r["url"], "https://www.nitori-net.tw/product/7950285s")
        self.assertEqual(r["name"], "巧拼地墊 N VT01-N")
        self.assertEqual(r["category"], "地毯．地墊")
        t = recs["2116100000043"]  # 沒有 7 位數編號就用台灣店內碼
        self.assertIsNone(t["salePrice"])
        self.assertEqual(t["category"], "")  # 行銷分類不當 category


class AdastriaTest(unittest.TestCase):
    def test_split_title(self):
        self.assertEqual(adastria.split_title("GW", "GLOBAL WORK女法蘭絨格紋襯衫上衣-二色-1074909"),
                         ("女法蘭絨格紋襯衫上衣", "1074909", ["女"]))
        self.assertEqual(adastria.split_title("NIKO", "niko and防寒保暖毛絨坐墊-二色-1066038"),
                         ("防寒保暖毛絨坐墊", "1066038", []))
        self.assertEqual(adastria.split_title("GW", "GLOBAL WORK男女適穿刷毛外套-1000001")[2], ["女", "男"])

    def test_transform_uses_code_and_cached_barcodes(self):
        pages = {12257970: {"salePageId": 12257970, "title": "GLOBAL WORK女法蘭絨格紋襯衫上衣-二色-1074909",
                            "price": 903.0, "suggestPrice": 1290.0, "skuOuterId": "1900024793829", "picUrl": "//img/1"}}
        cache = {"12257970": {"barcodes": ["1900024793829", "1900024793850"]}}
        r = adastria.transform("GW", pages, cache)[0]
        self.assertEqual(r["id"], "1074909")
        self.assertEqual(r["altIds"], ["1900024793829", "1900024793850"])
        self.assertEqual((r["price"], r["salePrice"]), (1290, 903))
        self.assertEqual(r["url"], "https://www.dot-st.tw/SalePage/Index/12257970")
        self.assertEqual(r["image"], "https://img/1")


class MontbellTest(unittest.TestCase):
    PRODUCT = {"id": 66411219, "handle": "wind-1103242", "title": "WIND BLAST PK男款連帽風衣#1103242",
               "featured_image": {"large": "//cdn/x.jpg"},
               "variants": [{"sku": "1103242BK-M", "option1": "BK黑", "price": 2480.0, "compare_at_price": None},
                            {"sku": "1103242BK-L", "option1": "BK黑", "price": 2480.0, "compare_at_price": None},
                            {"sku": "1103242NV-M", "option1": "NV藍", "price": 1990.0, "compare_at_price": 2480.0}]}

    def test_parse_and_transform(self):
        c = dict(montbell.parse_product(self.PRODUCT), fetched="2026-10-27")
        self.assertEqual(c["image"], "https://cdn/x.jpg")
        r = montbell.transform({"wind-1103242": c})[0]
        self.assertEqual(r["id"], "1103242")
        self.assertEqual(r["name"], "WIND BLAST PK男款連帽風衣")
        self.assertEqual((r["price"], r["salePrice"], r["maxPrice"]), (2480, 1990, 2480))
        self.assertEqual([(v["color"], v["salePrice"]) for v in r["variants"]], [("BK黑", None), ("NV藍", 1990)])
        self.assertEqual(r["audience"], ["男"])
        self.assertEqual(r["checkedAt"], "2026-10-27")
        self.assertEqual(r["url"], "https://www.montbell.com.tw/products/wind-1103242")

    def test_skips_products_without_code(self):
        c = montbell.parse_product({"id": 1, "handle": "gift", "title": "禮物卡", "variants": [{"price": 500.0}]})
        self.assertEqual(montbell.transform({"gift": c}), [])

    def test_update_cache_prefers_missing(self):
        calls = []
        orig = montbell.http.get_json
        montbell.http.get_json = lambda url, **kw: calls.append(url) or {"id": 9, "handle": url, "variants": []}
        try:
            cache = {"old": {"id": 1, "handle": "old", "fetched": "2026-01-01"}, "gone": {"id": 2, "fetched": "2026-01-01"}}
            cache, done, missing = montbell.update_cache(cache, ["old", "new"], 1)
        finally:
            montbell.http.get_json = orig
        self.assertEqual((done, missing), (1, 0))
        self.assertTrue(calls[0].endswith("/products/new.json"))
        self.assertNotIn("gone", cache)


class JapanTest(unittest.TestCase):
    def _item(self, group, price, promo, colors):
        return {"productId": "E475367-000", "priceGroup": group, "name": "エアリズムコットンカノコポロシャツ",
                "prices": {"base": {"value": price}, "promo": {"value": price} if promo else None},
                "colors": [{"displayCode": c[:2], "name": c[3:]} for c in colors]}

    def test_merges_sale_colours_into_one_code(self):
        items = [self._item("00", 2990, False, ["00 WHITE", "09 BLACK"]), self._item("03", 790, True, ["11 PINK"])]
        r = japan.transform_fr("UQ", items)["475367"]
        self.assertEqual(r["url"], "https://www.uniqlo.com/jp/ja/products/E475367-000/00")
        self.assertEqual(r["variants"], [
            {"color": "00 WHITE", "price": 2990, "sale": False},
            {"color": "09 BLACK", "price": 2990, "sale": False},
            {"color": "11 PINK", "price": 790, "sale": True}])

    def test_health_drops_bad_prices_and_checks_count(self):
        good = {"name": "a", "url": "u", "variants": [{"color": "", "price": 1990, "sale": False}]}
        bad = {"name": "b", "url": "u", "variants": [{"color": "", "price": 0, "sale": False}]}
        records = {str(i): good for i in range(30)} | {"x": bad}
        ok, errors, kept = health.check_jp(records, 30)
        self.assertTrue(ok)
        self.assertNotIn("x", kept)
        ok, errors, kept = health.check_jp(records, 100)
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
