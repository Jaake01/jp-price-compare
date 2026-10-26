# 第 1 階段：資料探勘報告

探勘日期：2026-10-26（台灣時間上午）
探勘方式：curl 直接呼叫網站自己用的 JSON API；為了找出 API，用無頭瀏覽器開過幾個頁面記錄網路請求。
請求量：三站合計約 100 次請求，間隔 1.5–3 秒，帶一般瀏覽器 User-Agent，沒有登入。

---

## 結論摘要

| 問題 | UNIQLO 台灣 | GU 台灣 | MUJI 台灣 |
| --- | --- | --- | --- |
| 資料來源 | JSON API（POST） | JSON API（POST），和 UQ 完全同一套 | JSON API（91APP GraphQL，GET） |
| 商品數 | 1,406 筆列表／1,343 個不重複編號 | 869 筆列表／788 個不重複編號 | 約 3,800 款／約 6,400 個「顏色頁」 |
| 原價與特價 | ✅ `originPrice`、`minPrice` | ✅ 同 UQ | ✅ `suggestPrice`、`price` |
| 編號 | ✅ 6 位數 `code`，100% 都有 | ✅ 同 UQ | ⚠️ 有 JAN 碼，但列表只給「第一個尺寸」的 JAN |
| 能否共用爬蟲 | ✅ 可以，只差網域與 Referer | ✅ | — |

**可行性：三個品牌都能用 JSON API 取得資料，不需要解析 HTML。** 但有三件事會影響規格（第 5 節），其中三項需要你決定（第 6 節）。

---

## 1. 資料從哪裡取得、大約幾件

### UNIQLO 台灣（www.uniqlo.com/tw）

台灣站**不是** UNIQLO 全球版（日本、美國用的 `/api/commerce/v5`）那套，而是迅銷在大中華區用的「hmall」平台。前端是 React，商品列表由下面這支 API 提供：

```
POST https://d.uniqlo.com/tw/p/search/products/by-category
Headers: Content-Type: application/json; charset=utf-8
         langcode: zh_TW
         Referer: https://www.uniqlo.com/
Body:
{"pageInfo":{"page":1,"pageSize":200},"belongTo":"pc","rank":"overall",
 "priceRange":{"low":0,"high":0},"color":[],"size":[],"identity":[],"exist":[],
 "categoryCode":"ALL","byCateCodeWithLineUp":false,"searchFlag":false,
 "description":"","stockFilter":"warehouse"}
```

- `categoryCode: "ALL"` 一次列出全站，`pageSize` 可設 200 → **全站 8 次請求就抓完**（每次約 1 MB、1 秒）。
- 回應 `resp[0].productSum` = 1,406，`productList` 為商品陣列。
- 把 `stockFilter` 改成空字串，總數一樣是 1,406。
- 用一般 curl 就能拿到，不需要 Cookie。不過 www.uniqlo.com 前面有 **Akamai 反機器人**（頁面會送 `sensor_data`），目前 API 網域 `d.uniqlo.com` 沒擋 curl，但這是最大的不確定性（見第 5 節風險）。
- robots.txt 沒有禁止 `/tw/` 的 API 或商品頁。

### GU 台灣（www.gu-global.com/tw）

和 UQ 台灣**完全同一套平台**，連前端的 vendor bundle 檔名都一樣（`vendor.2f4a25d3388ce4fb02bd.bundle.js`）。API 只差網域：

```
POST https://d.gu-global.com/tw/p/search/products/by-category
Referer: https://www.gu-global.com/
（Body 同上）
```

- 全站 869 筆，5 次請求抓完。

### MUJI 台灣（shop.muji.tw）

**確認建在 91APP 上**（shop id = `41566`，頁面裡有 `nineyi.shop.s041566`）。

商品列表來自 91APP 的 CDN GraphQL 端點（分類頁本身就用它）：

```
GET https://fts-api.91app.com/pythia-cdn/graphql
    ?shopId=41566&lang=zh-TW
    &query=query cms_shopCategory($shopId:Int!,$categoryId:Int!,$startIndex:Int!,$fetchCount:Int!){
             shopCategory(shopId:$shopId,categoryId:$categoryId){
               salePageList(startIndex:$startIndex,maxCount:$fetchCount){
                 salePageList{ salePageId title picUrl price suggestPrice isSoldOut
                               skuOuterId salePageGroup{ groupTitle groupItems{ salePageId itemTitle } } }
                 totalSize shopCategoryName } } }
    &variables={"shopId":41566,"categoryId":483010,"startIndex":0,"fetchCount":100}
```

