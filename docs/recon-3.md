# 日本官網價格探勘：UNIQLO、GU、MUJI

探勘日期：2026-10-31

## 結論

| 品牌 | 能否抓取 | 資料來源 | 商品數 | 和台灣編號對得上 |
| --- | --- | --- | --- | --- |
| UNIQLO 日本 | ✅ | commerce API，一次列出全站 | 1,800 筆（1,692 個編號） | 台灣 1,344 款中 700 款（52%） |
| GU 日本 | ✅ | 同上 | 1,182 筆（1,054 個編號） | 台灣 793 款中 618 款（78%） |
| MUJI 日本 | ❌ | — | — | — |

對不上的多半是日本官網已經沒在賣的款（例如 PEACE FOR ALL 部分圖案）。日本店內仍可能有，只是沒有官網價格可顯示。

## UNIQLO、GU 日本官網

- 列表：`GET https://www.uniqlo.com/jp/api/commerce/v5/ja/products?path=,,&limit=100&offset=N`（GU 換成 `www.gu-global.com`）。`path=,,` 代表全部分類，`pagination.total` 是總數。每頁 100 筆，UNIQLO 約 18 頁、GU 約 12 頁。
- 每筆有 `productId`（`E475367-000`，中間 6 位數就是台灣的商品編號）、`priceGroup`、`name`（日文）、`prices.base.value`（目前含稅售價）、`prices.promo`（特價中才有，值和 base 相同）、`colors`（`displayCode` 例如 `57`、`name` 例如 `OLIVE`，和台灣色碼相同）。
- 和台灣一樣，特價顏色會拆成另一筆（同一個 productId、不同 priceGroup），要依編號合併。例：475367 AIRism 棉質網眼 POLO 衫 — 11 色 ¥2,990、14 RED ¥1,290、11 PINK ¥790。
- API 不提供特價前的原價，只有目前售價與是否特價。
- 商品頁網址：`https://www.uniqlo.com/jp/ja/products/{productId}/{priceGroup}`。
- robots.txt：只禁止購物車、搜尋頁的 `?q=`、篩選參數等，沒有禁止 `/jp/api/`。

## MUJI 日本網路商店

- `www.muji.com` 從這個開發環境、以及 GitHub Actions 的伺服器（Azure 美東）都連不上：HTTP/2 立即被重置，HTTP/1.1 逾時，連 robots.txt 都拿不到。看起來是擋雲端／資料中心的連線。
- 這是網站有意的阻擋，不嘗試繞過。暫不提供 MUJI 日本官網價格。
- 替代做法（2026-10-31 決定）：商品頁放「在日本官網查」連結，用使用者手機打開 `https://www.muji.com/jp/ja/store/cmdty/detail/{JAN}`（日本官網商品頁網址即 13 位數 JAN，例如 MUJI 員工推薦文章裡的 `detail/4547315079469`）。
