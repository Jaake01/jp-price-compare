import json
import os
import unittest
from email.message import Message
from unittest import mock

from crawler import coupon_vision as v


class VisionTest(unittest.TestCase):
    def test_extract_json(self):
        self.assertEqual(v._extract_json('好的：\n{"a": {"b": 1}} 以上'), {"a": {"b": 1}})
        with self.assertRaises(ValueError):
            v._extract_json("沒有 JSON")

    def test_clean_info(self):
        info = v._clean_info({"hasBarcode": True, "validUntil": "2027/04/30", "tiers": [
            {"condition": "未稅滿 ¥5,000", "discount": "7% OFF", "items": "家電"}, {"condition": "", "discount": None}, "x"],
            "excludes": " Apple 產品 ", "notes": None, "extra": "ignored"})
        self.assertEqual(info["validUntil"], None)  # 格式不對就不收
        self.assertEqual(info["tiers"], [{"condition": "未稅滿 ¥5,000", "discount": "7% OFF", "items": "家電"}])
        self.assertEqual(info["excludes"], "Apple 產品")
        self.assertNotIn("extra", info)
        self.assertIsNone(v._clean_info("not a dict"))

    def test_run_reads_new_images_once_and_applies(self):
        data = {"items": [{"id": "a", "couponImage": "https://img/a.jpg"},
                          {"id": "b", "couponImage": "https://img/b.webp"},
                          {"id": "c", "couponImage": "https://img/a.jpg"},  # 同一張圖只讀一次
                          {"id": "d", "couponImage": None}]}
        cache = {"https://img/b.webp": {"info": {"tiers": [], "hasBarcode": False}}}
        seen = []

        def fake_read(paths, model, workdir):
            seen.extend(os.path.basename(p) for p in paths)
            return {os.path.basename(paths[0]): {"hasBarcode": True, "validUntil": "2027-04-30", "tiers": []}}

        with mock.patch.object(v.http, "request_full", lambda u, timeout=60: (b"img", Message(), u)), \
                mock.patch.object(v, "read_batch", fake_read):
            done, errors = v.run(data, cache, "m", limit=10)
        self.assertEqual((done, errors), (1, []))
        self.assertEqual(seen, ["coupon1.jpg"])
        self.assertEqual(data["items"][0]["imageInfo"]["validUntil"], "2027-04-30")
        self.assertEqual(data["items"][2]["imageInfo"], data["items"][0]["imageInfo"])
        self.assertIn("imageInfo", data["items"][1])
        self.assertNotIn("imageInfo", data["items"][3])
        json.dumps(cache)  # 可存檔

    def test_skips_without_token(self):
        import tempfile
        d = tempfile.mkdtemp()
        data_p, cache_p = os.path.join(d, "c.json"), os.path.join(d, "v.json")
        with open(data_p, "w") as f:
            json.dump({"items": [{"id": "a", "couponImage": "u"}]}, f)
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": ""}):
            self.assertEqual(v.main(["--data", data_p, "--cache", cache_p]), 0)
        with open(cache_p) as f:
            self.assertEqual(json.load(f), {})


if __name__ == "__main__":
    unittest.main()