- **沒有「全部商品」分類**（根分類 id=1 查詢會報錯），內部真正的分類樹（例如「1_衣料雜貨 > 16_女內衣」）是隱藏的、查不到。只能**逐一查 36 個頂層分類再去重**。
- 頂層分類（女裝、男裝、文具、食品…）的 `totalSize` 合計約 3,800；同一款的不同顏色是不同的商品頁（salePage）。例如「女裝」分組後 411 款、不分組 1,019 頁。
- sitemap（`/Sitemap/sitemap_ShopSalePage.xml.gz`）有 6,365 個商品頁，跟推算一致。
- 估計每天約 70 次請求（每次 100 筆）可以抓完全部顏色頁。
- `fts-api.91app.com` 沒有 robots.txt；`shop.muji.tw/robots.txt` 禁止 `/webapi/`，但列出了一些允許的端點。另一個網域 `webapi.91app.com` 的 robots.txt 是 `Disallow: /`（全部禁止）。
- shop.muji.tw 本站的 `/webapi/` 有 AWS WAF（請求帶 `x-aws-waf-token`），GraphQL 端點沒有。

---

## 2. 能否取得原價與特價

| 品牌 | 原價欄位 | 目前售價欄位 | 特價判斷 | 這次看到的特價數 |
| --- | --- | --- | --- | --- |
| UQ | `originPrice` | `minPrice`（= `maxPrice` = `prices[0]`） | `minPrice < originPrice` | 456 / 1,406 筆 |
| GU | `originPrice` | `minPrice` | 同上 | 291 / 869 筆 |
| MUJI | `suggestPrice` | `price` | `price < suggestPrice` | 「SALE｜衣料服飾」分類 100/100 筆 |

- 三站都**能取得**兩個欄位。UQ/GU 另有 `identity` 標籤，`concessional_rate` 表示特價中。
- UQ/GU 沒有看到 `minPrice ≠ maxPrice`，也沒有售價高於原價的情況。
- MUJI 另有 `promotionPrices`（活動價、會員價），依規格不處理。

**⚠️ 特價是「依顏色」的**：UQ/GU 會把同一款的特價顏色**拆成另一筆商品**（不同的 `productCode`、同一個 6 位數編號）。例如：

| 編號 | 商品 | 顏色 | 原價 | 售價 |
| --- | --- | --- | --- | --- |
| 483457 | AIRism棉質T恤(短袖) | 白、淺灰、黑、米、深棕、藏青 | 390 | 390 |
| 483457 | AIRism棉質T恤(短袖) | 粉、紅、綠 | 390 | **190** |

UQ 有 59 組、GU 有 58 組這種情況（約佔編號的 4–7%）。GU 甚至有兩筆都是特價但價格不同（359811 蝙蝠袖透膚襯衫：多數顏色 590、粉色 390）。規格的 `salePrice` 只有一個數字，**放不下這種情況**，見第 6 節決定 2。

MUJI 也一樣：每個顏色是獨立的商品頁，價格可能不同（例如工作短褲只有黑色在 SALE 分類）。

---

## 3. 編號：UQ/GU 6 位數、MUJI JAN 碼

### UQ、GU：✅ 取得到

- `code` 欄位就是 6 位數商品編號，**100% 的商品都有，全部都是 6 位數**。
- 抽樣到日本官網用同一個編號查：UQ `488298`（台灣「羅紋連帽上衣(長袖)」= 日本「フーデッドリブT」¥1,990）對得上；GU 抽 5 筆有 3 筆對得上（`362202` 透膚圓點T恤 = シアードットT），另外 2 筆日本官網查不到（可能是日本已下架或台灣限定）。
- **重要發現：同一款的不同顏色可能有不同的 6 位數編號。** `styleText` 欄位會寫成 `"474405 / 09 BLACK"`，表示黑色在其他市場或前一季是 474405。UQ 有 219 筆品名後面直接附了其他編號（例如「繭型牛仔褲 482280 / 490633」）。日本店內吊牌印的有可能是這些編號，**建議全部放進 `altIds`**。
- 品名要把後面附的編號去掉才乾淨（`productName` 欄位更亂，混了尺寸、顏色、行銷標籤，不要用）。

### MUJI：✅ 有 JAN 碼，但只有部分 ⚠️

