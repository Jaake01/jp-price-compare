# jp-price-compare
在日本相同的商品，和台灣官網價格快速比價的工具

規格見 [SPEC.md](SPEC.md)，資料來源探勘見 [docs/recon.md](docs/recon.md)。

## 網頁（第 3 階段）

`web/` 是手機網頁（PWA），純 HTML／JS，不需要建置。`.github/workflows/pages.yml` 會把它和 `data` 分支的最新資料一起發布到 GitHub Pages：
推送 `web/` 到 main、或每日資料更新跑完時自動發布。

**第一次要先開啟 Pages**：儲存庫 Settings → Pages → Build and deployment 的 Source 選「GitHub Actions」。

**本機預覽**：

```sh
mkdir -p web/data && for f in uq gu muji fx; do git show origin/data:$f.json > web/data/$f.json; done
cd web && python3 -m http.server 8000   # 開 http://localhost:8000
node --test web/tests/*.test.mjs        # 計算與搜尋的測試（在專案根目錄執行）
```

## 每日資料更新

GitHub Actions（`.github/workflows/update-data.yml`）每天台灣時間 05:37 執行，結果發布到 `data` 分支：

| 檔案 | 內容 |
| --- | --- |
| `uq.json`、`gu.json`、`muji.json`、`nitori.json`、`gw.json`、`niko.json`、`montbell.json` | 各品牌商品（格式見 SPEC.md「資料規格」） |
| `uq_jp.json`、`gu_jp.json` | UNIQLO、GU 日本官網價格（以 6 位數編號為鍵） |
| `fx.json` | 日圓匯率 |
| `muji_cache.json` | MUJI 各商品頁的全部尺寸 JAN 快取 |
| `gw_cache.json`、`niko_cache.json` | GLOBAL WORK、niko and ... 各商品頁的各色各尺寸條碼快取 |
| `montbell_cache.json` | mont-bell 單品資料快取（每天輪流更新約 250 款） |

某個品牌健康檢查沒過時，沿用上一份資料，並自動開一個「[資料更新失敗] 品牌名」的 Issue；之後成功會自動關閉。

**手動執行**：Actions → 每日資料更新 → Run workflow。可選「讓一個品牌故意失敗」來測試失敗處理。

**自動修復（選用）**：新開失敗 Issue 時，會讓 Claude 試著修爬蟲，並在 Issue 留言附上建立 PR 的連結。要啟用的話：

1. 在自己電腦安裝 Claude Code 後執行 `claude setup-token`，取得長效權杖（使用你的 Claude 訂閱額度）。
2. 儲存庫 Settings → Secrets and variables → Actions → New repository secret，名稱 `CLAUDE_CODE_OAUTH_TOKEN`，貼上權杖。也可以改用 Anthropic API 金鑰，名稱 `ANTHROPIC_API_KEY`（依用量付費）。
3. 測試：手動執行時選一個品牌故意失敗，並勾選「故意失敗時也測試自動修復」。這種測試 Claude 不會改程式，只會在 Issue 留言說明。

**本機執行**（只需要 Python 3.10 以上，不用安裝套件）：

```sh
python -m unittest                      # 單元測試
python -m crawler.run --sample          # 每個品牌只抓少量資料，確認連得上
python -m crawler.run --prev 上次資料目錄 --out out --muji-pdp-limit 20
```
