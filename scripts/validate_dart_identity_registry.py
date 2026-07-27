"""Validate Company Change Monitor DART identity registry consistency."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
IDENTITIES_PATH = ROOT / "config" / "company_change_monitoring" / "company_identities.json"
REGISTRY_PATH = ROOT / "config" / "company_change_monitoring" / "dart_company_identity_registry.json"
POLICY_PATH = ROOT / "config" / "company_change_monitoring" / "source_coverage_policy.json"
REPORT_PATH = ROOT / "artifacts" / "company-source-coverage" / "dart-identity-registry-validation.json"

CORP_CODE_RE = re.compile(r"^\d{8}$")
VALID_MAPPING_STATUSES = {"verified", "not_verified", "ambiguous"}
VALID_IDENTITY_RISKS = {"low", "moderate", "high", "unknown"}
SECRET_FIELD_NAMES = {"businessRegistrationNumber", "corporateRegistrationNumber", "jurirNo", "bizrNo"}
VERIFIED_EVIDENCE_TYPES = {"official_opendart_registry_and_company_profile", "existing_verified_identity_policy"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_registry(
    *,
    identities: dict[str, Any],
    registry: dict[str, Any],
    policy: dict[str, Any],
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or utc_now()
    identity_rows = identities.get("companies", [])
    registry_rows = registry.get("companies", [])
    identity_by_id = {row.get("companyId"): row for row in identity_rows}
    registry_by_id = {row.get("companyId"): row for row in registry_rows}
    issues: list[dict[str, Any]] = []

    def issue(code: str, company_id: str = "", message: str = "") -> None:
        issues.append({"code": code, "companyId": company_id, "message": message})

    if len(identity_by_id) != len(identity_rows):
        issue("duplicate_company_identity_id")
    if len(registry_by_id) != len(registry_rows):
        issue("duplicate_registry_company_id")
    missing_registry = sorted(set(identity_by_id) - set(registry_by_id))
    extra_registry = sorted(set(registry_by_id) - set(identity_by_id))
    for company_id in missing_registry:
        issue("missing_registry_company", company_id)
    for company_id in extra_registry:
        issue("unexpected_registry_company", company_id)

    corp_codes: list[str] = []
    same_name_contamination_count = 0
    verified_ids: list[str] = []
    for company_id in sorted(set(identity_by_id) & set(registry_by_id)):
        identity = identity_by_id[company_id]
        row = registry_by_id[company_id]
        status = row.get("mappingStatus")
        corp_code = row.get("corpCode")
        identity_code = identity.get("corpCode")
        if status not in VALID_MAPPING_STATUSES:
            issue("invalid_mapping_status", company_id, str(status))
        if row.get("identityRisk", "unknown") not in VALID_IDENTITY_RISKS:
            issue("invalid_identity_risk", company_id, str(row.get("identityRisk")))
        if identity_code != corp_code:
            issue("corp_code_mismatch", company_id)
        if status == "verified":
            verified_ids.append(company_id)
            if not corp_code:
                issue("verified_missing_corp_code", company_id)
            elif not CORP_CODE_RE.match(str(corp_code)):
                issue("invalid_corp_code_format", company_id)
            else:
                corp_codes.append(str(corp_code))
            if row.get("evidenceType") not in VERIFIED_EVIDENCE_TYPES:
                issue("verified_missing_official_evidence_type", company_id)
        else:
            if corp_code:
                issue("unverified_has_corp_code", company_id)
        if company_id == "daeseung-engineering" and status == "verified":
            notes = " ".join([str(row.get("notes") or ""), *(str(item) for item in row.get("exclusionNotes") or [])])
            if not notes:
                same_name_contamination_count += 1
                issue("same_name_guard_missing", company_id)
        for field_name in SECRET_FIELD_NAMES:
            value = row.get(field_name)
            if value:
                issue("sensitive_identifier_present", company_id, field_name)
    duplicates = len(corp_codes) - len(set(corp_codes))
    if duplicates:
        issue("duplicate_corp_code")

    total = len(identity_rows)
    coverage_ratio = len(verified_ids) / total if total else 0
    minimum = float(policy.get("minimumDartMappingCoverage", 0.8))
    if coverage_ratio < minimum:
        issue("dart_mapping_coverage_below_policy", message=f"{coverage_ratio:.4f} < {minimum:.4f}")

    return {
        "schemaVersion": "company-dart-identity-registry-validation-v1",
        "generatedAt": generated_at,
        "valid": not issues,
        "expectedCompanyCount": total,
        "registryCompanyCount": len(registry_rows),
        "verifiedCompanyCount": len(verified_ids),
        "coverageRatio": round(coverage_ratio, 4),
        "targetCoverageRatio": minimum,
        "verifiedCompanyIds": sorted(verified_ids),
        "unresolvedCompanyIds": sorted(company_id for company_id, row in registry_by_id.items() if row.get("mappingStatus") != "verified"),
        "duplicateCorpCodeCount": duplicates,
        "corpCodeMismatchCount": sum(1 for item in issues if item["code"] == "corp_code_mismatch"),
        "sameNameContaminationCount": same_name_contamination_count,
        "secretExposureDetected": any(item["code"] == "sensitive_identifier_present" for item in issues),
        "registryPolicyConsistent": bool(registry.get("policy", {}).get("corpCodeInferenceAllowed") is False),
        "issues": issues,
    }


def main() -> int:
    report = validate_registry(
        identities=read_json(IDENTITIES_PATH),
        registry=read_json(REGISTRY_PATH),
        policy=read_json(POLICY_PATH),
    )
    write_json(REPORT_PATH, report)
    print(json.dumps({k: report[k] for k in ["valid", "verifiedCompanyCount", "coverageRatio", "duplicateCorpCodeCount", "corpCodeMismatchCount", "sameNameContaminationCount", "secretExposureDetected"]}, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
