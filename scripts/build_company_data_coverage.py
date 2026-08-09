#!/usr/bin/env python3
"""Build company data coverage and freshness control-plane artifacts.

The builder is intentionally observational: it reads the current public company
universe and existing audit-financial view model, then emits state labels and
data-gap work items. It does not score companies and it does not promote or
modify audit-financial source values.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPANIES = ROOT / "frontend" / "public" / "data" / "companies" / "companies.json"
DEFAULT_REPORT_INSIGHTS = ROOT / "frontend" / "public" / "data" / "companies" / "company_report_insights.json"
DEFAULT_SUPPLEMENTS = ROOT / "frontend" / "src" / "data" / "publicCompanySupplements.json"
DEFAULT_AUDIT_SOURCE_ROOT = ROOT / "data" / "company_reports"
DEFAULT_ARTIFACT_DIR = ROOT / "artifacts" / "company-data-coverage"
DEFAULT_SNAPSHOT = ROOT / "data" / "company_reports" / "company_data_coverage_snapshot.json"

SCHEMA_VERSION = "company_data_coverage_v1"
EXPECTED_AUDIT_YEARS = 3
REQUIRED_AUDIT_METRICS = [
    "revenue",
    "gross_profit",
    "operating_profit",
    "net_income",
    "operating_cash_flow",
    "total_assets",
    "total_liabilities",
    "total_equity",
    "total_borrowings",
    "receivables_total",
]
OPTIONAL_AUDIT_METRICS = [
    "inventory",
    "work_in_progress",
    "current_assets",
    "current_liabilities",
]
VERIFIED_STATUSES = {"verified", "cross_verified", "official_verified", "verified_section_range"}
CONFIRMED_FACILITY_STATUSES = {"confirmed_own_facility", "confirmed_partner_facility", "confirmed_affiliate_facility"}
PROJECT_CREDIT_STATUSES = {"completed", "under_construction", "contracted", "awarded"}

REASON_DOMAIN = {
    "audit_record_without_company_master": "consistency",
    "audit_insight_without_public_source": "consistency",
    "public_source_without_audit_insight": "consistency",
    "verified_cross_source_conflict": "consistency",
    "critical_source_stale": "consistency",
    "future_verification_date": "consistency",
    "supplemental_profile_not_canonicalized": "consistency",
    "missing_audit_financials": "financial",
    "audit_years_incomplete": "financial",
    "audit_data_stale": "financial",
    "financial_scope_unknown": "financial",
    "missing_operating_cash_flow": "financial",
    "missing_borrowings": "financial",
    "missing_receivables": "financial",
    "production_capacity_unknown": "production",
    "production_verification_stale": "production",
    "project_evidence_sparse": "project",
    "technology_evidence_sparse": "technology",
    "company_profile_stale": "identity",
    "excessive_verification_pending": "evidence",
    "source_coverage_sparse": "evidence",
}

PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


@dataclass(frozen=True)
class FreshnessPolicy:
    current_days: int
    aging_days: int


FRESHNESS_POLICIES = {
    "company_profile": FreshnessPolicy(current_days=365, aging_days=730),
    "production": FreshnessPolicy(current_days=365, aging_days=548),
    "project": FreshnessPolicy(current_days=548, aging_days=730),
    "technology": FreshnessPolicy(current_days=730, aging_days=1095),
}


def stable_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_date(value: Any) -> date | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        pass
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return datetime.strptime(text, "%Y-%m-%d").date()
    if re.fullmatch(r"\d{4}-\d{2}", text):
        return datetime.strptime(text, "%Y-%m").date()
    if re.fullmatch(r"\d{4}", text):
        return datetime.strptime(text, "%Y").date()
    return None


def date_is_future(value: Any, as_of_date: date) -> bool:
    parsed = parse_date(value)
    return bool(parsed and parsed > as_of_date)


def latest_date(values: list[Any]) -> str | None:
    parsed = [item for item in (parse_date(value) for value in values) if item]
    return max(parsed).isoformat() if parsed else None


def oldest_date(values: list[Any]) -> str | None:
    parsed = [item for item in (parse_date(value) for value in values) if item]
    return min(parsed).isoformat() if parsed else None


def freshness_state(value: str | None, as_of_date: date, policy: FreshnessPolicy) -> str:
    parsed = parse_date(value)
    if parsed is None:
        return "unknown"
    age_days = (as_of_date - parsed).days
    if age_days <= policy.current_days:
        return "current"
    if age_days <= policy.aging_days:
        return "aging"
    return "stale"


def load_company_universe(path: Path = DEFAULT_COMPANIES) -> list[dict[str, Any]]:
    payload = load_json(path)
    companies = payload.get("companies")
    if not isinstance(companies, list):
        raise ValueError(f"{path} does not contain a companies list")
    return sorted(companies, key=lambda item: item.get("company_id", ""))


def load_report_insights(path: Path = DEFAULT_REPORT_INSIGHTS) -> list[dict[str, Any]]:
    payload = load_json(path)
    companies = payload.get("companies")
    if not isinstance(companies, list):
        raise ValueError(f"{path} does not contain a companies list")
    return sorted(companies, key=lambda item: item.get("company_id", ""))


def load_supplemental_companies(path: Path = DEFAULT_SUPPLEMENTS) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = load_json(path)
    if payload.get("schema_version") != "public_company_supplements_v1":
        raise ValueError(f"{path} does not contain public_company_supplements_v1")
    companies = payload.get("companies")
    if not isinstance(companies, list):
        raise ValueError(f"{path} does not contain a companies list")
    return sorted(companies, key=lambda item: item.get("company_id", ""))


def effective_company_universe(
    canonical_companies: list[dict[str, Any]],
    supplemental_companies: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    effective: list[dict[str, Any]] = []
    seen: set[str] = set()
    for company in canonical_companies:
        record = dict(company)
        record["company_record_source"] = "canonical"
        effective.append(record)
        seen.add(company["company_id"])
    for company in supplemental_companies:
        company_id = company.get("company_id")
        if not company_id or company_id in seen:
            continue
        record = dict(company)
        record["company_record_source"] = "supplemental"
        effective.append(record)
        seen.add(company_id)
    return sorted(effective, key=lambda item: item.get("company_id", ""))


def load_audit_source(company_id: str, source_root: Path = DEFAULT_AUDIT_SOURCE_ROOT) -> dict[str, Any] | None:
    discovered = discover_public_audit_source(company_id, source_root)
    path = discovered["path"]
    if path is None:
        return None
    payload = load_json(path)
    if payload.get("schema_version") != "company_audit_financials_v1":
        return None
    return payload


def financial_year_span(payload: dict[str, Any]) -> tuple[int, int]:
    years = [int(year) for year in payload.get("financial_years", {}) if str(year).isdigit()]
    if not years:
        return (0, 0)
    return (min(years), max(years))


def discover_public_audit_source(company_id: str, source_root: Path = DEFAULT_AUDIT_SOURCE_ROOT) -> dict[str, Any]:
    """Return the deterministic public audit source candidate for a company.

    Public audit sources live directly below data/company_reports/<company-id>/.
    Staging, onboarding, artifacts, and candidate files are intentionally
    excluded so in-progress onboarding work is not treated as public coverage.
    """

    company_dir = source_root / company_id
    if not company_dir.exists():
        return {"status": "missing", "path": None, "candidate_paths": [], "ambiguous": False}
    candidates: list[tuple[int, int, str, Path]] = []
    for path in sorted(company_dir.glob("audit_financials_*.json")):
        relative_parts = {part.lower() for part in path.relative_to(company_dir).parts[:-1]}
        filename = path.name.lower()
        if relative_parts & {"onboarding", "staging", "artifacts"}:
            continue
        if "candidate" in filename:
            continue
        try:
            payload = load_json(path)
        except json.JSONDecodeError:
            continue
        if payload.get("schema_version") != "company_audit_financials_v1":
            continue
        first_year, latest_year = financial_year_span(payload)
        candidates.append((latest_year, first_year, path.name, path))
    if not candidates:
        return {"status": "missing", "path": None, "candidate_paths": [], "ambiguous": False}
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    top = candidates[0]
    same_span = [item for item in candidates if item[0] == top[0] and item[1] == top[1]]
    return {
        "status": "ambiguous" if len(same_span) > 1 else "found",
        "path": top[3],
        "candidate_paths": [item[3] for item in candidates],
        "ambiguous": len(same_span) > 1,
    }


def metric_status(metric: dict[str, Any] | None) -> str:
    if not isinstance(metric, dict):
        return "missing"
    if metric.get("raw_krw") is not None:
        return "reported"
    status = metric.get("disclosure_status") or metric.get("calculation_basis")
    if status in {"not_disclosed", "not_applicable", "verification_pending"}:
        return status
    return "missing"


def coverage_for_metrics(insight: dict[str, Any] | None, metric_ids: list[str]) -> dict[str, Any]:
    coverage: dict[str, Any] = {}
    series = insight.get("financial_series", []) if insight else []
    for metric_id in metric_ids:
        counts = Counter()
        by_year: dict[str, str] = {}
        for row in series:
            year = str(row.get("year"))
            status = metric_status(row.get("metrics", {}).get(metric_id))
            counts[status] += 1
            by_year[year] = status
        coverage[metric_id] = {
            "reported": counts["reported"],
            "not_disclosed": counts["not_disclosed"],
            "not_applicable": counts["not_applicable"],
            "verification_pending": counts["verification_pending"],
            "missing": counts["missing"],
            "by_year": by_year,
        }
    return coverage


def metric_status_counts(metric_coverage: dict[str, Any]) -> Counter:
    counts = Counter()
    for metric in metric_coverage.values():
        for key in ["reported", "not_disclosed", "not_applicable", "verification_pending", "missing"]:
            counts[key] += int(metric.get(key, 0))
    return counts


def audit_state(insight: dict[str, Any] | None, as_of_date: date, required_coverage: dict[str, Any]) -> str:
    if not insight:
        return "unavailable"
    years = insight.get("available_years") or []
    latest_year = insight.get("latest_year")
    counts = metric_status_counts(required_coverage)
    if counts["verification_pending"] > 0 or insight.get("source_summary", {}).get("pending_location_count", 0) > 0:
        return "verification_pending"
    if len(years) >= EXPECTED_AUDIT_YEARS and latest_year and int(latest_year) >= as_of_date.year - 1 and counts["missing"] == 0:
        return "complete"
    return "partial"


def audit_freshness_state(insight: dict[str, Any] | None, as_of_date: date) -> str:
    if not insight:
        return "unknown"
    latest_year = insight.get("latest_year")
    if not latest_year:
        return "unknown"
    gap = as_of_date.year - int(latest_year)
    if gap <= 1:
        return "current"
    if gap <= 2:
        return "aging"
    return "stale"


def verified_item(item: dict[str, Any]) -> bool:
    status = item.get("verification_status") or item.get("evidence_status")
    return status in VERIFIED_STATUSES


def production_summary(company: dict[str, Any], as_of_date: date) -> dict[str, Any]:
    facilities = company.get("production") or []
    verified = [
        item
        for item in facilities
        if verified_item(item)
        and (item.get("own_facility_status") in CONFIRMED_FACILITY_STATUSES or item.get("operation_status") == "active")
    ]
    dates = [item.get("verified_at") or item.get("last_verified_at") for item in facilities]
    latest_verified_at = latest_date(dates)
    return {
        "production_facility_count": len(facilities),
        "verified_production_facility_count": len(verified),
        "production_capacity_available": any(
            item.get("reported_capacity") is not None
            or item.get("capacity_value") is not None
            or item.get("capacity_status") not in {None, "unavailable", "unknown"}
            for item in verified
        ),
        "production_verified_at": latest_verified_at,
        "production_freshness_state": freshness_state(latest_verified_at, as_of_date, FRESHNESS_POLICIES["production"]),
    }


def project_summary(company: dict[str, Any], as_of_date: date) -> dict[str, Any]:
    projects = company.get("project_portfolio") or []
    verified = [
        item
        for item in projects
        if item.get("project_credit") is True
        and item.get("project_status") in PROJECT_CREDIT_STATUSES
        and (verified_item(item) or item.get("evidence_status") == "verified")
    ]
    dates = [
        item.get("verified_at") or item.get("completion_date") or item.get("contract_date") or item.get("announced_at")
        for item in projects
    ]
    latest_verified_at = latest_date(dates)
    return {
        "project_count": len(projects),
        "verified_project_count": len(verified),
        "project_verified_at": latest_verified_at,
        "project_freshness_state": freshness_state(latest_verified_at, as_of_date, FRESHNESS_POLICIES["project"]),
    }


def technology_items(company: dict[str, Any]) -> list[dict[str, Any]]:
    tech = company.get("technology") or {}
    items: list[dict[str, Any]] = []
    if isinstance(tech, dict):
        for value in tech.values():
            if isinstance(value, list):
                items.extend(item for item in value if isinstance(item, dict))
    elif isinstance(tech, list):
        items.extend(item for item in tech if isinstance(item, dict))
    return items


def technology_summary(company: dict[str, Any], as_of_date: date) -> dict[str, Any]:
    items = technology_items(company)
    verified = [item for item in items if verified_item(item) or item.get("status") in {"registered", "active"}]
    dates = [item.get("verified_at") or item.get("registered_at") or item.get("registration_date") for item in items]
    latest_verified_at = latest_date(dates)
    return {
        "technology_count": len(items),
        "verified_technology_count": len(verified),
        "technology_verified_at": latest_verified_at,
        "technology_freshness_state": freshness_state(latest_verified_at, as_of_date, FRESHNESS_POLICIES["technology"]),
    }


def evidence_summary(company: dict[str, Any], insight: dict[str, Any] | None) -> dict[str, Any]:
    sources = company.get("sources") or []
    source_count = len(sources)
    verified_source_count = sum(1 for source in sources if source.get("confidence") == "high" or source.get("primary_source") is True)
    pending_source_count = sum(1 for source in sources if source.get("confidence") in {"pending", "low"} or source.get("review_status") == "pending")
    not_disclosed_count = 0
    verification_pending_count = 0
    manual_page_check_count = 0
    if insight:
        for row in insight.get("evidence_health") or []:
            not_disclosed_count += int(row.get("not_disclosed_item_count", 0))
            verification_pending_count += int(row.get("verification_pending_item_count", 0))
        manual_page_check_count = int(insight.get("data_quality", {}).get("pending_manual_page_check_count", 0))
    if verified_source_count and not pending_source_count and not manual_page_check_count:
        state = "verified"
    elif verified_source_count and (pending_source_count or manual_page_check_count):
        state = "mixed"
    elif pending_source_count or manual_page_check_count:
        state = "pending"
    else:
        state = "sparse"
    return {
        "source_count": source_count,
        "verified_source_count": verified_source_count,
        "pending_source_count": pending_source_count,
        "not_disclosed_count": not_disclosed_count,
        "verification_pending_count": verification_pending_count,
        "manual_page_check_count": manual_page_check_count,
        "evidence_coverage_state": state,
    }


def operational_state(production: dict[str, Any], projects: dict[str, Any], technology: dict[str, Any]) -> str:
    verified_domains = sum(
        [
            production["verified_production_facility_count"] > 0,
            projects["verified_project_count"] > 0,
            technology["verified_technology_count"] > 0,
        ]
    )
    if verified_domains >= 2:
        return "sufficiently_covered"
    if verified_domains == 1:
        return "partial"
    if production["production_facility_count"] or projects["project_count"] or technology["technology_count"]:
        return "sparse"
    return "unavailable"


def combined_freshness_state(states: list[str]) -> str:
    if not states or all(state == "unknown" for state in states):
        return "unknown"
    if "stale" in states:
        return "stale"
    if "aging" in states:
        return "aging"
    if all(state in {"current", "unknown"} for state in states):
        return "current"
    return "unknown"


def priority_for_reasons(reasons: list[str]) -> str:
    if not reasons:
        return "P3"
    if any(
        reason
        in {
            "audit_record_without_company_master",
            "audit_insight_without_public_source",
            "public_source_without_audit_insight",
            "verified_cross_source_conflict",
            "critical_source_stale",
            "future_verification_date",
        }
        for reason in reasons
    ):
        return "P0"
    if "supplemental_profile_not_canonicalized" in reasons:
        return "P2"
    if any(reason in {"missing_audit_financials", "audit_years_incomplete", "audit_data_stale", "excessive_verification_pending"} for reason in reasons):
        return "P1"
    if any(
        reason
        in {
            "missing_operating_cash_flow",
            "missing_borrowings",
            "missing_receivables",
            "production_capacity_unknown",
            "production_verification_stale",
            "project_evidence_sparse",
            "company_profile_stale",
            "source_coverage_sparse",
        }
        for reason in reasons
    ):
        return "P2"
    return "P3"


def next_action_for_reasons(reasons: list[str]) -> str:
    if any(reason in {"audit_record_without_company_master", "audit_insight_without_public_source", "public_source_without_audit_insight"} for reason in reasons):
        return "company_universe_reconciliation"
    if "supplemental_profile_not_canonicalized" in reasons:
        return "canonical_company_migration"
    if "future_verification_date" in reasons:
        return "source_date_reconciliation"
    if "missing_audit_financials" in reasons:
        return "audit_report_onboarding"
    if "audit_data_stale" in reasons or "audit_years_incomplete" in reasons:
        return "audit_report_refresh"
    if any(reason.startswith("missing_") for reason in reasons):
        return "audit_metric_reconciliation"
    if any(reason.startswith("production_") for reason in reasons):
        return "production_source_refresh"
    if "project_evidence_sparse" in reasons:
        return "project_evidence_review"
    if "technology_evidence_sparse" in reasons:
        return "technology_source_review"
    if "company_profile_stale" in reasons:
        return "company_profile_refresh"
    if "source_coverage_sparse" in reasons:
        return "source_registry_review"
    return "monitor"


def next_domain_for_reasons(reasons: list[str]) -> str:
    if "supplemental_profile_not_canonicalized" in reasons:
        return "consistency"
    return REASON_DOMAIN.get(reasons[0], "monitoring") if reasons else "monitoring"


def recommendation_reasons(
    company: dict[str, Any],
    insight: dict[str, Any] | None,
    audit_coverage_state: str,
    audit_freshness: str,
    required_coverage: dict[str, Any],
    production: dict[str, Any],
    projects: dict[str, Any],
    technology: dict[str, Any],
    evidence: dict[str, Any],
    profile_freshness: str,
    as_of_date: date,
) -> list[str]:
    reasons: list[str] = []
    if not insight:
        reasons.append("missing_audit_financials")
    elif audit_coverage_state == "partial":
        reasons.append("audit_years_incomplete")
    elif audit_coverage_state == "verification_pending":
        reasons.append("excessive_verification_pending")
    if audit_freshness == "stale":
        reasons.append("audit_data_stale")
    if insight and insight.get("financial_scope") not in {"standalone", "consolidated", "standalone_and_consolidated"}:
        reasons.append("financial_scope_unknown")
    metric_reason_map = {
        "operating_cash_flow": "missing_operating_cash_flow",
        "total_borrowings": "missing_borrowings",
        "receivables_total": "missing_receivables",
    }
    for metric_id, reason in metric_reason_map.items():
        metric = required_coverage.get(metric_id, {})
        if int(metric.get("missing", 0)) or int(metric.get("verification_pending", 0)):
            reasons.append(reason)
    if production["verified_production_facility_count"] and not production["production_capacity_available"]:
        reasons.append("production_capacity_unknown")
    if production["production_freshness_state"] == "stale":
        reasons.append("production_verification_stale")
    if projects["verified_project_count"] == 0:
        reasons.append("project_evidence_sparse")
    if technology["verified_technology_count"] == 0:
        reasons.append("technology_evidence_sparse")
    if profile_freshness == "stale":
        reasons.append("company_profile_stale")
    if evidence["verified_source_count"] == 0 or evidence["source_count"] == 0:
        reasons.append("source_coverage_sparse")
    if company.get("company_record_source") == "supplemental":
        reasons.append("supplemental_profile_not_canonicalized")
    critical_dates = [
        company.get("last_verified_at"),
        production["production_verified_at"],
        projects["project_verified_at"],
        technology["technology_verified_at"],
        insight.get("source_summary", {}).get("latest_report_date") if insight else None,
    ]
    if any(date_is_future(value, as_of_date) for value in critical_dates):
        reasons.append("future_verification_date")
    return sorted(set(reasons), key=lambda reason: (PRIORITY_ORDER[priority_for_reasons([reason])], reason))


def build_company_coverage(company: dict[str, Any], insight: dict[str, Any] | None, as_of_date: date) -> dict[str, Any]:
    required_coverage = coverage_for_metrics(insight, REQUIRED_AUDIT_METRICS)
    optional_coverage = coverage_for_metrics(insight, OPTIONAL_AUDIT_METRICS)
    audit_coverage_state = audit_state(insight, as_of_date, required_coverage)
    audit_freshness = audit_freshness_state(insight, as_of_date)
    production = production_summary(company, as_of_date)
    projects = project_summary(company, as_of_date)
    technology = technology_summary(company, as_of_date)
    evidence = evidence_summary(company, insight)
    profile_verified_at = company.get("last_verified_at")
    profile_freshness = freshness_state(profile_verified_at, as_of_date, FRESHNESS_POLICIES["company_profile"])
    freshness = combined_freshness_state(
        [
            profile_freshness,
            production["production_freshness_state"],
            projects["project_freshness_state"],
            technology["technology_freshness_state"],
            audit_freshness,
        ]
    )
    reasons = recommendation_reasons(
        company,
        insight,
        audit_coverage_state,
        audit_freshness,
        required_coverage,
        production,
        projects,
        technology,
        evidence,
        profile_freshness,
        as_of_date,
    )
    next_action = next_action_for_reasons(reasons)
    priority = priority_for_reasons(reasons)
    oldest_critical = oldest_date(
        [
            profile_verified_at,
            production["production_verified_at"],
            projects["project_verified_at"],
            technology["technology_verified_at"],
            insight.get("source_summary", {}).get("latest_report_date") if insight else None,
        ]
    )
    return {
        "company_id": company["company_id"],
        "company_name": company.get("company_name"),
        "company_record_source": company.get("company_record_source", "canonical"),
        "company_master_present": True,
        "company_profile_present": bool(company.get("company_profile") or company.get("summary")),
        "headquarters_present": bool(company.get("headquarters")),
        "representative_present": bool((company.get("company_profile") or {}).get("representative") or company.get("representative")),
        "website_present": bool(company.get("website_url")),
        "audit_financials_available": bool(insight),
        "audit_years": insight.get("available_years", []) if insight else [],
        "latest_audit_year": insight.get("latest_year") if insight else None,
        "financial_scope": insight.get("financial_scope") if insight else None,
        "accounting_standard": (load_audit_source(company["company_id"]) or {}).get("accounting_standard") if insight else None,
        "latest_report_date": insight.get("source_summary", {}).get("latest_report_date") if insight else None,
        "source_document_count": len(insight.get("source_summary", {}).get("primary_documents", [])) if insight else 0,
        "required_metric_coverage": required_coverage,
        "optional_metric_coverage": optional_coverage,
        **production,
        **projects,
        **technology,
        **evidence,
        "company_profile_verified_at": profile_verified_at,
        "audit_latest_report_date": insight.get("source_summary", {}).get("latest_report_date") if insight else None,
        "oldest_critical_verification_date": oldest_critical,
        "audit_coverage_state": audit_coverage_state,
        "operational_coverage_state": operational_state(production, projects, technology),
        "freshness_state": freshness,
        "recommended_next_action": next_action,
        "recommended_next_domain": next_domain_for_reasons(reasons),
        "recommendation_priority": priority,
        "recommendation_reason_codes": reasons,
    }


def company_priority_queue(companies: list[dict[str, Any]], company_id: str | None = None, priority: str | None = None) -> list[dict[str, Any]]:
    queue = []
    for company in companies:
        reasons = company["recommendation_reason_codes"]
        if not reasons:
            continue
        item_type = "maintenance_issue" if "supplemental_profile_not_canonicalized" in reasons else "company_data_gap"
        item = {
            "item_type": item_type,
            "priority": company["recommendation_priority"],
            "company_id": company["company_id"],
            "company_name": company["company_name"],
            "recommended_next_action": company["recommended_next_action"],
            "recommended_next_domain": company["recommended_next_domain"],
            "reason_codes": reasons,
        }
        queue.append(item)
    if company_id:
        queue = [item for item in queue if item["company_id"] == company_id]
    if priority:
        queue = [item for item in queue if item["priority"] == priority]
    return sorted(queue, key=lambda item: (PRIORITY_ORDER[item["priority"]], item["company_id"]))


def public_audit_source_company_ids(source_root: Path = DEFAULT_AUDIT_SOURCE_ROOT) -> set[str]:
    ids: set[str] = set()
    if not source_root.exists():
        return ids
    for company_dir in source_root.iterdir():
        if not company_dir.is_dir():
            continue
        discovered = discover_public_audit_source(company_dir.name, source_root)
        if discovered["path"] is not None:
            ids.add(company_dir.name)
    return ids


def build_consistency(
    company_ids: list[str],
    audit_company_ids: list[str],
    source_root: Path = DEFAULT_AUDIT_SOURCE_ROOT,
) -> dict[str, Any]:
    company_set = set(company_ids)
    audit_set = set(audit_company_ids)
    public_source_ids = public_audit_source_company_ids(source_root)
    audit_without_master = sorted(audit_set - company_set)
    master_without_audit = sorted(company_set - audit_set)
    insight_without_source = sorted(audit_set - public_source_ids)
    source_without_insight = sorted(public_source_ids - audit_set)
    issues: list[dict[str, Any]] = []
    for company_id in audit_without_master:
        issues.append(
            {
                "issue_type": "audit_record_without_company_master",
                "company_id": company_id,
                "reason_code": "audit_record_without_company_master",
            }
        )
    for company_id in insight_without_source:
        issues.append(
            {
                "issue_type": "audit_insight_without_public_source",
                "company_id": company_id,
                "reason_code": "audit_insight_without_public_source",
            }
        )
    for company_id in source_without_insight:
        issues.append(
            {
                "issue_type": "public_source_without_audit_insight",
                "company_id": company_id,
                "reason_code": "public_source_without_audit_insight",
            }
        )
    reason_codes = sorted({issue["reason_code"] for issue in issues})
    return {
        "status": "issue_detected" if issues else "clean",
        "issue_count": len(issues),
        "issues": sorted(issues, key=lambda item: (item["issue_type"], item["company_id"])),
        "reason_codes": reason_codes,
        "audit_record_without_company_master_ids": audit_without_master,
        "company_master_without_audit_record_ids": master_without_audit,
        "audit_insight_without_public_source_ids": insight_without_source,
        "public_source_without_audit_insight_ids": source_without_insight,
    }


def consistency_priority_queue(consistency: dict[str, Any], insight_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for issue in consistency.get("issues", []):
        company_id = issue["company_id"]
        reason = issue["reason_code"]
        items.append(
            {
                "item_type": "consistency_issue",
                "priority": priority_for_reasons([reason]),
                "company_id": company_id,
                "company_name": (insight_by_id.get(company_id) or {}).get("company_name"),
                "recommended_next_action": next_action_for_reasons([reason]),
                "recommended_next_domain": REASON_DOMAIN.get(reason, "consistency"),
                "reason_codes": [reason],
            }
        )
    return sorted(items, key=lambda item: (PRIORITY_ORDER[item["priority"]], item["company_id"], item["reason_codes"]))


def build_payload(
    as_of_date: date,
    companies_path: Path = DEFAULT_COMPANIES,
    report_insights_path: Path = DEFAULT_REPORT_INSIGHTS,
    supplements_path: Path = DEFAULT_SUPPLEMENTS,
    source_root: Path = DEFAULT_AUDIT_SOURCE_ROOT,
    company_id: str | None = None,
    priority: str | None = None,
) -> dict[str, Any]:
    canonical_companies = load_company_universe(companies_path)
    supplemental_companies = load_supplemental_companies(supplements_path)
    companies = effective_company_universe(canonical_companies, supplemental_companies)
    insights = load_report_insights(report_insights_path)
    canonical_company_ids = [company["company_id"] for company in canonical_companies]
    supplemental_company_ids = [company["company_id"] for company in supplemental_companies]
    company_ids = [company["company_id"] for company in companies]
    insight_by_id = {company["company_id"]: company for company in insights}
    audit_company_ids = sorted(insight_by_id)
    if company_id:
        companies = [company for company in companies if company["company_id"] == company_id]

    coverage_companies = [build_company_coverage(company, insight_by_id.get(company["company_id"]), as_of_date) for company in companies]
    audit_backed_in_canonical = [company_id for company_id in canonical_company_ids if company_id in insight_by_id]
    audit_backed_in_universe = [company_id for company_id in company_ids if company_id in insight_by_id]
    non_audit_company_ids = [company_id for company_id in company_ids if company_id not in insight_by_id]
    audit_not_in_universe = sorted(set(audit_company_ids) - set(company_ids))
    consistency = build_consistency(company_ids, audit_company_ids, source_root=source_root)
    audit_state_counts = Counter(company["audit_coverage_state"] for company in coverage_companies)
    freshness_counts = Counter(company["freshness_state"] for company in coverage_companies)
    operational_counts = Counter(company["operational_coverage_state"] for company in coverage_companies)
    evidence_counts = Counter(company["evidence_coverage_state"] for company in coverage_companies)
    company_queue = company_priority_queue(coverage_companies, company_id=company_id, priority=priority)
    consistency_queue = consistency_priority_queue(consistency, insight_by_id)
    if company_id:
        consistency_queue = [item for item in consistency_queue if item["company_id"] == company_id]
    if priority:
        consistency_queue = [item for item in consistency_queue if item["priority"] == priority]
    queue = sorted(company_queue + consistency_queue, key=lambda item: (PRIORITY_ORDER[item["priority"]], item["item_type"], item["company_id"], item["reason_codes"]))
    company_priority_counts = Counter(company["recommendation_priority"] for company in coverage_companies)
    work_item_priority_counts = Counter(item["priority"] for item in queue)
    full_three_year_audit_record_count = sum(1 for item in insights if len(item.get("available_years") or []) >= EXPECTED_AUDIT_YEARS)
    full_three_year_audit_in_canonical_count = sum(
        1 for item in insights if item["company_id"] in canonical_company_ids and len(item.get("available_years") or []) >= EXPECTED_AUDIT_YEARS
    )
    full_three_year_audit_in_universe_count = sum(
        1 for item in insights if item["company_id"] in company_ids and len(item.get("available_years") or []) >= EXPECTED_AUDIT_YEARS
    )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "as_of_date": as_of_date.isoformat(),
        "generated_at": f"{as_of_date.isoformat()}T00:00:00Z",
        "summary": {
            "total_company_count": len(company_ids),
            "canonical_company_count": len(canonical_company_ids),
            "supplemental_public_company_count": len(set(supplemental_company_ids) - set(canonical_company_ids)),
            "effective_public_company_count": len(company_ids),
            "audit_record_count": len(audit_company_ids),
            "audit_backed_company_count": len(audit_company_ids),
            "audit_backed_in_canonical_universe_count": len(audit_backed_in_canonical),
            "audit_backed_in_universe_count": len(audit_backed_in_universe),
            "audit_backed_in_effective_universe_count": len(audit_backed_in_universe),
            "non_audit_company_count": len(non_audit_company_ids),
            "full_three_year_audit_count": full_three_year_audit_record_count,
            "full_three_year_audit_record_count": full_three_year_audit_record_count,
            "full_three_year_audit_in_canonical_universe_count": full_three_year_audit_in_canonical_count,
            "full_three_year_audit_in_universe_count": full_three_year_audit_in_universe_count,
            "full_three_year_audit_in_effective_universe_count": full_three_year_audit_in_universe_count,
            "canonical_company_ids": canonical_company_ids,
            "supplemental_company_ids": supplemental_company_ids,
            "effective_public_company_ids": company_ids,
            "company_ids": company_ids,
            "audit_company_ids": audit_company_ids,
            "audit_company_ids_not_in_universe": audit_not_in_universe,
            "non_audit_company_ids": non_audit_company_ids,
            "audit_coverage_state_counts": dict(sorted(audit_state_counts.items())),
            "operational_coverage_state_counts": dict(sorted(operational_counts.items())),
            "evidence_coverage_state_counts": dict(sorted(evidence_counts.items())),
            "freshness_state_counts": dict(sorted(freshness_counts.items())),
            "company_priority_counts": {key: company_priority_counts.get(key, 0) for key in ["P0", "P1", "P2", "P3"]},
            "work_item_priority_counts": {key: work_item_priority_counts.get(key, 0) for key in ["P0", "P1", "P2", "P3"]},
            "priority_counts": {key: work_item_priority_counts.get(key, 0) for key in ["P0", "P1", "P2", "P3"]},
        },
        "consistency": consistency,
        "companies": coverage_companies,
        "company_priority_queue": company_queue,
        "consistency_priority_queue": consistency_queue,
        "priority_queue": queue,
        "stale_domains": [
            {
                "company_id": company["company_id"],
                "company_name": company["company_name"],
                "freshness_state": company["freshness_state"],
                "oldest_critical_verification_date": company["oldest_critical_verification_date"],
            }
            for company in coverage_companies
            if company["freshness_state"] in {"aging", "stale", "unknown"}
        ],
        "audit_coverage": {
            "state_counts": dict(sorted(audit_state_counts.items())),
            "audit_record_count": len(audit_company_ids),
            "audit_company_ids": audit_company_ids,
            "audit_company_ids_not_in_universe": audit_not_in_universe,
            "audit_backed_in_canonical_universe_count": len(audit_backed_in_canonical),
            "audit_backed_in_universe_count": len(audit_backed_in_universe),
            "audit_backed_in_effective_universe_count": len(audit_backed_in_universe),
            "full_three_year_audit_record_count": full_three_year_audit_record_count,
            "full_three_year_audit_in_canonical_universe_count": full_three_year_audit_in_canonical_count,
            "full_three_year_audit_in_universe_count": full_three_year_audit_in_universe_count,
            "full_three_year_audit_in_effective_universe_count": full_three_year_audit_in_universe_count,
        },
        "evidence_coverage": {
            "state_counts": dict(sorted(evidence_counts.items())),
            "manual_page_check_company_ids": [
                company["company_id"] for company in coverage_companies if company["manual_page_check_count"] > 0
            ],
        },
    }
    return payload


def build_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": payload["schema_version"],
        "as_of_date": payload["as_of_date"],
        "company_count": payload["summary"]["total_company_count"],
        "canonical_company_count": payload["summary"]["canonical_company_count"],
        "supplemental_public_company_count": payload["summary"]["supplemental_public_company_count"],
        "effective_public_company_count": payload["summary"]["effective_public_company_count"],
        "audit_record_count": payload["summary"]["audit_record_count"],
        "audit_backed_count": payload["summary"]["audit_backed_company_count"],
        "audit_backed_in_universe_count": payload["summary"]["audit_backed_in_universe_count"],
        "audit_backed_in_effective_universe_count": payload["summary"]["audit_backed_in_effective_universe_count"],
        "full_three_year_audit_record_count": payload["summary"]["full_three_year_audit_record_count"],
        "full_three_year_audit_in_universe_count": payload["summary"]["full_three_year_audit_in_universe_count"],
        "full_three_year_audit_in_effective_universe_count": payload["summary"]["full_three_year_audit_in_effective_universe_count"],
        "consistency_status": payload["consistency"]["status"],
        "consistency_issue_count": payload["consistency"]["issue_count"],
        "consistency_reason_codes": payload["consistency"]["reason_codes"],
        "audit_record_without_company_master_ids": payload["consistency"]["audit_record_without_company_master_ids"],
        "company_coverage_states": [
            {
                "company_id": company["company_id"],
                "company_record_source": company["company_record_source"],
                "audit_coverage_state": company["audit_coverage_state"],
                "operational_coverage_state": company["operational_coverage_state"],
                "evidence_coverage_state": company["evidence_coverage_state"],
                "freshness_state": company["freshness_state"],
                "recommendation_priority": company["recommendation_priority"],
                "recommendation_reason_codes": company["recommendation_reason_codes"],
            }
            for company in payload["companies"]
        ],
        "company_priority_counts": payload["summary"]["company_priority_counts"],
        "work_item_priority_counts": payload["summary"]["work_item_priority_counts"],
        "priority_counts": payload["summary"]["work_item_priority_counts"],
    }


def markdown_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Company Data Coverage & Freshness",
        "",
        f"- As of date: `{payload['as_of_date']}`",
        f"- Canonical companies: {summary['canonical_company_count']}",
        f"- Supplemental public companies: {summary['supplemental_public_company_count']}",
        f"- Effective public companies: {summary['effective_public_company_count']}",
        f"- Audit records: {summary['audit_record_count']}",
        f"- Effective public universe audit-backed: {summary['audit_backed_in_effective_universe_count']} / {summary['effective_public_company_count']}",
        f"- Full three-year audit records: {summary['full_three_year_audit_record_count']}",
        f"- Full three-year audit records in effective public universe: {summary['full_three_year_audit_in_effective_universe_count']}",
        f"- Non-audit companies in public universe: {summary['non_audit_company_count']}",
        f"- Consistency status: {payload['consistency']['status']} ({payload['consistency']['issue_count']} issues)",
        f"- Company priority counts P0/P1/P2/P3: {summary['company_priority_counts']['P0']} / {summary['company_priority_counts']['P1']} / {summary['company_priority_counts']['P2']} / {summary['company_priority_counts']['P3']}",
        f"- Work-item priority counts P0/P1/P2/P3: {summary['work_item_priority_counts']['P0']} / {summary['work_item_priority_counts']['P1']} / {summary['work_item_priority_counts']['P2']} / {summary['work_item_priority_counts']['P3']}",
        "",
        "This artifact is a data-work priority control plane. It is not a company score, credit rating, investment recommendation, or ranking.",
        "",
        "## Priority Queue",
        "",
    ]
    if not payload["priority_queue"]:
        lines.append("No data-gap work items were generated.")
    else:
        lines.append("| Priority | Type | Company | Domain | Next action | Reason codes |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for item in payload["priority_queue"]:
            lines.append(
                f"| {item['priority']} | {item['item_type']} | {item['company_id']} | {item['recommended_next_domain']} | {item['recommended_next_action']} | {', '.join(item['reason_codes'])} |"
            )
    lines.extend(["", "## Company Coverage", ""])
    lines.append("| Company | Audit | Operations | Evidence | Freshness | Next action |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for company in payload["companies"]:
        lines.append(
            f"| {company['company_id']} | {company['audit_coverage_state']} | {company['operational_coverage_state']} | {company['evidence_coverage_state']} | {company['freshness_state']} | {company['recommended_next_action']} |"
        )
    if summary["audit_company_ids_not_in_universe"]:
        lines.extend(
            [
                "",
                "## Audit IDs Not In Public Universe",
                "",
                "These audit-backed records are present in the financial insight view model but are not listed in `companies.json`. The control plane reports this as a P0 data-integrity work item only. It is not a company risk rating and it does not modify either source.",
                "",
            ]
        )
        for company_id in summary["audit_company_ids_not_in_universe"]:
            lines.append(f"- `{company_id}`")
    lines.append("")
    return "\n".join(lines)


def write_outputs(payload: dict[str, Any], artifact_dir: Path, snapshot_path: Path) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "company-data-coverage.json").write_text(stable_json(payload), encoding="utf-8")
    (artifact_dir / "company-data-coverage.md").write_text(markdown_report(payload), encoding="utf-8")
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(stable_json(build_snapshot(payload)), encoding="utf-8")


def check_outputs(payload: dict[str, Any], artifact_dir: Path, snapshot_path: Path) -> list[str]:
    expected = {
        artifact_dir / "company-data-coverage.json": stable_json(payload),
        artifact_dir / "company-data-coverage.md": markdown_report(payload),
        snapshot_path: stable_json(build_snapshot(payload)),
    }
    issues = []
    for path, rendered in expected.items():
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        if existing != rendered:
            issues.append(str(path))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Build company data coverage and freshness artifacts.")
    parser.add_argument("--as-of-date", type=str, default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument("--companies", type=Path, default=DEFAULT_COMPANIES)
    parser.add_argument("--report-insights", type=Path, default=DEFAULT_REPORT_INSIGHTS)
    parser.add_argument("--supplements", type=Path, default=DEFAULT_SUPPLEMENTS)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_AUDIT_SOURCE_ROOT)
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--company-id")
    parser.add_argument("--priority", choices=["P0", "P1", "P2", "P3"])
    parser.add_argument("--check", action="store_true", help="Fail if stored outputs differ from generated outputs.")
    args = parser.parse_args()

    as_of_date = parse_date(args.as_of_date)
    if as_of_date is None:
        raise SystemExit(f"Invalid --as-of-date: {args.as_of_date}")
    payload = build_payload(
        as_of_date=as_of_date,
        companies_path=args.companies,
        report_insights_path=args.report_insights,
        supplements_path=args.supplements,
        source_root=args.source_root,
        company_id=args.company_id,
        priority=args.priority,
    )
    if args.check:
        issues = check_outputs(payload, args.artifact_dir, args.snapshot)
        if issues:
            raise SystemExit("company data coverage outputs are not up to date:\n" + "\n".join(issues))
        print("company data coverage outputs are up to date")
        return 0
    write_outputs(payload, args.artifact_dir, args.snapshot)
    print(
        "wrote company data coverage for "
        f"{payload['summary']['total_company_count']} companies "
        f"({payload['summary']['audit_backed_company_count']} audit-backed)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