- 列表 API 的 `skuOuterId` 就是 JAN 碼（例如 `4550723435437`，455 開頭是良品計画的日本條碼）。
- **但每個商品頁只給一個 JAN（第一個尺寸）。** 衣服每個尺寸都有自己的 JAN，例如「女棉保暖厚織U領八分袖T恤 淺粉」：

  | 尺寸 | JAN |
  | --- | --- |
  | S | 4550723297400 |
  | M | 4550723297417 |
  | L | 4550723297424 |
  | XL | 4550723297431 |

  只存第一個的話，在日本拿 M 號吊牌輸入 JAN，會顯示「查無」。
- 要拿到全部尺寸的 JAN，有兩個地方：
  1. **商品頁 HTML**（robots 允許）：每頁約 340 KB，6,400 頁 ≈ 每天 2.2 GB、1 秒一頁要跑將近 2 小時。
  2. **91APP 商品資訊 API** `webapi.91app.com/webapi/SalePageV2/GetSalePageV2Info/41566/{id}`：每筆 15 KB，但該網域 robots.txt 全部禁止。這次只為了確認欄位呼叫過 1 次。
- 雜貨、食品大多只有一個尺寸，列表給的 JAN 就是唯一的 JAN，不受影響。
- 日本 MUJI 官網（www.muji.com）從這次探勘的環境連不上（逾時），**台灣與日本 JAN 是否一致還沒驗證**。

---

## 4. UQ 與 GU 能否共用爬蟲

✅ **可以，同一個模組、兩組設定就好。**

| 項目 | UQ | GU |
| --- | --- | --- |
| API | `https://d.uniqlo.com/tw/p/search/products/by-category` | `https://d.gu-global.com/tw/p/search/products/by-category` |
| Referer | `https://www.uniqlo.com/` | `https://www.gu-global.com/` |
| 圖片網址前綴 | `https://www.uniqlo.com/tw` + `mainPic` | `https://www.gu-global.com/tw` + `mainPic` |
| 商品頁 | `https://www.uniqlo.com/tw/zh_TW/product-detail.html?productCode={productCode}` | `https://www.gu-global.com/tw/zh_TW/product-detail.html?productCode={productCode}` |

請求格式、回應欄位、分頁方式完全相同。圖片網址兩站都實測 200。

---

## 5. 風險

1. **UQ/GU 反機器人（中風險）**：www 網域有 Akamai Bot Manager。今天 API 網域 `d.uniqlo.com` 用 curl 就能拿，但 GitHub Actions 是從美國的雲端 IP 發出請求，可能被判定成機器人。**第 2 階段第一件事應該在 Actions 上實測一次。** 被擋的話備案是用 Playwright 開真瀏覽器，會慢一些、比較複雜。
2. **MUJI 只拿得到部分 JAN（高影響）**：見第 3 節，需要你決定（決定 1）。
3. **同一個編號有多個價格（高影響）**：UQ/GU 約 4–7% 的編號、MUJI 的多色商品，價格依顏色不同。如果只存一個 `salePrice`，可能顯示錯誤的價格，違反「不出錯」原則。需要你決定（決定 2）。
4. **健康檢查的價格下限 NT$50 會誤判 MUJI**：MUJI 文具最低 NT$15、零件 NT$20。照現在的規則「任一商品低於 50」就會讓 MUJI 每天都失敗（決定 3）。UQ/GU 最低 NT$79，沒問題。
5. **MUJI 分類是行銷用的**：可見分類有「社群人氣話題」「防颱對策」等重疊分類，真正的商品分類是隱藏的。`category` 欄位只能用頂層分類名稱（女裝、文具…），關鍵字搜尋的效果會比 UQ/GU 差一點。
6. **MUJI 跨國 JAN 未驗證**：沒辦法從這裡連到日本 MUJI 官網。建議你有空時用手機開 www.muji.com 查一下第 7 節的 JAN，或等到日本實測。
7. **API 不是公開文件**：三站的 API 都可能無預警改版。這正是健康檢查 + 自動開 Issue 要處理的情況，規格已經有涵蓋。
8. UQ/GU 圖片路徑含 `/hmall/test/`，看起來像測試路徑，但實際就是正式圖片，可以正常使用。

---

## 6. 需要你決定的事

> **已決定（2026-10-26）**：決定 1 選 A、決定 2 選 A、決定 3 照建議。已更新到 SPEC.md。

