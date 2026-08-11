"""Normalize OpenDART consolidated financial rows into the audit-financial contract.

This module is deliberately pure and network-free. Live OpenDART collection is
performed by a script and passed in here as structured payloads plus verified
filing metadata. The output can then be validated by the existing
``company_audit_financials_v1`` validator before any public promotion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


TARGET_YEARS = (2023, 2024, 2025)
GENERAL_CONTRACTORS: dict[str, dict[str, str]] = {
    "gs-ec": {
        "company_name": "GS건설",
        "reporting_entity": "지에스건설 주식회사 및 연결대상 종속기업",
        "corp_code": "00120030",
    },
    "samsung-ct-construction": {
        "company_name": "삼성물산 건설부문",
        "reporting_entity": "삼성물산 주식회사 및 연결대상 종속기업",
        "corp_code": "00149655",
    },
    "hyundai-engineering": {
        "company_name": "현대엔지니어링",
        "reporting_entity": "현대엔지니어링 주식회사 및 연결대상 종속기업",
        "corp_code": "00349927",
    },
    "dl-enc": {
        "company_name": "DL이앤씨",
        "reporting_entity": "DL이앤씨 주식회사 및 연결대상 종속기업",
        "corp_code": "01524093",
    },
}


@dataclass(frozen=True)
class MetricSpec:
    section: str
    field: str
    source_section: str
    statement_divisions: tuple[str, ...]
    account_ids: tuple[str, ...] = ()
    account_names: tuple[str, ...] = ()


def _norm(value: Any) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", str(value or "").lower())


def _amount(value: Any) -> int | None:
    if value in (None, ""):
        return None
    text = str(value).replace(",", "").strip()
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    try:
        parsed = int(float(text))
    except (TypeError, ValueError):
        return None
    return -parsed if negative else parsed


METRIC_SPECS: tuple[MetricSpec, ...] = (
    MetricSpec("income_statement", "revenue", "statement.income_statement", ("IS", "CIS"),
               ("ifrs-full_Revenue", "ifrs_Revenue"), ("매출액", "매출", "영업수익")),
    MetricSpec("income_statement", "gross_profit", "statement.income_statement", ("IS", "CIS"),
               ("ifrs-full_GrossProfit", "ifrs_GrossProfit"), ("매출총이익", "매출총손실")),
    MetricSpec("income_statement", "operating_profit", "statement.income_statement", ("IS", "CIS"),
               ("dart_OperatingIncomeLoss",), ("영업이익", "영업손실", "영업이익(손실)")),
    MetricSpec("income_statement", "net_income", "statement.income_statement", ("IS", "CIS"),
               ("ifrs-full_ProfitLoss", "ifrs_ProfitLoss"), ("당기순이익", "당기순손실", "당기순이익(손실)")),
    MetricSpec("balance_sheet", "total_assets", "statement.balance_sheet", ("BS",),
               ("ifrs-full_Assets", "ifrs_Assets"), ("자산총계",)),
    MetricSpec("balance_sheet", "total_liabilities", "statement.balance_sheet", ("BS",),
               ("ifrs-full_Liabilities", "ifrs_Liabilities"), ("부채총계",)),
    MetricSpec("balance_sheet", "total_equity", "statement.balance_sheet", ("BS",),
               ("ifrs-full_Equity", "ifrs_Equity"), ("자본총계",)),
    MetricSpec("balance_sheet", "current_assets", "statement.balance_sheet", ("BS",),
               ("ifrs-full_CurrentAssets", "ifrs_CurrentAssets"), ("유동자산",)),
    MetricSpec("balance_sheet", "current_liabilities", "statement.balance_sheet", ("BS",),
               ("ifrs-full_CurrentLiabilities", "ifrs_CurrentLiabilities"), ("유동부채",)),
    MetricSpec("cash_flow", "operating_cash_flow", "statement.cash_flow", ("CF",),
               ("ifrs-full_CashFlowsFromUsedInOperatingActivities", "ifrs_CashFlowsFromUsedInOperatingActivities"),
               ("영업활동현금흐름", "영업활동으로인한현금흐름")),
    MetricSpec("cash_flow", "investing_cash_flow", "statement.cash_flow", ("CF",),
               ("ifrs-full_CashFlowsFromUsedInInvestingActivities", "ifrs_CashFlowsFromUsedInInvestingActivities"),
               ("투자활동현금흐름", "투자활동으로인한현금흐름")),
    MetricSpec("cash_flow", "financing_cash_flow", "statement.cash_flow", ("CF",),
               ("ifrs-full_CashFlowsFromUsedInFinancingActivities", "ifrs_CashFlowsFromUsedInFinancingActivities"),
               ("재무활동현금흐름", "재무활동으로인한현금흐름")),
    MetricSpec("cash_flow", "ending_cash", "statement.cash_flow", ("CF", "BS"),
               ("ifrs-full_CashAndCashEquivalents", "ifrs_CashAndCashEquivalents"), ("현금및현금성자산",)),
    MetricSpec("working_capital", "inventory", "note.working_capital", ("BS",),
               ("ifrs-full_Inventories", "ifrs_Inventories"), ("재고자산",)),
    MetricSpec("borrowings", "short_term_borrowings", "note.borrowings", ("BS",),
               ("ifrs-full_ShorttermBorrowings", "ifrs_ShorttermBorrowings"), ("단기차입금",)),
    MetricSpec("borrowings", "current_portion_long_term_borrowings", "note.borrowings", ("BS",),
               ("ifrs-full_CurrentPortionOfLongtermBorrowings", "ifrs_CurrentPortionOfLongtermBorrowings"),
               ("유동성장기차입금",)),
    MetricSpec("borrowings", "long_term_borrowings", "note.borrowings", ("BS",),
               ("ifrs-full_LongtermBorrowings", "ifrs_LongtermBorrowings"), ("장기차입금",)),
)


SECTION_FIELDS: dict[str, tuple[str, ...]] = {
    "income_statement": ("revenue", "gross_profit", "operating_profit", "net_income"),
    "balance_sheet": ("total_assets", "total_liabilities", "total_equity", "current_assets", "current_liabilities"),
    "cash_flow": ("operating_cash_flow", "investing_cash_flow", "financing_cash_flow", "ending_cash"),
    "revenue_breakdown": ("goods_revenue", "product_revenue", "construction_revenue", "rental_revenue", "other_revenue"),
    "working_capital": ("trade_receivables_gross", "construction_receivables_gross", "inventory", "work_in_progress"),
    "borrowings": ("short_term_borrowings", "current_portion_long_term_borrowings", "long_term_borrowings"),
    "investment_signals": ("construction_in_progress", "industrial_property_rights", "research_and_development_expense"),
}

SECTION_SOURCE_CODES = {
    "income_statement": "statement.income_statement",
    "balance_sheet": "statement.balance_sheet",
    "cash_flow": "statement.cash_flow",
    "revenue_breakdown": "note.revenue_breakdown",
    "working_capital": "note.working_capital",
    "borrowings": "note.borrowings",
    "investment_signals": "note.investment_signals",
}

OPINION_MAP = {
    "unmodified": ("unqualified", "적정의견"),
    "unqualified": ("unqualified", "적정의견"),
    "qualified": ("qualified", "한정의견"),
    "adverse": ("adverse", "부적정의견"),
    "disclaimer": ("disclaimer", "의견거절"),
    "unknown": ("unknown", "확인 필요"),
}


def _row_matches(row: dict[str, Any], spec: MetricSpec) -> tuple[int, int] | None:
    sj_div = str(row.get("sj_div") or "").upper()
    if spec.statement_divisions and sj_div not in spec.statement_divisions:
        return None
    account_id = _norm(row.get("account_id"))
    account_name = _norm(row.get("account_nm"))
    normalized_ids = {_norm(value) for value in spec.account_ids}
    normalized_names = {_norm(value) for value in spec.account_names}
    if account_id and account_id in normalized_ids:
        return (0, len(account_name))
    if account_name and account_name in normalized_names:
        return (1, len(account_name))
    return None


def select_metric(rows: list[dict[str, Any]], spec: MetricSpec) -> dict[str, Any] | None:
    candidates: list[tuple[tuple[int, int], int, dict[str, Any]]] = []
    for index, row in enumerate(rows):
        rank = _row_matches(row, spec)
        amount = _amount(row.get("thstrm_amount"))
        if rank is None or amount is None:
            continue
        candidates.append((rank, index, row))
    if not candidates:
        return None
    _, _, row = min(candidates, key=lambda item: (item[0], item[1]))
    return row


def source_location(source_ref: str, section: str, *, verified: bool) -> dict[str, Any]:
    return {
        "source_ref": source_ref,
        "section": section,
        "verification_status": "verified" if verified else "pending_manual_page_check",
    }


def reported_amount(value: int, source_ref: str, section: str) -> dict[str, Any]:
    return {
        "reported": int(value),
        "disclosure_status": "reported",
        "source_refs": [source_ref],
        "source_locations": [source_location(source_ref, section, verified=True)],
    }


def pending_amount(source_ref: str, section: str, note: str) -> dict[str, Any]:
    return {
        "reported": None,
        "disclosure_status": "verification_pending",
        "source_refs": [source_ref],
        "source_locations": [source_location(source_ref, section, verified=False)],
        "notes": note,
    }


def map_structured_year(rows: list[dict[str, Any]], source_ref: str) -> tuple[dict[str, Any], dict[str, Any]]:
    mapped: dict[tuple[str, str], dict[str, Any]] = {}
    diagnostics: dict[str, Any] = {"matched": {}, "pending": []}
    for spec in METRIC_SPECS:
        row = select_metric(rows, spec)
        if row is None:
            continue
        value = _amount(row.get("thstrm_amount"))
        if value is None:
            continue
        mapped[(spec.section, spec.field)] = reported_amount(value, source_ref, spec.source_section)
        diagnostics["matched"][f"{spec.section}.{spec.field}"] = {
            "account_id": row.get("account_id"),
            "account_name": row.get("account_nm"),
            "statement": row.get("sj_div"),
        }

    year_record: dict[str, Any] = {"source_refs": [source_ref]}
    for section, fields in SECTION_FIELDS.items():
        year_record[section] = {}
        section_code = SECTION_SOURCE_CODES[section]
        for field in fields:
            record = mapped.get((section, field))
            if record is not None:
                year_record[section][field] = record
                continue
            note = (
                "OpenDART 전체재무제표 API에서 보수적으로 확정하지 못한 계정입니다. "
                "공시 원문 또는 XBRL 주석을 추가 확인해야 합니다."
            )
            year_record[section][field] = pending_amount(source_ref, section_code, note)
            diagnostics["pending"].append(f"{section}.{field}")
    return year_record, diagnostics


def _date_text(value: Any) -> str:
    text = re.sub(r"[^0-9]", "", str(value or ""))
    if len(text) != 8:
        raise ValueError(f"invalid filing date: {value!r}")
    return f"{text[:4]}-{text[4:6]}-{text[6:8]}"


def _source_ref(company_id: str, year: int, receipt_number: str) -> str:
    safe_receipt = re.sub(r"[^0-9A-Za-z_-]", "", receipt_number)
    return f"{company_id}_opendart_{year}_{safe_receipt}"


def build_audit_financial_candidate(
    *,
    company_id: str,
    structured_payloads: dict[int, dict[str, Any]],
    filing_metadata: dict[int, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build one schema-shaped consolidated candidate and diagnostics.

    ``filing_metadata`` must come from a verified DART filing identity and
    include receipt number, filing date and auditor. Missing auditor metadata is
    treated as a blocker rather than silently inventing a firm name.
    """

    if company_id not in GENERAL_CONTRACTORS:
        raise ValueError(f"unsupported general contractor: {company_id}")
    spec = GENERAL_CONTRACTORS[company_id]
    diagnostics: dict[str, Any] = {
        "company_id": company_id,
        "corp_code": spec["corp_code"],
        "financial_scope": "consolidated",
        "years": {},
        "blockers": [],
    }
    source_documents: dict[str, Any] = {}
    source_priority: dict[str, Any] = {}
    audit_opinions: list[dict[str, Any]] = []
    financial_years: dict[str, Any] = {}

    for year in TARGET_YEARS:
        payload = structured_payloads.get(year) or {}
        rows = list(payload.get("list") or [])
        meta = filing_metadata.get(year) or {}
        receipt_number = str(meta.get("receipt_number") or "").strip()
        auditor = str(meta.get("auditor") or "").strip()
        if not receipt_number:
            diagnostics["blockers"].append(f"{year}:missing_receipt_number")
            continue
        if not auditor:
            diagnostics["blockers"].append(f"{year}:missing_auditor")
            continue
        if not rows:
            diagnostics["blockers"].append(f"{year}:missing_cfs_rows")
            continue

        source_ref = _source_ref(company_id, year, receipt_number)
        opinion, opinion_label = OPINION_MAP.get(str(meta.get("audit_opinion") or "unknown"), OPINION_MAP["unknown"])
        report_date = _date_text(meta.get("filed_at"))
        source_documents[source_ref] = {
            "filename": f"OpenDART receipt {receipt_number}",
            "report_date": report_date,
            "covered_years": [year],
            "auditor": auditor,
            "auditor_report_date": None,
            "auditor_report_date_verification_status": "pending_manual_page_check",
            "auditor_report_date_note": "OpenDART 원문에서 독립감사인 보고서 작성일은 별도 수동 확인이 필요합니다.",
            "audit_opinion": opinion,
            "source_role": "primary",
            "usage": "OpenDART 연결 전체재무제표 API와 해당 공시 원문을 결합한 자동 온보딩 후보",
        }
        audit_opinions.append(
            {
                "source_ref": source_ref,
                "opinion": opinion,
                "opinion_label_ko": opinion_label,
                "covered_years": [year],
                "auditor": auditor,
                "auditor_report_date": None,
                "auditor_report_date_verification_status": "pending_manual_page_check",
                "auditor_report_date_note": "OpenDART 원문에서 독립감사인 보고서 작성일은 별도 수동 확인이 필요합니다.",
            }
        )
        source_priority[str(year)] = {
            "primary_source_ref": source_ref,
            "basis": "current_year_financial_statements",
        }
        year_record, year_diagnostics = map_structured_year(rows, source_ref)
        financial_years[str(year)] = year_record
        diagnostics["years"][str(year)] = year_diagnostics

    if diagnostics["blockers"]:
        raise ValueError("candidate blockers: " + ", ".join(diagnostics["blockers"]))

    candidate = {
        "schema_version": "company_audit_financials_v1",
        "company_id": company_id,
        "company_name": spec["company_name"],
        "reporting_entity": spec["reporting_entity"],
        "accounting_standard": {
            "code": "k_ifrs",
            "label_ko": "한국채택국제회계기준",
            "label_en": "K-IFRS",
        },
        "currency": "KRW",
        "unit": "won",
        "audit_opinions": audit_opinions,
        "source_documents": source_documents,
        "source_priority": source_priority,
        "financial_years": financial_years,
        "entity_attribution": {
            "reporting_entity": spec["reporting_entity"],
            "financial_scope": "consolidated",
            "related_entity_attribution_required": True,
            "modular_segment_revenue_disclosed": False,
            "attribution_warning": (
                "연결재무제표는 회사와 연결대상 종속기업의 실적을 포함합니다. "
                "회사 전체 매출 또는 건설 매출을 모듈러 사업 매출로 자동 해석하지 않습니다."
            ),
            "special_events": [],
        },
        "disclosure_limitations": [
            "연결재무제표 기준 회사 전체 실적이며 모듈러 사업부문 별도 실적으로 해석하지 않는다.",
            "OpenDART 전체재무제표 API에서 직접 확정할 수 없는 주석 계정은 verification_pending으로 유지한다.",
            "총차입금·채권·세부 매출구성은 구성 계정이 모두 검증된 경우에만 파생 계산한다.",
        ],
        "validation_metadata": {
            "created_for": "OpenDART general-contractor consolidated audit-financial onboarding",
            "amount_storage": "KRW integer won",
            "derived_metrics_storage": "not stored; derived by build_company_report_insights.py",
            "pdf_handling": "OpenDART API/XML sources only; source PDFs are not committed",
            "public_ui_impact": "none until guarded validation and promotion complete",
            "expected_years": list(TARGET_YEARS),
        },
    }
    return candidate, diagnostics
