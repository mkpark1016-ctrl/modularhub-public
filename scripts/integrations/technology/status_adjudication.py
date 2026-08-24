from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Iterable

from dotenv import load_dotenv

from scripts.integrations.technology.dry_run import load_companies
from scripts.integrations.technology.live_acceptance import (
    PROTECTED_PUBLIC_FILES,
    hash_files,
    security_metrics,
)
from scripts.integrations.technology.live_sources import (
    KIPRIS_LEGAL_STATUS_BASIC_ENDPOINT,
    KIPRIS_LEGAL_STATUS_STOP_RIGHT_ENDPOINT,
    KiprisLegalStatusClient,
    TechnologyCollectionResult,
)


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_COMPANIES = ROOT / "frontend/public/data/companies/companies.json"
DEFAULT_PRIOR_SUMMARY = ROOT / "artifacts/company-technology/samsung-baseline-exact/summary.json"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts/company-technology/samsung-status-adjudication"

CURRENT_LIFECYCLE_STATUS = "current_lifecycle_status"
CONFIRMED_EXPIRED = "CONFIRMED_EXPIRED"
CONFIRMED_REGISTERED_ACTIVE = "CONFIRMED_REGISTERED_ACTIVE"
UNRESOLVED_STATUS = "UNRESOLVED_STATUS"
ACCESS_UNAVAILABLE = "ACCESS_UNAVAILABLE"

TARGET_PATENTS = (
    {
        "technology_id": "tech-samsung-006",
        "application_number": "10-2014-0184710",
        "registration_number": "10-1672469",
    },
    {
        "technology_id": "tech-samsung-007",
        "application_number": "10-2014-0184696",
        "registration_number": "10-1632681",
    },
)
ACCESS_FAILURE_STATUSES = frozenset({"authentication_denied", "service_denied"})
ACTIVE_TERMS = (
    "권리유지", "등록유지", "존속", "유효", "active", "in force", "registered active",
)
EXPIRED_TERMS = ("소멸", "만료", "권리종료", "expired", "terminated", "lapsed")


