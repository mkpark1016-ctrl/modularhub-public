"""Resolve monitored company DART identities from official OpenDART data.

The resolver is intentionally conservative. It reads OpenDART corpCode.xml and
company.json, emits only sanitized evidence, and writes repository config only
when --apply is supplied.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.env_config import load_project_dotenv  # noqa: E402
from src.opendart_client import DEFAULT_CACHE_DIR, OpenDartClient  # noqa: E402


IDENTITIES_PATH = ROOT / "config" / "company_change_monitoring" / "company_identities.json"
REGISTRY_PATH = ROOT / "config" / "company_change_monitoring" / "dart_company_identity_registry.json"
OUTPUT_DIR = ROOT / "artifacts" / "company-source-coverage"

CORP_CODE_RE = re.compile(r"^\d{8}$")
CORPORATE_SUFFIX_RE = re.compile(r"주식회사|\(?주\)?|㈜|co\.?,?ltd\.?|corporation", re.I)
SAFE_OVERVIEW_FIELDS = {"corp_name", "corp_name_eng", "stock_name", "stock_code", "corp_cls", "hm_url", "adres"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_company_name(value: str | None) -> str:
    text = "" if value is None else str(value)
    text = CORPORATE_SUFFIX_RE.sub("", text)
    text = re.sub(r"[\s·ㆍ\-.&/,_]+", "", text.lower())
    return text


def normalize_domain(value: str | None) -> str:
    text = "" if value is None else str(value).strip().lower()
    text = re.sub(r"^https?://", "", text)
    text = text.split("/", 1)[0]
    if text.startswith("www."):
        text = text[4:]
    return text


def safe_overview(overview: dict[str, Any]) -> dict[str, Any]:
    return {key: overview.get(key) for key in sorted(SAFE_OVERVIEW_FIELDS) if overview.get(key)}


def get_opendart_api_key() -> str | None:
    load_project_dotenv()
    return os.getenv("OPENDART_API_KEY") or os.getenv("DART_API_KEY")


def candidate_names(identity: dict[str, Any]) -> tuple[str, set[str]]:
    legal = normalize_company_name(identity.get("legalName"))
    alias_names = {
        normalize_company_name(name)
        for name in [
            *(identity.get("aliases") or []),
            *(identity.get("formerNames") or []),
            identity.get("displayName"),
        ]
        if normalize_company_name(name)
    }
    return legal, alias_names


def find_candidates(identity: dict[str, Any], corp_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    legal, aliases = candidate_names(identity)
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in corp_rows:
        corp_code = str(row.get("corp_code") or "")
        corp_name = str(row.get("corp_name") or "")
        normalized = normalize_company_name(corp_name)
        if not normalized:
            continue
        match_type = None
        if normalized == legal:
            match_type = "legal_name"
        elif normalized in aliases:
            match_type = "alias"
        if match_type and corp_code not in seen:
            seen.add(corp_code)
            candidates.append(
                {
                    "corpCode": corp_code,
                    "corpName": corp_name,
                    "stockCode": str(row.get("stock_code") or "").strip() or None,
                    "modifyDate": str(row.get("modify_date") or "").strip() or None,
                    "matchType": match_type,
                }
            )
    return candidates


def overview_matches_identity(identity: dict[str, Any], overview: dict[str, Any]) -> dict[str, Any]:
    legal = normalize_company_name(identity.get("legalName"))
    corp_name_match = normalize_company_name(overview.get("corp_name")) == legal
    official_domains = {normalize_domain(domain) for domain in identity.get("officialDomains") or [] if normalize_domain(domain)}
    overview_domain = normalize_domain(overview.get("hm_url"))
    homepage_match = bool(overview_domain and overview_domain in official_domains)
    listed_stock = bool(str(overview.get("stock_code") or "").strip())
    return {
        "corpNameMatchesLegalName": corp_name_match,
        "homepageMatchesOfficialDomain": homepage_match,
        "listedStockCodePresent": listed_stock,
        "overviewStatus": overview.get("status"),
        "safeOverview": safe_overview(overview),
    }


def choose_verified_candidate(identity: dict[str, Any], candidates: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str, list[str]]:
    exact = [row for row in candidates if row.get("matchType") == "legal_name"]
    if not candidates:
        return None, "No exact normalized OpenDART legal-name or alias match.", []
    eligible = []
    for row in candidates:
        evidence = row.get("overviewEvidence") or {}
        if evidence.get("overviewStatus") == "000" and evidence.get("corpNameMatchesLegalName"):
            if evidence.get("listedStockCodePresent") or evidence.get("homepageMatchesOfficialDomain"):
                eligible.append(row)
    if len(eligible) == 1:
        selected = eligible[0]
        reason_bits = ["single official OpenDART profile candidate after legal identity matching"]
        evidence = selected.get("overviewEvidence") or {}
        if evidence.get("listedStockCodePresent"):
            reason_bits.append("listed stock code present")
        if evidence.get("homepageMatchesOfficialDomain"):
            reason_bits.append("official homepage domain matched")
        return selected, "; ".join(reason_bits), []
    if len(eligible) > 1:
        homepage_matched = [row for row in eligible if (row.get("overviewEvidence") or {}).get("homepageMatchesOfficialDomain")]
        if len(homepage_matched) == 1:
            selected = homepage_matched[0]
            return selected, "single official homepage domain match among multiple OpenDART profile candidates", []
        return None, "Multiple eligible OpenDART legal-name/profile candidates; manual review required.", [row["corpCode"] for row in eligible]
    if exact:
        return None, "OpenDART legal-name candidates lacked required official profile disambiguation.", [row["corpCode"] for row in exact]
    return None, "Alias candidates did not resolve to an official OpenDART company profile matching the legal name.", [row["corpCode"] for row in candidates]


def resolve_identities(
    *,
    companies: list[str],
    client: OpenDartClient,
    identities: dict[str, Any] | None = None,
    registry: dict[str, Any] | None = None,
    corp_rows: list[dict[str, str]] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or utc_now()
    identities = identities or read_json(IDENTITIES_PATH)
    registry = registry or read_json(REGISTRY_PATH)
    identity_by_id = {row["companyId"]: row for row in identities.get("companies", [])}
    registry_by_id = {row["companyId"]: row for row in registry.get("companies", [])}
    corp_rows = corp_rows if corp_rows is not None else client.list_corp_codes()
    selected_company_ids = companies or list(identity_by_id)
    results: list[dict[str, Any]] = []
    for company_id in selected_company_ids:
        identity = identity_by_id[company_id]
        candidates = find_candidates(identity, corp_rows)
        for candidate in candidates:
            try:
                overview = client.company_overview(candidate["corpCode"])
            except Exception as exc:  # noqa: BLE001 - source errors are isolated per candidate.
                candidate["overviewEvidence"] = {"overviewStatus": "error", "safeErrorCategory": type(exc).__name__}
            else:
                candidate["overviewEvidence"] = overview_matches_identity(identity, overview)
        selected, reason, ambiguous_codes = choose_verified_candidate(identity, candidates)
        current = registry_by_id.get(company_id, {})
        previous_status = current.get("mappingStatus") or "missing"
        if selected:
            result = {
                "companyId": company_id,
                "legalName": identity.get("legalName"),
                "displayName": identity.get("displayName"),
                "previousCorpCode": current.get("corpCode"),
                "resolvedCorpCode": selected["corpCode"],
                "stockCode": selected.get("stockCode") or selected.get("overviewEvidence", {}).get("safeOverview", {}).get("stock_code"),
                "previousMappingStatus": previous_status,
                "mappingStatus": "verified",
                "evidenceType": "official_opendart_registry_and_company_profile",
                "mappingReason": reason,
                "identityRisk": "low" if company_id != "samsung-ct-construction" else "moderate",
                "ambiguousCorpCodes": [],
                "candidateCount": len(candidates),
            }
        else:
            has_exact_candidate = any(row.get("matchType") == "legal_name" for row in candidates)
            result = {
                "companyId": company_id,
                "legalName": identity.get("legalName"),
                "displayName": identity.get("displayName"),
                "previousCorpCode": current.get("corpCode"),
                "resolvedCorpCode": None,
                "stockCode": None,
                "previousMappingStatus": previous_status,
                "mappingStatus": "ambiguous" if ambiguous_codes and has_exact_candidate else "not_verified",
                "evidenceType": "official_opendart_registry_and_company_profile",
                "mappingReason": reason,
                "identityRisk": current.get("identityRisk") or "moderate",
                "ambiguousCorpCodes": ambiguous_codes,
                "candidateCount": len(candidates),
            }
        result["candidates"] = [
            {
                "corpCode": row["corpCode"],
                "corpName": row["corpName"],
                "stockCode": row.get("stockCode"),
                "matchType": row.get("matchType"),
                "overviewEvidence": {
                    key: value
                    for key, value in (row.get("overviewEvidence") or {}).items()
                    if key != "safeOverview"
                },
            }
            for row in candidates
        ]
        results.append(result)
    verified_after = set()
    for row in registry.get("companies", []):
        if row.get("mappingStatus") == "verified":
            verified_after.add(row["companyId"])
    for row in results:
        if row["mappingStatus"] == "verified":
            verified_after.add(row["companyId"])
        elif row["companyId"] in verified_after and row["previousMappingStatus"] != "verified":
            verified_after.remove(row["companyId"])
    total = len(identity_by_id)
    return {
        "schemaVersion": "company-dart-identity-resolution-v1",
        "generatedAt": generated_at,
        "targetCompanies": selected_company_ids,
        "expectedCompanyCount": total,
        "verifiedCompanyCount": len(verified_after),
        "coverageRatio": round(len(verified_after) / total, 4) if total else 0,
        "targetCoverageRatio": 0.8,
        "verifiedCompanyIds": sorted(verified_after),
        "unresolvedCompanyIds": sorted(row["companyId"] for row in results if row["mappingStatus"] == "not_verified"),
        "ambiguousCompanyIds": sorted(row["companyId"] for row in results if row["mappingStatus"] == "ambiguous"),
        "secretExposureDetected": False,
        "results": results,
    }


def apply_resolution(resolution: dict[str, Any], *, identities: dict[str, Any], registry: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    identities = deepcopy(identities)
    registry = deepcopy(registry)
    identity_by_id = {row["companyId"]: row for row in identities.get("companies", [])}
    registry_by_id = {row["companyId"]: row for row in registry.get("companies", [])}
    verified_at = today_utc()
    for result in resolution.get("results", []):
        company_id = result["companyId"]
        identity = identity_by_id[company_id]
        row = registry_by_id[company_id]
        if result["mappingStatus"] == "verified":
            identity["corpCode"] = result["resolvedCorpCode"]
            row.update(
                {
                    "corpCode": result["resolvedCorpCode"],
                    "stockCode": result.get("stockCode"),
                    "mappingStatus": "verified",
                    "mappingReason": result["mappingReason"],
                    "evidenceType": "official_opendart_registry_and_company_profile",
                    "evidenceReference": "OpenDART corpCode.xml and company.json",
                    "lastVerifiedAt": verified_at,
                    "verifiedBy": "opendart_identity_resolver",
                    "identityRisk": result["identityRisk"],
                    "notes": "Verified from official OpenDART registry and sanitized company overview. Corporate/business registration numbers are not stored.",
                }
            )
        else:
            identity["corpCode"] = result.get("previousCorpCode")
            row.update(
                {
                    "corpCode": result.get("previousCorpCode"),
                    "mappingStatus": "not_verified",
                    "mappingReason": result["mappingReason"],
                    "evidenceType": "official_opendart_registry_and_company_profile",
                    "evidenceReference": "OpenDART corpCode.xml and company.json",
                    "lastVerifiedAt": verified_at,
                    "verifiedBy": "opendart_identity_resolver",
                    "identityRisk": result["identityRisk"],
                }
            )
    return identities, registry


def parse_companies(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve monitored company OpenDART identities.")
    parser.add_argument("--companies", default="", help="Comma-separated company IDs. Blank means all monitored companies.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Resolve without changing repository config.")
    mode.add_argument("--apply", action="store_true", help="Apply verified mappings to monitored identity config.")
    parser.add_argument("--refresh", action="store_true", help="Refresh the ignored OpenDART corpCode cache.")
    parser.add_argument("--cache-dir", type=Path, default=None, help="Ignored OpenDART cache directory. Defaults to .cache/opendart.")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR / "dart-identity-resolution.json")
    args = parser.parse_args()

    api_key = get_opendart_api_key()
    if not api_key:
        print("DART_API_KEY configured: false")
        print("OPENDART_API_KEY configured: false")
        return 2
    print("DART_API_KEY configured:", bool(os.getenv("DART_API_KEY")))
    print("OPENDART_API_KEY configured:", bool(os.getenv("OPENDART_API_KEY")))
    identities = read_json(IDENTITIES_PATH)
    registry = read_json(REGISTRY_PATH)
    client = OpenDartClient(api_key=api_key, cache_dir=args.cache_dir or DEFAULT_CACHE_DIR)
    corp_rows = client.list_corp_codes(refresh=args.refresh)
    resolution = resolve_identities(
        companies=parse_companies(args.companies),
        client=client,
        identities=identities,
        registry=registry,
        corp_rows=corp_rows,
    )
    write_json(args.output, resolution)
    print("resolution_output:", args.output.relative_to(ROOT).as_posix())
    print("verifiedCompanyCount:", resolution["verifiedCompanyCount"])
    print("coverageRatio:", resolution["coverageRatio"])
    if args.apply:
        next_identities, next_registry = apply_resolution(resolution, identities=identities, registry=registry)
        write_json(IDENTITIES_PATH, next_identities)
        write_json(REGISTRY_PATH, next_registry)
        print("apply: true")
    else:
        print("apply: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
