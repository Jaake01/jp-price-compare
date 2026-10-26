"""有禮貌的 HTTP 工具：固定 User-Agent、請求間隔、失敗重試。只用標準函式庫。"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
MIN_INTERVAL = 1.5  # 秒，SPEC 要求至少 1 秒
RETRIES = 3

_last_request = 0.0


class FetchError(Exception):
    pass


def _wait():
    global _last_request
    delay = MIN_INTERVAL - (time.monotonic() - _last_request)
    if delay > 0:
        time.sleep(delay)
    _last_request = time.monotonic()


def request(url, *, data=None, headers=None, params=None, timeout=60):
    """回傳 bytes。data 為 dict 時以 JSON POST。"""
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    hdrs = {"User-Agent": USER_AGENT, "Accept-Language": "zh-TW"}
    hdrs.update(headers or {})
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        hdrs.setdefault("Content-Type", "application/json; charset=utf-8")
    last_err = None
    for attempt in range(RETRIES):
        _wait()
        req = urllib.request.Request(url, data=body, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = e
            # 4xx（除了 429）重試也沒用
            if isinstance(e, urllib.error.HTTPError) and e.code < 500 and e.code != 429:
                break
            time.sleep(5 * (attempt + 1))
    raise FetchError(f"{url[:120]}: {last_err}")


def get_json(url, **kw):
    raw = request(url, **kw)
    try:
        return json.loads(raw)
    except ValueError as e:
        raise FetchError(f"{url[:120]}: 回應不是 JSON（{raw[:80]!r}）") from e