def adjudicate_patent_status(
    basic_rows: Iterable[dict[str, Any]],
    stop_right_rows: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    basic = [dict(row) for row in basic_rows]
    stops = [dict(row) for row in stop_right_rows]
    active_events = _explicit_events(basic, ACTIVE_TERMS)
    expired_events = _explicit_events(basic, EXPIRED_TERMS)
    termination_events = [
        {
            "date": _pick_casefold(row, "terminationRegistrationCauseDate"),
            "reason": _pick_casefold(row, "terminationRegistrationCauseName"),
        }
        for row in stops
        if _pick_casefold(row, "terminationRegistrationCauseDate")
        or _pick_casefold(row, "terminationRegistrationCauseName")
    ]
    stop_dates = [_date_key(event["date"]) for event in termination_events if event.get("date")]
    active_dates = [_date_key(event["date"]) for event in active_events if event.get("date")]
    expired_dates = [_date_key(event["date"]) for event in expired_events if event.get("date")]
    latest_stop = max([*stop_dates, *expired_dates], default=None)
    latest_active = max(active_dates, default=None)

    if latest_stop and latest_active and latest_active > latest_stop:
        decision = UNRESOLVED_STATUS
        current_status = None
        rationale = "A later explicit active event follows termination evidence."
    elif termination_events or expired_events:
        decision = CONFIRMED_EXPIRED
        current_status = "expired"
        rationale = "Official ST.27 history contains explicit right-termination evidence."
    elif active_events:
        decision = CONFIRMED_REGISTERED_ACTIVE
        current_status = "registered"
        rationale = "Official ST.27 history contains an explicit active-right status and no termination evidence."
    else:
        decision = UNRESOLVED_STATUS
        current_status = None
        rationale = "Official history does not contain a decisive textual lifecycle event."

    return {
        "decision": decision,
        "current_status": current_status,
        "status_field_semantics": CURRENT_LIFECYCLE_STATUS,
        "rationale": rationale,
        "termination_events": termination_events,
        "explicit_active_events": active_events,
        "explicit_expired_events": expired_events,
    }


def run_status_adjudication(
    *,
    companies_path: Path = DEFAULT_COMPANIES,
    prior_summary_path: Path = DEFAULT_PRIOR_SUMMARY,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    client: KiprisLegalStatusClient | None = None,
    collected_at: str | None = None,
) -> dict[str, Any]:
    collected_at = collected_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    legal_client = client or KiprisLegalStatusClient()
    targets = _load_targets(companies_path)
    protected_before = hash_files(PROTECTED_PUBLIC_FILES)
    results: list[tuple[str, str, TechnologyCollectionResult]] = []
    reports: list[dict[str, Any]] = []
    access_unavailable = False

    for target in targets:
        if access_unavailable:
            reports.append(_access_report(target, "Legal-status access failed before this target was queried."))
            continue
        basic = legal_client.lookup(
            "basic", target["application_number"], collected_at=collected_at
        )
        results.append((target["technology_id"], "basic", basic))
        if basic.diagnostic.status in ACCESS_FAILURE_STATUSES:
            access_unavailable = True
            reports.append(_access_report(target, "KIPRISPlus ST.27 product access is unavailable."))
            continue

        stop_right = legal_client.lookup(
            "stop_right", target["application_number"], collected_at=collected_at
        )
        results.append((target["technology_id"], "stop_right", stop_right))
        if stop_right.diagnostic.status in ACCESS_FAILURE_STATUSES:
            access_unavailable = True
            reports.append(_access_report(target, "KIPRISPlus ST.27 product access is unavailable."))
            continue

        invalid_statuses = [
            result.diagnostic.status
            for result in (basic, stop_right)
            if result.diagnostic.status not in {"healthy", "empty_result"}
        ]
        if invalid_statuses:
            reports.append(_unresolved_source_report(target, invalid_statuses))
            continue

        adjudication = adjudicate_patent_status(basic.records, stop_right.records)
        reports.append({
            **target,
            "baseline_status": target["baseline_status"],
            "bibliographic_status": "expired",
            **adjudication,
            "status_update_candidate": (
                {"from": target["baseline_status"], "to": adjudication["current_status"]}
                if adjudication["decision"] == CONFIRMED_EXPIRED
                and target["baseline_status"] != adjudication["current_status"]
                else None
            ),
            "public_write_performed": False,
        })

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for technology_id, operation, result in results:
        for index, raw_page in enumerate(result.raw_pages, start=1):
            (raw_dir / f"{technology_id}-{operation}-{index:02d}.xml").write_text(
                raw_page, encoding="utf-8"
            )
        _write_json(
            raw_dir / f"{technology_id}-{operation}-diagnostic.json",
            result.diagnostic.as_dict(),
        )
    _write_json(output_dir / "status_adjudication_report.json", reports)

    counts = Counter(report["decision"] for report in reports)
    prior = _read_optional_object(prior_summary_path)
    prior_matched = prior.get("matched_official_count")
    resolved_count = counts[CONFIRMED_EXPIRED] + counts[CONFIRMED_REGISTERED_ACTIVE]
    protected_after = hash_files(PROTECTED_PUBLIC_FILES)
    summary = {
        "schema_version": "samsung-patent-status-adjudication-v1",
        "generated_at": collected_at,
        "target_technology_ids": [target["technology_id"] for target in targets],
        "status_field_semantics": CURRENT_LIFECYCLE_STATUS,
        "kipris_legal_status_configured": legal_client.configured(),
        "legal_status_operations": ["BasicInfo", "StopRightInfo"],
        "legal_status_endpoints": [
            KIPRIS_LEGAL_STATUS_BASIC_ENDPOINT,
            KIPRIS_LEGAL_STATUS_STOP_RIGHT_ENDPOINT,
        ],
        "request_count": sum(result.diagnostic.pages_requested for _, _, result in results),
        "http_statuses": sorted({
            result.diagnostic.http_status
            for _, _, result in results
            if result.diagnostic.http_status is not None
        }),
        "api_result_codes": sorted({
            result.diagnostic.api_result_code
            for _, _, result in results
            if result.diagnostic.api_result_code is not None
        }),
        "source_statuses": sorted({result.diagnostic.status for _, _, result in results}),
        "confirmed_expired_count": counts[CONFIRMED_EXPIRED],
        "confirmed_registered_active_count": counts[CONFIRMED_REGISTERED_ACTIVE],
        "unresolved_status_count": counts[UNRESOLVED_STATUS],
        "access_unavailable_count": counts[ACCESS_UNAVAILABLE],
        "status_update_candidate_count": sum(
            report.get("status_update_candidate") is not None for report in reports
        ),
        "remaining_conflict_count": counts[UNRESOLVED_STATUS] + counts[ACCESS_UNAVAILABLE],
        "prior_matched_official_count": prior_matched,
        "matched_official_count_after_adjudication": (
            int(prior_matched) + resolved_count if isinstance(prior_matched, int) else None
        ),
        "broad_applicant_request_count": 0,
        "baseline_exact_request_count": 0,
        "kaia_request_count": 0,
        "public_write_performed": False,
        "protected_public_hashes_before": protected_before,
        "protected_public_hashes_after": protected_after,
        "protected_public_data_unchanged": protected_before == protected_after,
        "security": {
            "credential_url_count": 0,
            "secret_exposure_count": 0,
            "raw_public_field_count": 0,
        },
    }
    summary["decision"] = _summary_decision(summary)
    _write_json(output_dir / "summary.json", summary)
    _write_markdown(output_dir / "report.md", summary, reports)
    summary["security"] = security_metrics(
        normalized_payload=[], candidates=[], output_dir=output_dir, secrets=(legal_client.api_key,)
    )
    summary["decision"] = _summary_decision(summary)
    _write_json(output_dir / "summary.json", summary)
    _write_markdown(output_dir / "report.md", summary, reports)
    return summary


def _summary_decision(summary: dict[str, Any]) -> str:
    security = summary["security"]
    if security["secret_exposure_count"] or security["credential_url_count"]:
        return "HOLD_FOR_KIPRIS_SECURITY_REVIEW"
    if summary["access_unavailable_count"]:
        return "HOLD_FOR_KIPRIS_LEGAL_STATUS_ACCESS"
    if summary["status_field_semantics"] != CURRENT_LIFECYCLE_STATUS:
        return "HOLD_FOR_TECHNOLOGY_STATUS_SEMANTICS"
    if summary["remaining_conflict_count"]:
        return "HOLD_FOR_MANUAL_PATENT_STATUS_REVIEW"
    if summary["confirmed_expired_count"] == len(TARGET_PATENTS):
        return "SAMSUNG_PATENT_STATUS_CONFLICT_RESOLVED"
    return "HOLD_FOR_MANUAL_PATENT_STATUS_REVIEW"


def _load_targets(companies_path: Path) -> list[dict[str, Any]]:
    companies = load_companies(companies_path)
    samsung = next(
        (row for row in companies if row.get("company_id") == "samsung-ct-construction"), None
    )
    if samsung is None:
        raise ValueError("Samsung C&T company baseline is missing")
    patents = {
        row.get("technology_id"): row
        for row in (samsung.get("technology") or {}).get("patents", [])
        if isinstance(row, dict)
    }
    targets = []
    for identity in TARGET_PATENTS:
        baseline = patents.get(identity["technology_id"])
        if not baseline:
            raise ValueError(f"target patent is missing: {identity['technology_id']}")
        if _digits(baseline.get("registration_number")) != _digits(identity["registration_number"]):
            raise ValueError(f"target registration identity changed: {identity['technology_id']}")
        targets.append({
            **identity,
            "title": baseline.get("name") or baseline.get("title"),
            "baseline_status": baseline.get("status"),
        })
    return targets


def _explicit_events(rows: Iterable[dict[str, Any]], terms: Iterable[str]) -> list[dict[str, Any]]:
    matches = []
    normalized_terms = tuple(term.casefold() for term in terms)
    for row in rows:
        labels = [
            str(value)
            for key, value in row.items()
            if any(token in key.casefold() for token in ("status", "eventname", "stagename", "statename"))
            and value not in (None, "")
        ]
        matching = [label for label in labels if any(term in label.casefold() for term in normalized_terms)]
        if matching:
            matches.append({
                "date": _pick_casefold(row, "eventDate"),
                "labels": matching,
            })
    return matches


def _pick_casefold(row: dict[str, Any], key: str) -> Any:
    expected = key.casefold()
    return next((value for name, value in row.items() if name.casefold() == expected), None)


def _date_key(value: Any) -> str:
    return re.sub(r"[^0-9]", "", str(value or ""))


def _digits(value: Any) -> str:
    return re.sub(r"[^0-9]", "", str(value or ""))


def _access_report(target: dict[str, Any], rationale: str) -> dict[str, Any]:
    return {
        **target,
        "baseline_status": target["baseline_status"],
        "bibliographic_status": "expired",
        "decision": ACCESS_UNAVAILABLE,
        "current_status": None,
        "status_field_semantics": CURRENT_LIFECYCLE_STATUS,
        "rationale": rationale,
        "termination_events": [],
        "explicit_active_events": [],
        "explicit_expired_events": [],
        "status_update_candidate": None,
        "public_write_performed": False,
    }


def _unresolved_source_report(target: dict[str, Any], statuses: list[str]) -> dict[str, Any]:
    report = _access_report(
        target,
        f"Legal-status source diagnostics were not healthy: {', '.join(sorted(set(statuses)))}.",
    )
    report["decision"] = UNRESOLVED_STATUS
    return report


def _read_optional_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_markdown(path: Path, summary: dict[str, Any], reports: list[dict[str, Any]]) -> None:
    lines = [
        "# Samsung patent lifecycle status adjudication",
        "",
        f"- Decision: `{summary['decision']}`",
        f"- Status semantics: `{summary['status_field_semantics']}`",
        f"- Requests: {summary['request_count']}",
        f"- Confirmed expired: {summary['confirmed_expired_count']}",
        f"- Confirmed active: {summary['confirmed_registered_active_count']}",
        f"- Remaining conflicts: {summary['remaining_conflict_count']}",
        f"- Public write performed: {str(summary['public_write_performed']).lower()}",
        f"- Protected public data unchanged: {str(summary['protected_public_data_unchanged']).lower()}",
        f"- Secret exposure count: {summary['security']['secret_exposure_count']}",
        "",
        "## Records",
        "",
    ]
    for report in reports:
        lines.extend([
            f"### {report['technology_id']}",
            f"- Decision: `{report['decision']}`",
            f"- Baseline status: `{report['baseline_status']}`",
            f"- Adjudicated status: `{report.get('current_status') or 'unresolved'}`",
            f"- Rationale: {report['rationale']}",
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Adjudicate two Samsung patent lifecycle conflicts")
    parser.add_argument("--companies", type=Path, default=DEFAULT_COMPANIES)
    parser.add_argument("--prior-summary", type=Path, default=DEFAULT_PRIOR_SUMMARY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    summary = run_status_adjudication(
        companies_path=args.companies,
        prior_summary_path=args.prior_summary,
        output_dir=args.output_dir,
    )
    print(json.dumps({
        "decision": summary["decision"],
        "kipris_legal_status_configured": summary["kipris_legal_status_configured"],
        "request_count": summary["request_count"],
        "http_statuses": summary["http_statuses"],
        "confirmed_expired_count": summary["confirmed_expired_count"],
        "remaining_conflict_count": summary["remaining_conflict_count"],
        "secret_exposure_count": summary["security"]["secret_exposure_count"],
    }, ensure_ascii=False, indent=2))
    return 0 if summary["decision"] == "SAMSUNG_PATENT_STATUS_CONFLICT_RESOLVED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
