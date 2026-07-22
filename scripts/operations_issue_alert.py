from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import request
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


LABELS = ["data-pipeline", "operations", "freshness-alert"]


def api_request(url: str, token: str, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "ModularHubOperationsAlert")
    req.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with request.urlopen(req, timeout=20) as response:  # noqa: S310 - GitHub API endpoint is controlled by workflow input.
        text = response.read().decode("utf-8")
        return json.loads(text) if text else {}


def issue_body(alert: dict[str, Any], summary: dict[str, Any], run_url: str) -> str:
    return "\n".join(
        [
            "<!-- modularhub-operations-alert -->",
            f"Fingerprint: `{alert['fingerprint']}`",
            "",
            "## Operations Alert",
            "",
            f"- 발생 시각: `{datetime.now(timezone.utc).isoformat()}`",
            f"- Workflow Run: {run_url or '-'}",
            f"- Dataset: `{alert.get('dataset')}`",
            f"- Source: `{alert.get('sourceId')}`",
            f"- 오류 분류: `{alert.get('errorCategory')}`",
            f"- 상태: `{alert.get('state')}`",
            f"- 전체 상태: `{summary.get('overallState')}`",
            f"- Last Known Good 유지: `true`",
            "",
            "## Suggested Action",
            "",
            "- Source credential, endpoint, permission, or freshness policy threshold를 확인하세요.",
            "- 같은 fingerprint의 열린 이슈가 있으면 이 이슈에 후속 run 결과가 누적됩니다.",
            "- Secret, raw response, 인증 header는 이 알림에 포함하지 않습니다.",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or update sanitized GitHub Issues for ModularHub operations alerts.")
    parser.add_argument("--summary", type=Path, default=Path("artifacts/operations/freshness-summary.json"))
    parser.add_argument("--repo", default=os.getenv("GITHUB_REPOSITORY", ""))
    parser.add_argument("--run-url", default=os.getenv("GITHUB_SERVER_URL", "https://github.com") + "/" + os.getenv("GITHUB_REPOSITORY", "") + "/actions/runs/" + os.getenv("GITHUB_RUN_ID", ""))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.summary.exists():
        print("No operations freshness summary found; skipping issue alert.")
        return 0
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    alerts = [alert for alert in summary.get("alerts", []) if alert.get("state") in {"critical", "warning", "auth_error", "permission_error", "rate_limited", "timeout", "parse_error", "source_unavailable", "stale"}]
    if not alerts:
        print("No operations alerts to publish.")
        return 0
    token = os.getenv("GITHUB_TOKEN", "")
    if args.dry_run or not token or not args.repo:
        print(f"Operations issue alert dry-run/fallback: alerts={len(alerts)}")
        for alert in alerts:
            print(f"::warning::operations_alert fingerprint={alert.get('fingerprint')} dataset={alert.get('dataset')} source={alert.get('sourceId')} state={alert.get('state')}")
        return 0

    owner_repo = args.repo.strip("/")
    base = f"https://api.github.com/repos/{owner_repo}"
    for alert in alerts:
        fingerprint = alert["fingerprint"]
        query = quote(f'repo:{owner_repo} is:issue is:open "{fingerprint}"', safe="")
        try:
            search = api_request(f"https://api.github.com/search/issues?q={query}", token)
            existing = (search.get("items") or [None])[0]
            body = issue_body(alert, summary, args.run_url)
            if existing:
                number = existing["number"]
                api_request(f"{base}/issues/{number}/comments", token, "POST", {"body": body})
                print(f"Updated operations alert issue #{number} for {fingerprint}")
            else:
                created = api_request(
                    f"{base}/issues",
                    token,
                    "POST",
                    {
                        "title": f"ModularHub data pipeline alert: {alert.get('dataset')} / {alert.get('sourceId')}",
                        "body": body,
                        "labels": LABELS,
                    },
                )
                print(f"Created operations alert issue #{created.get('number')} for {fingerprint}")
        except Exception as exc:  # noqa: BLE001 - issue alert must not break data publication.
            print(f"::warning::Unable to publish operations alert for {fingerprint}: {type(exc).__name__}")
            continue
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
