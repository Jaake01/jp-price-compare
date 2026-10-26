"""日圓匯率：國際參考匯率（exchangerate-api 免費資料，每日更新）。

台灣銀行牌告網站有反機器人驗證，從雲端環境抓不到，因此改用此來源（2026-10-26 決定）。
"""
from datetime import datetime, timezone

from . import http

SOURCE_URL = "https://open.er-api.com/v6/latest/JPY"


def fetch():
    d = http.get_json(SOURCE_URL)
    if d.get("result") != "success":
        raise http.FetchError(f"匯率 API 回傳失敗：{d.get('error-type')}")
    rate = float(d["rates"]["TWD"])
    date = datetime.fromtimestamp(d["time_last_update_unix"], timezone.utc).strftime("%Y-%m-%d")
    return {
        "currency": "JPY",
        "rate": round(rate, 6),  # 1 日圓 = ? 新台幣
        "source": "國際參考匯率（ExchangeRate-API）",
        "sourceUrl": "https://www.exchangerate-api.com",
        "date": date,
    }
