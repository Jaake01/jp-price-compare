"""每日資料更新主程式。

用法：python -m crawler.run --prev 上次資料目錄 --out 輸出目錄 --report report.json

每個品牌獨立處理：抓取 → 健康檢查 → 通過就寫出新資料，否則沿用上次資料。
任何一個品牌失敗都不影響其他品牌。結果寫到 report.json，給開 Issue 的步驟使用。
"""
import argparse
import json
import os
import shutil
import sys
import traceback
from datetime import datetime, timezone

from . import fastretailing, fx, health, muji

BRANDS = ["uq", "gu", "muji", "fx"]
MUJI_CACHE = "muji_cache.json"


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _products_file(brand, records):
    return {"brand": brand, "updatedAt": _now(), "count": len(records), "items": records}


def run_brand(key, args, prev_dir):
    """回傳 (資料物件, 健康檢查錯誤列表, 附註列表)。"""
    if args.force_fail == key:
        raise RuntimeError("手動觸發的測試失敗（--force-fail）")
    sample = args.sample
    notes = []
    if key in ("uq", "gu"):
        brand = key.upper()
        products, total = fastretailing.fetch(brand, max_pages=1 if sample else None)
        if not sample and len(products) < total:
            raise RuntimeError(f"只抓到 {len(products)}/{total} 筆")
        records = fastretailing.transform(brand, products)
    elif key == "muji":
        pages, groups = muji.fetch_listing(max_categories=2 if sample else None,
                                           max_pages=1 if sample else None)
        cache = _load(os.path.join(prev_dir, MUJI_CACHE)) or {}
        cache, done, remaining = muji.update_cache(cache, pages, args.muji_pdp_limit)
        _write(os.path.join(args.out, MUJI_CACHE), cache)
        notes.append(f"商品頁補 JAN：本次 {done} 頁，尚餘 {remaining} 頁")
        records = muji.transform(pages, groups, cache)
        brand = "MUJI"
    else:
        data = fx.fetch()
        ok, errors = health.check_fx(data, _load(os.path.join(prev_dir, "fx.json")))
        return dict(data, updatedAt=_now()), errors, notes
    prev = _load(os.path.join(prev_dir, f"{key}.json"))
    ok, errors, kept, bad = health.check_products(records, None if sample else (prev or {}).get("count"))
    if ok and bad:
        notes.append(f"剔除 {len(bad)} 筆價格不合理的商品：" +
                     "、".join(f"{r['id']}（{r['price']}/{r['salePrice']}）" for r in bad[:20]))
    return _products_file(brand, kept), errors, notes


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--prev", default="prev", help="上次的資料目錄（可不存在）")
    ap.add_argument("--out", default="out")
    ap.add_argument("--report", default="report.json")
    ap.add_argument("--brands", default=",".join(BRANDS))
    ap.add_argument("--force-fail", default="", help="測試用：讓指定品牌失敗")
    ap.add_argument("--muji-pdp-limit", type=int, default=500, help="每次最多抓幾個 MUJI 商品頁補 JAN")
    ap.add_argument("--sample", action="store_true", help="只抓少量資料，確認連得上（不做商品數檢查）")
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)

    # 先把上次的資料全部複製過去，成功的品牌再覆蓋
    if os.path.isdir(args.prev):
        for name in os.listdir(args.prev):
            if name.endswith(".json"):
                shutil.copy2(os.path.join(args.prev, name), args.out)

    report = {"startedAt": _now(), "results": []}
    for key in [b.strip() for b in args.brands.split(",") if b.strip()]:
        print(f"== {key}", flush=True)
        result = {"brand": key.upper(), "ok": False, "errors": [], "notes": []}
        try:
            data, errors, notes = run_brand(key, args, args.prev)
            result["notes"] = notes
            if errors:
                result["errors"] = errors
            else:
                _write(os.path.join(args.out, f"{key}.json"), data)
                result["ok"] = True
                result["count"] = data.get("count")
        except Exception as e:  # 單一品牌失敗不影響其他品牌
            traceback.print_exc()
            result["errors"] = [f"{type(e).__name__}: {e}"]
        status = "OK" if result["ok"] else "FAIL（沿用上次資料）"
        print(f"   {status} {result.get('count', '')} {result['errors']} {result['notes']}", flush=True)
        report["results"].append(result)
    report["finishedAt"] = _now()
    _write(args.report, report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
