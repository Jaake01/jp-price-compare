import unittest

from crawler import fastretailing, health, muji


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


if __name__ == "__main__":
    unittest.main()
