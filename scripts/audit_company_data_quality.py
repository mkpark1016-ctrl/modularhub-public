#!/usr/bin/env python3
"""Audit the public 11-company data universe and write research reports."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "research" / "company-enrichment"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.company_data_quality import build_quality_audit, load_public_company_universe, source_registry  # noqa: E402


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def markdown_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    lines = ["|" + "|".join(label for _, label in columns) + "|", "|" + "|".join("---" for _ in columns) + "|"]
    for row in rows:
        values = []
        for key, _ in columns:
            value = row.get(key)
            if isinstance(value, float):
                value = f"{value:.1f}"
            values.append(str(value if value not in (None, "") else "확인 중").replace("\n", " "))
        lines.append("|" + "|".join(values) + "|")
    return "\n".join(lines)


def quality_report(audit: dict[str, Any]) -> str:
    rows = audit["companies"]
    columns = [
        ("companyId", "기업 ID"),
        ("displayName", "기업명"),
        ("score", "데이터 검증 수준"),
        ("scoreBand", "구간"),
        ("populatedFields", "입력 필드"),
        ("sourcedFields", "출처 연결 레코드"),
        ("tier1SourcedFields", "Tier 1 출처"),
        ("unresolvedFields", "조사 공백"),
    ]
    lines = [
        "# 11개 모듈러 기업 데이터 품질 감사",
        "",
        f"- 생성 시각: `{audit['generatedAt']}`",
        f"- 기업 수: `{audit['companyCount']}`",
        f"- Source 수: `{audit['sourceCount']}`",
        f"- 검증 상태: `{audit['status']}`",
        "",
        "이 점수는 기업 경쟁력 평가가 아니라 공개 데이터의 완성도와 검증 수준을 추적하기 위한 내부 운영 지표입니다.",
        "",
        markdown_table(rows, columns),
        "",
        "## 기업별 상위 조사 공백",
        "",
    ]
    for row in rows:
        lines.append(f"### {row['displayName']} (`{row['companyId']}`)")
        gaps = row.get("topResearchGaps") or ["추가 조사 공백 없음"]
        lines.extend(f"- {gap}" for gap in gaps)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def research_gaps_report(audit: dict[str, Any]) -> str:
    lines = [
        "# 기업정보 보강 후속 조사 항목",
        "",
        "현재 공개 데이터는 기존 검증 기준선을 유지한다. 다음 보강은 기업별 공식 홈페이지, DART 감사보고서, 특허 원문, 발주기관 계약자료를 우선 사용해 순차 진행한다.",
        "",
        "공식 근거가 없는 값은 0이나 확정값으로 추정하지 않고 `확인 중` 또는 조사 공백으로 유지한다.",
        "",
    ]
    daeseung = next((row for row in audit["companies"] if row["companyId"] == "daeseung-engineering"), None)
    if daeseung:
        lines.extend(
            [
                "## 대승엔지니어링",
                "",
                "- 공식 홈페이지와 공식 연락처 확인",
                "- 군산 생산시설의 법적 주소, 현재 운영 상태, 소유·임차 관계 확인",
                "- 군산 생산시설의 공식 생산능력 확인",
                "- 2025년 매출액을 감사보고서 또는 기업 공식 재무자료와 교차검증",
                "- 김천 본사, 서울 사무실, 군산 사업장의 역할 구분",
                "",
            ]
        )
    lines.extend(
        [
            "## 기존 10개 기업 공통 보강",
            "",
            "- 생산능력 수치가 제3자 자료에만 의존하는 항목의 1차 출처 확보",
            "- 계획·증설 시설과 실제 운영 시설의 상태 재확인",
            "- 2025년 재무의 연결·별도 및 모듈러 부문 구분 재확인",
            "- 프로젝트의 계약·수주·착공·준공 상태 최신화",
            "- 특허 법적 상태 및 권리자 최신화",
            "",
            "## 기업별 자동 탐지 Research Gap",
            "",
        ]
    )
    for row in audit["companies"]:
        lines.append(f"## {row['displayName']} (`{row['companyId']}`)")
        for gap in row.get("topResearchGaps") or []:
            lines.append(f"- {gap}")
        if not row.get("topResearchGaps"):
            lines.append("- 현재 구조화 데이터 기준 추가 공백 없음")
        lines.append("")
    return "\n".join(lines)


def conflict_report(audit: dict[str, Any]) -> str:
    conflicting = [row for row in audit["companies"] if row.get("conflictingFields", 0) > 0]
    lines = ["# 기업 데이터 충돌 보고서", ""]
    if not conflicting:
        lines.append("현재 구조화 데이터 기준으로 자동 탐지된 충돌 필드는 없습니다. 공식 원천과 2차 자료가 충돌하는 경우 향후 `conflicting_values`에 기록합니다.")
    else:
        for row in conflicting:
            lines.append(f"- `{row['companyId']}`: {row['conflictingFields']}건")
    lines.append("")
    lines.append("대승엔지니어링은 동명 김해 수처리 업체, 자동차 부품 대승 및 대승그룹 정보를 명시적으로 배제합니다.")
    return "\n".join(lines) + "\n"


def change_report(audit: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": "company-data-change-report-v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "changes": [
            {
                "changeType": "newly_verified",
                "target": "company_data_quality_audit",
                "before": None,
                "after": "11-company quality audit, source registry, research gap, and conflict reports generated",
                "reason": "Phase 4D requires field-level verification structure without inventing unconfirmed facts.",
                "sourceIds": [],
            }
        ],
        "protectedDataChanged": False,
    }


def change_report_md(report: dict[str, Any]) -> str:
    lines = ["# 기업 데이터 변경 이력", "", f"- 생성 시각: `{report['generatedAt']}`", ""]
    for change in report["changes"]:
        lines.append(f"## {change['changeType']}: {change['target']}")
        lines.append(f"- before: {change['before']}")
        lines.append(f"- after: {change['after']}")
        lines.append(f"- reason: {change['reason']}")
        lines.append("")
    return "\n".join(lines)


def write_outputs(output_dir: Path) -> dict[str, str]:
    audit = build_quality_audit(ROOT)
    companies = load_public_company_universe(ROOT)
    registry = source_registry(companies)
    changes = change_report(audit)

    paths = {
        "qualityJson": output_dir / "company-quality-audit.json",
        "qualityMd": output_dir / "company-quality-audit.md",
        "sources": output_dir / "sources.json",
        "gaps": output_dir / "research-gaps.md",
        "conflicts": output_dir / "conflict-report.md",
        "changeJson": output_dir / "change-report.json",
        "changeMd": output_dir / "change-report.md",
    }
    write_json(paths["qualityJson"], audit)
    write_text(paths["qualityMd"], quality_report(audit))
    write_json(paths["sources"], registry)
    write_text(paths["gaps"], research_gaps_report(audit))
    write_text(paths["conflicts"], conflict_report(audit))
    write_json(paths["changeJson"], changes)
    write_text(paths["changeMd"], change_report_md(changes))
    return {key: str(value.relative_to(ROOT)) for key, value in paths.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    paths = write_outputs(args.output_dir)
    audit = json.loads((args.output_dir / "company-quality-audit.json").read_text(encoding="utf-8"))
    print(f"COMPANY DATA QUALITY {audit['status'].upper()}: companies={audit['companyCount']} sources={audit['sourceCount']}")
    for key, path in paths.items():
        print(f"{key}: {path}")
    return 0 if audit["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
