from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.operations_public_data import (  # noqa: E402
    OperationsAuditError,
    audit_datasets,
    contains_secret_indicator,
    count_delta_guard,
    load_json,
    load_policy,
    source_health_from_payloads,
    worst_state,
)


def load_optional(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = load_json(path)
    return payload if isinstance(payload, dict) else {}


def dataset_items(payload: dict[str, Any], key: str = "items") -> list[dict[str, Any]]:
    items = payload.get(key, [])
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def previous_count(payload: dict[str, Any], dataset: str, current: int) -> int:
    if dataset == "news":
        return int(payload.get("previous_news_count") or payload.get("current_news_count") or current)
    if dataset == "business":
        return int(payload.get("previous_business_count") or payload.get("current_business_count") or current)
    return current


def markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) if cell is not None else "-" for cell in row) + " |")
    return lines


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "## Operations Data Freshness",
        "",
        f"- overall_state: `{summary['overallState']}`",
        f"- generated_at: `{summary['generatedAt']}`",
        f"- policy: `{summary['policyPath']}`",
        "",
        "### Dataset SLA",
        "",
    ]
    lines.extend(
        markdown_table(
            ["Dataset", "Count", "Latest", "Age", "SLA", "State", "Reason"],
            [
                [
                    row["dataset"],
                    row["recordCount"],
                    row.get("latestItemAt") or "-",
                    row.get("ageHours", row.get("ageDays", "-")),
                    f"{row['warningThreshold']}/{row['criticalThreshold']}",
                    row["state"],
                    row["reason"],
                ]
                for row in summary["datasets"]
            ],
        )
    )
    lines.extend(["", "### Source Health", ""])
    lines.extend(
        markdown_table(
            ["Source", "Configured", "HTTP", "Fetched", "Accepted", "Duplicate", "Rejected", "Latest", "State"],
            [
                [
                    row["sourceName"],
                    row["configured"],
                    row["httpStatus"] or "-",
                    row["fetchedCount"],
                    row["acceptedCount"],
                    row["duplicateCount"],
                    row["rejectedCount"],
                    row["latestSourceItemAt"] or "-",
                    row["state"],
                ]
                for row in summary["sources"]
            ],
        )
    )
    lines.extend(["", "### Count Delta Guard", ""])
    lines.extend(
        markdown_table(
            ["Dataset", "Previous", "Current", "Delta", "Drop %", "State", "Reason"],
            [
                [
                    row["dataset"],
                    row["previousCount"],
                    row["currentCount"],
                    row["delta"],
                    row["dropPercent"],
                    row["state"],
                    row["reason"],
                ]
                for row in summary["countDeltas"]
            ],
        )
    )
    if summary.get("alerts"):
        lines.extend(["", "### Alerts", ""])
        for alert in summary["alerts"]:
            lines.append(f"- `{alert['fingerprint']}` {alert['dataset']} / {alert['sourceId']} / {alert['errorCategory']}: {alert['state']}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit ModularHub public data freshness, source health, and count deltas.")
    parser.add_argument("--policy", type=Path, default=Path("config/operations/data_freshness_policy.json"))
    parser.add_argument("--news", type=Path, default=Path("frontend/public/data/news.json"))
    parser.add_argument("--business", type=Path, default=Path("frontend/public/data/business.json"))
    parser.add_argument("--meta", type=Path, default=Path("frontend/public/data/meta.json"))
    parser.add_argument("--companies", type=Path, default=Path("frontend/public/data/companies/companies.json"))
    parser.add_argument("--companies-v2", type=Path, default=Path("frontend/public/data/companies/company_intelligence_v2.json"))
    parser.add_argument("--daeseung-source", type=Path, default=Path("frontend/src/data/daeseungEngineeringCompany.js"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/operations"))
    parser.add_argument("--strict-critical", action="store_true", help="Exit 1 when any critical state is found.")
    args = parser.parse_args()

    try:
        policy = load_policy(args.policy)
        news_payload = load_optional(args.news)
        business_payload = load_optional(args.business)
        meta_payload = load_optional(args.meta)
        companies_payload = load_optional(args.companies)
        company_v2_payload = load_optional(args.companies_v2)
        datasets = audit_datasets(
            news_payload=news_payload,
            business_payload=business_payload,
            companies_payload=companies_payload,
            company_v2_payload=company_v2_payload,
            meta_payload=meta_payload,
            policy=policy,
            now=datetime.now(timezone.utc),
            daeseung_source=args.daeseung_source,
        )
        sources = source_health_from_payloads(news_payload, business_payload, meta_payload, policy)
        counts = {
            "news": len(dataset_items(news_payload)),
            "business": len(dataset_items(business_payload)),
            "companies": next((row["recordCount"] for row in datasets if row["dataset"] == "companies"), 0),
        }
        count_deltas = [
            count_delta_guard(counts["news"], previous_count(news_payload, "news", counts["news"]), policy["datasets"]["news"], "news"),
            count_delta_guard(counts["business"], previous_count(business_payload, "business", counts["business"]), policy["datasets"]["business"], "business"),
            count_delta_guard(counts["companies"], counts["companies"], policy["datasets"]["companies"], "companies"),
        ]
        alerts = []
        from src.operations_public_data import issue_fingerprint  # local import keeps top import compact

        for row in datasets:
            if row["state"] in {"critical", "warning"}:
                alerts.append(
                    {
                        "dataset": row["dataset"],
                        "sourceId": "dataset",
                        "errorCategory": row["state"],
                        "state": row["state"],
                        "fingerprint": issue_fingerprint(row["dataset"], "dataset", row["state"]),
                    }
                )
        for row in sources:
            if row["state"] in {"auth_error", "permission_error", "rate_limited", "timeout", "parse_error", "source_unavailable", "stale"}:
                alerts.append(
                    {
                        "dataset": row["category"],
                        "sourceId": row["sourceId"],
                        "errorCategory": row["errorCategory"] if row["errorCategory"] != "none" else row["state"],
                        "state": row["state"],
                        "fingerprint": issue_fingerprint(row["category"], row["sourceId"], row["errorCategory"] if row["errorCategory"] != "none" else row["state"]),
                    }
                )
        for row in count_deltas:
            if row["state"] == "critical":
                alerts.append(
                    {
                        "dataset": row["dataset"],
                        "sourceId": "count_delta",
                        "errorCategory": "count_drop",
                        "state": "critical",
                        "fingerprint": issue_fingerprint(row["dataset"], "count_delta", "count_drop"),
                    }
                )

        overall_records = datasets + count_deltas
        overall_state = worst_state(overall_records)
        if any(row.get("state") == "critical" for row in count_deltas):
            overall_state = "critical"
        summary = {
            "schemaVersion": 1,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "policyPath": str(args.policy),
            "overallState": overall_state,
            "datasets": datasets,
            "sources": sources,
            "countDeltas": count_deltas,
            "alerts": alerts,
            "secretExposureDetected": False,
        }
        serialized = json.dumps(summary, ensure_ascii=False, indent=2)
        summary["secretExposureDetected"] = contains_secret_indicator(serialized, policy)
        serialized = json.dumps(summary, ensure_ascii=False, indent=2)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "freshness-summary.json").write_text(serialized + "\n", encoding="utf-8")
        (args.output_dir / "freshness-report.md").write_text(render_markdown(summary), encoding="utf-8")
        print(f"OPERATIONS FRESHNESS AUDIT {overall_state.upper()}: wrote {args.output_dir}")
        if summary["secretExposureDetected"]:
            print("Secret indicator detected in operations audit output.")
            return 2
        if args.strict_critical and overall_state == "critical":
            return 1
        return 0
    except OperationsAuditError as exc:
        print(f"OPERATIONS FRESHNESS AUDIT ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
