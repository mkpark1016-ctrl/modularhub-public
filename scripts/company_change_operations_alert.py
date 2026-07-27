#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib import request
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.company_change_operations import FAILED, HEALTHY

LABELS = ["operations", "company-monitor", "automated-alert"]
MARKER_PREFIX = "company-change-monitor-alert:"


class IssueClient(Protocol):
    def search_open(self, marker: str) -> dict[str, Any] | None: ...
    def create(self, title: str, body: str, labels: list[str]) -> dict[str, Any]: ...
    def comment(self, number: int, body: str) -> None: ...
    def close(self, number: int, body: str) -> None: ...
    def ensure_labels(self, labels: list[str]) -> None: ...


class GitHubIssueClient:
    def __init__(self, repo: str, token: str) -> None:
        self.repo = repo.strip("/")
        self.token = token
        self.base = f"https://api.github.com/repos/{self.repo}"

    def _request(self, url: str, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = request.Request(url, data=data, method=method)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("User-Agent", "ModularHubCompanyChangeOperations")
        req.add_header("Authorization", f"Bearer {self.token}")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        with request.urlopen(req, timeout=20) as response:  # noqa: S310 - GitHub API URL is derived from GITHUB_REPOSITORY.
            text = response.read().decode("utf-8")
            return json.loads(text) if text else {}

    def search_open(self, marker: str) -> dict[str, Any] | None:
        query = quote(f'repo:{self.repo} is:issue is:open "{marker}"', safe="")
        payload = self._request(f"https://api.github.com/search/issues?q={query}")
        items = payload.get("items") or []
        return items[0] if items else None

    def create(self, title: str, body: str, labels: list[str]) -> dict[str, Any]:
        return self._request(f"{self.base}/issues", "POST", {"title": title, "body": body, "labels": labels})

    def comment(self, number: int, body: str) -> None:
        self._request(f"{self.base}/issues/{number}/comments", "POST", {"body": body})

    def close(self, number: int, body: str) -> None:
        self.comment(number, body)
        self._request(f"{self.base}/issues/{number}", "PATCH", {"state": "closed"})

    def ensure_labels(self, labels: list[str]) -> None:
        for label in labels:
            try:
                self._request(f"{self.base}/labels", "POST", {"name": label})
            except Exception:
                continue


def alert_marker(alert_code: str) -> str:
    return f"<!-- {MARKER_PREFIX}{alert_code} -->"


def issue_title(evaluation: dict[str, Any]) -> str:
    code = evaluation.get("alertCode", "unknown")
    if evaluation.get("state") == FAILED:
        if "source" in code:
            return "[Company Monitor] Source coverage degraded"
        if "candidate" in code or "ref" in code or "conflict" in code:
            return "[Company Monitor] Candidate integrity failure"
        return "[Company Monitor] Production operation failure"
    return "[Company Monitor] Source coverage degraded"


def issue_body(evaluation: dict[str, Any]) -> str:
    code = evaluation.get("alertCode", "unknown")
    run = evaluation.get("runMetadata", {})
    candidates = evaluation.get("candidates", {})
    protection = evaluation.get("protection", {})
    lines = [
        alert_marker(code),
        "",
        "## Company Change Monitor Alert",
        "",
        f"- Created at: `{datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')}`",
        f"- Run URL: {run.get('runUrl') or '-'}",
        f"- Run number: `{run.get('runNumber') or '-'}`",
        f"- Run SHA: `{run.get('runSha') or '-'}`",
        f"- State: `{evaluation.get('state')}`",
        f"- Alert code: `{code}`",
        f"- Company count: `{evaluation.get('companyScope', {}).get('actualCount')}`",
        f"- Candidate count: `{candidates.get('candidateCount')}`",
        f"- Pending/Duplicate/Conflict/Insufficient evidence: `{candidates.get('pending')}` / `{candidates.get('duplicate')}` / `{candidates.get('conflict')}` / `{candidates.get('insufficientEvidence')}`",
        f"- Public data changed: `{protection.get('publicDataChanged')}`",
        f"- Proposal generated: `{protection.get('proposalGenerated')}`",
        f"- Secret exposure: `{protection.get('secretExposureDetected')}`",
        "",
        "## Sources",
        "",
    ]
    for source in evaluation.get("sources", []):
        lines.append(
            f"- `{source.get('sourceId')}`: configured={source.get('configured')}, attempted={source.get('attempted')}, state={source.get('state')}, raw={source.get('rawCount')}, normalized={source.get('normalizedCount')}, error={source.get('safeErrorCategory')}"
        )
    lines.extend(
        [
            "",
            "## Next Action",
            "",
            "- Inspect the workflow artifacts before changing public data.",
            "- Keep the monitor read-only until a human review approves any follow-up.",
            "- This issue intentionally omits secrets, auth headers, and raw API responses.",
        ]
    )
    return "\n".join(lines) + "\n"


def handle_alert(evaluation: dict[str, Any], client: IssueClient | None) -> dict[str, Any]:
    code = evaluation.get("alertCode", "none")
    if code == "none" or evaluation.get("state") == HEALTHY:
        closed = []
        closed_numbers: set[int] = set()
        if client:
            for stale_code in ["failed", "warning"]:
                existing = client.search_open(f"{MARKER_PREFIX}{stale_code}")
                if existing and existing["number"] not in closed_numbers:
                    client.close(existing["number"], "Recovery observed: Company Change Monitor is HEALTHY.")
                    closed_numbers.add(existing["number"])
                    closed.append(existing.get("html_url") or f"#{existing['number']}")
        return {"action": "recovery_closed" if closed else "none", "alertCode": code, "issueUrl": closed[0] if closed else None, "duplicatePrevented": False}

    if not evaluation.get("alertRequired"):
        return {"action": "none", "alertCode": code, "issueUrl": None, "duplicatePrevented": False}

    marker = f"{MARKER_PREFIX}{code}"
    body = issue_body(evaluation)
    if not client:
        return {"action": "dry_run", "alertCode": code, "issueUrl": None, "duplicatePrevented": False}

    client.ensure_labels(LABELS)
    existing = client.search_open(marker)
    if existing:
        client.comment(existing["number"], body)
        return {"action": "issue_updated", "alertCode": code, "issueUrl": existing.get("html_url"), "duplicatePrevented": True}
    created = client.create(issue_title(evaluation), body, LABELS)
    return {"action": "issue_created", "alertCode": code, "issueUrl": created.get("html_url"), "duplicatePrevented": False}


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or update deduplicated GitHub Issues for Company Change Monitor operations.")
    parser.add_argument("--evaluation", type=Path, default=Path("artifacts/company-change-monitor/operations-evaluation.json"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/company-change-monitor/operations-alert.json"))
    parser.add_argument("--repo", default=os.getenv("GITHUB_REPOSITORY", ""))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.evaluation.exists():
        print("No operations evaluation found; skipping alert.")
        return 0
    evaluation = json.loads(args.evaluation.read_text(encoding="utf-8"))
    token = os.getenv("GITHUB_TOKEN", "")
    client = None if args.dry_run or not token or not args.repo else GitHubIssueClient(args.repo, token)
    try:
        result = handle_alert(evaluation, client)
    except Exception as exc:  # noqa: BLE001 - alert publication must not hide the original monitor outcome.
        result = {"action": "alert_error", "alertCode": evaluation.get("alertCode", "unknown"), "issueUrl": None, "duplicatePrevented": False, "errorCategory": type(exc).__name__}
        print(f"::warning::Company monitor alert publication failed: {type(exc).__name__}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