### 決定 1：MUJI 其他尺寸的 JAN 怎麼拿？

| 選項 | 做法 | 優點 | 缺點 |
| --- | --- | --- | --- |
| **A（建議）** | 每天用列表 API 更新價格；**只有新出現的商品頁**才去抓一次商品頁 HTML 補齊 JAN，存成快取（JAN 不會變）。第一次補齊 6,400 頁分好幾天慢慢跑。 | 遵守 robots；每天只多抓幾十頁；能拿到全部 JAN | 第一次要好幾天才補完；多一個快取檔 |
| B | 只存列表給的第一個 JAN，其他尺寸用品名搜尋 | 最簡單 | 衣服類用 JAN 查常常「查無」 |
| C | 用 91APP 商品資訊 API（每筆 15 KB） | 輕量、乾淨 | 違反該網域 robots.txt |

### 決定 2：同一款不同顏色價格不同時，怎麼顯示？

| 選項 | 做法 | 優點 | 缺點 |
| --- | --- | --- | --- |
| **A（建議）** | 資料多存一個 `variants` 陣列（顏色、該色售價、該色 altIds）。搜尋卡片顯示價格區間「NT$190–390」；詳細頁列出各顏色價格，價差預設用最高售價計算（保守），可點選顏色切換。 | 不會顯示錯誤價格 | 資料格式和詳細頁多一點東西 |
| B | 不合併，每個顏色組當一筆（同編號會出現兩張卡） | 實作最簡單 | 違反「同一款合併成一筆」，查編號時會跳出「多筆」 |
| C | 只顯示一個價格（最低），加註「部分顏色特價」 | 改動最少 | 你看到的價格可能不是手上那件的價格 |

### 決定 3：價格合理範圍怎麼改？

建議改成：**單一商品超出範圍時只剔除該商品（記錄在 log），超過 5% 的商品不合理才算整個品牌失敗**；下限從 NT$50 改成 **NT$10**。

---

## 7. 範例資料（實際取得，已轉成 SPEC 格式）

> `_note` 欄位只是說明，正式資料不會有。UQ/GU 的 `altIds` 來自 `styleText` 與品名後附的編號。MUJI 是單一顏色頁轉換的結果（還沒合併顏色）。

### UNIQLO

```json
[
  {
    "brand": "UQ",
    "id": "488298",
    "altIds": [],
    "name": "羅紋連帽上衣(長袖)",
    "price": 590,
    "salePrice": null,
    "image": "https://www.uniqlo.com/tw/hmall/test/u0000000054740/main/first/561/1.jpg",
    "url": "https://www.uniqlo.com/tw/zh_TW/product-detail.html?productCode=u0000000054740",
    "category": "T恤/休閒上衣/刷毛",
    "_note": "一般商品。日本官網同編號：フーデッドリブT ¥1,990"
  },
  {
    "brand": "UQ",
    "id": "483457",
    "altIds": ["474405"],
    "name": "AIRism棉質T恤(短袖)",
    "price": 390,
    "salePrice": 190,
    "image": "https://www.uniqlo.com/tw/hmall/test/u0000000052707/main/first/561/1.jpg",
    "url": "https://www.uniqlo.com/tw/zh_TW/product-detail.html?productCode=u0000000052707",
    "category": "T恤/休閒上衣/刷毛",
    "_note": "兩筆列表合併：白/淺灰/黑/米/深棕/藏青 390 元（u0000000052707）；粉/紅/綠 190 元（u0000000053980）。黑色編號 474405。"
  },
  {
    "brand": "UQ",
    "id": "485824",
    "altIds": ["478954"],
    "name": "HEATTECH極暖喀什米爾混紡高領T恤(長袖)",
    "price": 690,
    "salePrice": null,
    "image": "https://www.uniqlo.com/tw/hmall/test/u0000000054622/main/first/561/1.jpg",
    "url": "https://www.uniqlo.com/tw/zh_TW/product-detail.html?productCode=u0000000054622",
    "category": "T恤/休閒上衣/刷毛",
    "_note": "灰03/黑/藏青的編號是 478954，其他顏色是 485824；原始品名為「…(長袖) 478954」"
  }
]
```

### GU

