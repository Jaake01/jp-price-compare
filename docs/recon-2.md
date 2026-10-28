# 新增品牌探勘：宜得利、GLOBAL WORK、niko and...、mont-bell

探勘日期：2026-10-27
方式：和 `docs/recon.md` 相同，呼叫網站自己用的 API，用瀏覽器記錄網路請求找出 API；間隔 1.5–2 秒，四站合計約 60 次請求。

## 結論

| 品牌 | 台灣官網 | 平台 | 商品數 | 原價／特價 | 編號 | 台日編號一致？ | 每日請求數 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 宜得利 NITORI | www.nitori-net.tw | 自建（Next.js＋API） | 5,660 款／9,552 品項 | ✅ `listPrice`／`salePrice` | 7 位數商品編號（約 52%）；其餘是台灣 13 位數店內碼 | ✅ 抽 2 筆，日本官網同編號是同一件 | 約 25 |
| GLOBAL WORK | www.dot-st.tw（and ST TW） | 91APP（同 MUJI） | 797 款 | ✅ `suggestPrice`／`price` | 7 位數「商品貨號」＋各色各尺寸 13 位數條碼 | ⚠️ 日本官網從雲端被擋，未驗證 | 約 10 |
| niko and ... | 同上 | 同上 | 1,844 款 | ✅ | 同上 | ⚠️ 同上 | 約 20 |
| mont-bell | www.montbell.com.tw | Cyberbiz | 1,676 款 | ✅ 單品 JSON（列表頁價格不可靠） | 7 位數品番（如 #1101493）＋SKU（品番＋色＋尺寸） | ✅ 抽 2 筆，日本官網同品番是同一件 | 見下 |

四個都能做，資料都從 JSON 取得，不用解析畫面。

## 各品牌細節

### 宜得利（www.nitori-net.tw）

- 商品列表：`POST https://frontendapi-ggazgncacwcqc8bt.z01.azurefd.net/api/Category/GetCategoryFilter`，body 帶 `categoryId`。**大分類會連同所有子分類一起回傳**，所以 24 個大分類各請求一次就能抓完。
- 每筆有 `skunos`（編號，多色多尺寸時有多個）、`name`、`skusPrice[{listPrice, salePrice}]`、`imageUrl`；特價約 1,984 款。
- 商品頁網址：`https://www.nitori-net.tw/product/{編號}s`。
- 編號：4,981 個是 7 位數（和日本宜得利的「商品コード」相同）。另外 3,762 個是 `211…` 開頭的 13 位數台灣店內碼，多是 DECO HOME 和台灣限定商品，日本吊牌不會有，只能用品名搜尋。
- 驗證：`7980716`（純棉嬰兒用枕 IB001，NT$699→629）、`7550863`（蝶型記憶枕 P2304），日本官網同編號就是同一件。
- robots.txt 只禁止 `/member/`、`/cart/`。API 在另一個網域，沒有 robots.txt。

### GLOBAL WORK、niko and...（www.dot-st.tw，shop id 36426）

- 和 MUJI 同樣是 91APP，可以共用 `crawler/muji.py` 的 GraphQL 列表邏輯（改成可設定 shop id 和分類）。
- 品牌分類：GLOBAL WORK `218807`、niko and ... `245719`。
- 和 MUJI 不同：**一個商品頁就是一款**，多色多尺寸都在同一頁，不用再合併顏色。
- 編號：
  - 品名結尾就有 7 位數商品貨號，例如「GLOBAL WORK女法蘭絨格紋襯衫上衣-二色-1074909」，商品說明也寫「商品貨號：1074909」。
  - 各色各尺寸另有 13 位數條碼（例如 `1900024793829`），列表只給第一個，其他要像 MUJI 一樣從商品頁補（同樣的快取做法）。
- 原價 `suggestPrice`、售價 `price`（例如 1290→903）。
- 同站還有 LOWRYS FARM、LAKOLE、studio CLIP 等 Adastria 品牌，之後要加很容易。
- ⚠️ 日本 and ST（dot-st.com）從這個環境被擋（403），無法確認日本吊牌上的品番、條碼是否和台灣一樣。要到店內實測。

### mont-bell（www.montbell.com.tw）

- Cyberbiz 平台，sitemap 有 1,676 個商品頁。
- 單品 JSON：`/products/{handle}.json`，有每個 SKU 的 `sku`（例如 `1604177DKMA-L`＝品番＋顏色＋尺寸）、`price`、`compare_at_price`（原價，沒特價時為 null）。
- 列表頁 `/collections/all?page=N`，每頁 36 款，內嵌追蹤資料有品名和價格，但**價格和商品頁不一致**（例：WIND BLAST PK 男款 #1103242 列表 NT$1,686、商品頁 NT$2,480），不能用。
- 驗證：`#1101493` 在日本官網是「プラズマ1000 ダウンジャケット Men's」，`#1128593` 是「バーサライト ジャケット Women's」，和台灣同名商品一致。
- robots.txt 只禁止後台、購物車、會員頁，並註明 `ai-train=no`（禁止拿來訓練 AI）。我們只是查價，不受影響。
- 每天全部抓單品 JSON 要 1,676 次請求，約 45 分鐘，太慢，見下方決定 1。

## 需要決定的事

> **已決定（2026-10-27）**：mont-bell 每天輪流抓單品（實作時發現列表頁價格是活動價、和商品頁不一致，所以完全不用列表價格，接受最久約一週前的價格，每款顯示確認日期）；Adastria 只做 GLOBAL WORK、niko and ...；品牌按鈕改成可左右滑動（2026-10-28 改為換行、全部同時顯示）。

1. **mont-bell 怎麼抓**
   - A（建議）：每天抓列表 47 頁拿目前售價；單品 JSON（原價、網址、SKU）每天輪流抓約 250 款，一週輪完一次，結果存快取。新上架商品優先抓。
   - B：每天全部抓單品 JSON，約 45 分鐘。
2. **Adastria 只做 GLOBAL WORK、niko and...，還是同站其他品牌一起做**（LOWRYS FARM、studio CLIP 等）。
3. **前端品牌按鈕**：品牌變成 7 個，一排放不下，改成可左右滑動的按鈕列。
