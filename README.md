# jp-price-compare
在日本相同的商品，和台灣官網價格快速比價的工具

規格見 [SPEC.md](SPEC.md)，資料來源探勘見 [docs/recon.md](docs/recon.md)。

## 每日資料更新

GitHub Actions（`.github/workflows/update-data.yml`）每天台灣時間 06:00 執行，結果發布到 `data` 分支：

| 檔案 | 內容 |
| --- | --- |
| `uq.json`、`gu.json`、`muji.json` | 各品牌商品（格式見 SPEC.md「資料規格」） |
| `fx.json` | 日圓匯率 |
| `muji_cache.json` | MUJI 各商品頁的全部尺寸 JAN 快取 |

某個品牌健康檢查沒過時，沿用上一份資料，並自動開一個「[資料更新失敗] 品牌名」的 Issue；之後成功會自動關閉。

**手動執行**：Actions → 每日資料更新 → Run workflow。可選「讓一個品牌故意失敗」來測試失敗處理。

**本機執行**（只需要 Python 3.10 以上，不用安裝套件）：

```sh
python -m unittest                      # 單元測試
python -m crawler.run --sample          # 每個品牌只抓少量資料，確認連得上
python -m crawler.run --prev 上次資料目錄 --out out --muji-pdp-limit 20
```