```json
[
  {
    "brand": "GU",
    "id": "363184",
    "altIds": ["361784"],
    "name": "休閒Balloon連帽拉鍊外套UL",
    "price": 990,
    "salePrice": null,
    "image": "https://www.gu-global.com/tw/hmall/test/u0000000053382/main/first/561/1.jpg",
    "url": "https://www.gu-global.com/tw/zh_TW/product-detail.html?productCode=u0000000053382",
    "category": "外套",
    "_note": "灰/橄欖/藍的編號是 361784，黑色是 363184"
  },
  {
    "brand": "GU",
    "id": "359811",
    "altIds": [],
    "name": "蝙蝠袖透膚襯衫",
    "price": 790,
    "salePrice": 390,
    "image": "https://www.gu-global.com/tw/hmall/test/u0000000052567/main/first/561/1.jpg",
    "url": "https://www.gu-global.com/tw/zh_TW/product-detail.html?productCode=u0000000052567",
    "category": "襯衫・設計上衣",
    "_note": "白/黑/橄欖/藍 590 元，粉色 390 元。salePrice 只能放一個數字的問題例子。日本：シアードルマンスリーブシャツ ¥1,990"
  },
  {
    "brand": "GU",
    "id": "362202",
    "altIds": [],
    "name": "透膚圓點T恤(長袖)",
    "price": 290,
    "salePrice": null,
    "image": "https://www.gu-global.com/tw/hmall/test/u0000000052758/main/first/561/1.jpg",
    "url": "https://www.gu-global.com/tw/zh_TW/product-detail.html?productCode=u0000000052758",
    "category": "T恤・休閒上衣",
    "_note": "日本官網同編號：シアードットT(長袖) ¥990"
  }
]
```

### MUJI

```json
[
  {
    "brand": "MUJI",
    "id": "4550723297400",
    "altIds": ["4550723297417", "4550723297424", "4550723297431"],
    "name": "女棉保暖厚織U領八分袖T恤 淺粉",
    "price": 490,
    "salePrice": null,
    "image": "https://img.91app.com/webapi/imagesV3/Cropped/SalePage/12214559/0/639281868526300000?v=1",
    "url": "https://shop.muji.tw/SalePage/Index/12214559",
    "category": "保暖內衣推薦",
    "_note": "列表只給 S 號的 JAN；M/L/XL 的 JAN 是從商品資訊 API 取得（決定 1）。同組還有「柔白」等顏色（salePageGroup）。"
  },
  {
    "brand": "MUJI",
    "id": "4550723239424",
    "altIds": [],
    "name": "男抗撕裂工作短褲 黑色",
    "price": 990,
    "salePrice": 792,
    "image": "https://img.91app.com/webapi/imagesV3/Cropped/SalePage/12005982/0/639281870494030000?v=1",
    "url": "https://shop.muji.tw/SalePage/Index/12005982",
    "category": "SALE｜衣料服飾",
    "_note": "特價例子（8 折）。同組的棕色、深綠不在 SALE 分類，價格可能不同。altIds 未知（列表只給一個 JAN）。"
  },
  {
    "brand": "MUJI",
    "id": "4550723435437",
    "altIds": [],
    "name": "女棉保暖全圈絨直角襪 灰棕",
    "price": 290,
    "salePrice": null,
    "image": "https://img.91app.com/webapi/imagesV3/Original/SalePage/12257770/0/639284874992900000?v=1",
    "url": "https://shop.muji.tw/SalePage/Index/12257770",
    "category": "女襪",
    "_note": "只有一個尺寸（23～25cm），列表的 JAN 就是全部。資料取自商品頁 HTML 內嵌 JSON（SKUPropertySetList）；分類取自內嵌的 CategoryLevelName（1_衣料雜貨 > 107_女內衣・家居服 > 18_女襪 > 161_女長襪），已去掉數字前綴。"
  }
]
```

---

## 附錄：其他觀察

- UQ/GU 列表欄位中可用的還有：`categoryName`（多層分類名稱陣列，可用於關鍵字搜尋）、`colorNums`、`styleText`、`identity`（`ECONLY` 網路限定、`new_product` 新品等）、`stock`。
- MUJI 品名把顏色直接接在後面（「…短褲黑色」），沒有分隔符號；合併同款時要用 `salePageGroup` 的 `itemTitle`（顏色名）把它切掉。
- MUJI 商品頁 HTML 內嵌的 JSON 有 `CategoryLevelName`（隱藏的內部分類，例如「1_衣料雜貨 > 107_女內衣・家居服 > 16_女內衣」），如果採用決定 1 的選項 A，可以順便拿來當 `category`。
- 匯率（台灣銀行）不在這次探勘範圍內。
