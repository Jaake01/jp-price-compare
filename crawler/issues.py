"""依 report.json 開／留言／關閉 GitHub Issue。

失敗：同品牌已有未關閉的 Issue 就留言，否則開新的（GitHub 會寄信通知）。
成功：關閉該品牌未關閉的 Issue。
需要環境變數 GITHUB_TOKEN、GITHUB_REPOSITORY，以及選用的 RUN_URL。
"""
import json
import os
import sys
import urllib.request

API = "https://api.github.com"
LABEL = "data-update-failure"
NAMES = {"UQ": "UNIQLO", "GU": "GU", "MUJI": "MUJI", "FX": "匯率"}


def title_for(brand):
    return f"[資料更新失敗] {NAMES.get(brand, brand)}"


def _api(method, path, body=None):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        })
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


def failure_body(result, run_url):
    lines = [f"**品牌**：{NAMES.get(result['brand'], result['brand'])}", "", "**失敗原因**："]
    lines += [f"- {e}" for e in result["errors"]]
    if result.get("notes"):
        lines += ["", "**附註**："] + [f"- {n}" for n in result["notes"]]
    lines += ["", "已保留上一份正確資料，網頁照常可用（只會顯示較舊的更新時間）。"]
    if run_url:
        lines += ["", f"執行紀錄：{run_url}"]
    return "\n".join(lines)


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    run_url = os.environ.get("RUN_URL", "")
    with open(sys.argv[1] if len(sys.argv) > 1 else "report.json", encoding="utf-8") as f:
        report = json.load(f)
    open_issues = _api("GET", f"/repos/{repo}/issues?state=open&per_page=100") or []
    by_title = {i["title"]: i for i in open_issues if "pull_request" not in i}
    new_issues = []  # 這次新開的 Issue，交給自動修復
    for r in report["results"]:
        title = title_for(r["brand"])
        issue = by_title.get(title)
        if not r["ok"]:
            body = failure_body(r, run_url)
            if issue:
                _api("POST", f"/repos/{repo}/issues/{issue['number']}/comments", {"body": "今天仍然失敗。\n\n" + body})
                print(f"{r['brand']}: 留言於 #{issue['number']}")
            else:
                new = _api("POST", f"/repos/{repo}/issues", {"title": title, "body": body, "labels": [LABEL]})
                print(f"{r['brand']}: 開新 Issue #{new['number']}")
                new_issues.append({"brand": r["brand"], "number": new["number"], "errors": r["errors"]})
        elif issue:
            msg = f"今天更新成功（{r.get('count', '')} 筆），自動關閉。"
            if run_url:
                msg += f"\n\n執行紀錄：{run_url}"
            _api("POST", f"/repos/{repo}/issues/{issue['number']}/comments", {"body": msg})
            _api("PATCH", f"/repos/{repo}/issues/{issue['number']}", {"state": "closed", "state_reason": "completed"})
            print(f"{r['brand']}: 關閉 #{issue['number']}")
    write_output("new_issues", new_issues)


def write_output(name, value):
    """寫到 GitHub Actions 的 step output（本機執行時略過）。"""
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{name}={json.dumps(value, ensure_ascii=False)}\n")


if __name__ == "__main__":
    main()
