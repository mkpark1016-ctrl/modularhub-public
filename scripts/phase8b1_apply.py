#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8-sig")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"missing replacement target: {label}")
    return text.replace(old, new, 1)


def replace_between(text: str, start: str, end: str, replacement: str, label: str) -> str:
    start_index = text.find(start)
    end_index = text.find(end, start_index + len(start))
    if start_index < 0 or end_index < 0:
        raise RuntimeError(f"missing block: {label}")
    return text[:start_index] + replacement + text[end_index:]


def patch_app() -> None:
    path = "frontend/src/App.jsx"
    text = read(path)
    text = replace_once(
        text,
        '''import {\n  COMPETITIVE_ROLE_LABELS,\n  TIER_LABELS,\n  compareCompanies,\n  companyMatchesFilters,\n  companyRoleOptions,\n  getCompanyDataGapCount,\n  getCompanyItems,\n  getCompanySummary,\n  getCanonicalCompanyRoleLabel,\n  isModularSpecialistCompany,\n  optionCounts,\n  statusOptions,\n} from "./companyInsights";''',
        '''import {\n  compareCompanies,\n  companyMatchesFilters,\n  companyRoleOptions,\n  getCompanyItems,\n  getCompanySummary,\n} from "./companyInsights";''',
        "companyInsights import",
    )
    text = replace_once(
        text,
        '''import {\n  COMPANY_COMPARISON_SORT_OPTIONS,\n  MAX_COMPARISON_COMPANIES,''',
        '''import {\n  MAX_COMPARISON_COMPANIES,''',
        "company comparison sort import",
    )
    text = replace_once(
        text,
        '''const COMPANY_SORT_OPTIONS = [\n  ...COMPANY_COMPARISON_SORT_OPTIONS,\n];''',
        '''const COMPANY_LIST_SORT_OPTIONS = [\n  { value: "name", label: "기업명순" },\n  { value: "recent_activity", label: "최근 활동순" },\n  { value: "revenue", label: "최근 매출 높은 순" },\n  { value: "verified_projects", label: "검증 프로젝트 많은 순" },\n];''',
        "company list sort options",
    )

    discovery = '''function CompanyTypeSegmentedControl({ value, options, onChange }) {\n  return (\n    <div className="company-type-segmented" role="radiogroup" aria-label="기업 유형">\n      {options.map((option) => (\n        <button\n          key={option.value}\n          type="button"\n          role="radio"\n          aria-checked={value === option.value}\n          className={value === option.value ? "active" : ""}\n          onClick={() => onChange(option.value)}\n        >\n          <span>{option.label}</span>\n          <strong>{option.count.toLocaleString("ko-KR")}</strong>\n        </button>\n      ))}\n    </div>\n  );\n}\n\nfunction CompanyDiscoveryToolbar({ values, setParam, roleOptions, filteredCount, onReset }) {\n  const canReset = Boolean(values.q) || values.role !== "all" || values.sort !== "name";\n  return (\n    <section className="company-discovery-toolbar" aria-label="기업 탐색 조건">\n      <div className="company-discovery-primary">\n        <label className="company-toolbar-label">\n          <span>기업 유형</span>\n          <CompanyTypeSegmentedControl value={values.role} options={roleOptions} onChange={(nextRole) => setParam("role", nextRole)} />\n        </label>\n        <label className="company-toolbar-search">\n          <span>검색</span>\n          <SearchBar value={values.q} onChange={(value) => setParam("q", value)} placeholder="기업명, 프로젝트, 기술 검색" />\n        </label>\n        <label className="company-toolbar-sort">\n          <span>정렬</span>\n          <select value={values.sort} onChange={(event) => setParam("sort", event.target.value)}>\n            {COMPANY_LIST_SORT_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}\n          </select>\n        </label>\n      </div>\n      <div className="company-discovery-meta">\n        <p>검색 결과 {filteredCount.toLocaleString("ko-KR")}개사</p>\n        {canReset && <button type="button" className="text-button" onClick={onReset}>초기화</button>}\n      </div>\n    </section>\n  );\n}\n\n'''
    text = replace_between(text, "function CompanyFilters", "function CompanyListingPage", discovery, "CompanyFilters")

    listing = '''function CompanyListingPage() {\n  const { loading, error, data } = useDataset("companies/companies");\n  const activityState = useDataset("companies/company-activities");\n  const reportInsightState = useDataset("companies/company_report_insights");\n  const [searchParams, setSearchParams] = useSearchParams();\n  const [comparisonOpen, setComparisonOpen] = useState(false);\n  const compareButtonRef = useRef(null);\n  const items = getCompanyItems(data);\n  const activitiesByCompany = useMemo(() => {\n    const rows = new Map();\n    for (const company of items) {\n      rows.set(company.company_id, getCompanyActivities(activityState.data, company.company_id).filter(isValidActivity));\n    }\n    return rows;\n  }, [activityState.data, items]);\n  const reportInsightsByCompany = useMemo(() => {\n    const rows = new Map();\n    for (const company of items) {\n      const insight = getCompanyReportInsight(reportInsightState.data, company.company_id);\n      if (insight) rows.set(company.company_id, insight);\n    }\n    return rows;\n  }, [items, reportInsightState.data]);\n  const summary = useMemo(() => getCompanySummary(items), [items]);\n  const roleOptions = useMemo(() => [\n    { value: "all", label: "전체", count: summary.total },\n    ...companyRoleOptions(items),\n  ], [items, summary.total]);\n  const validValues = useMemo(() => ({\n    roles: roleOptions.map((option) => option.value),\n    companyIds: items.map((company) => company.company_id),\n  }), [items, roleOptions]);\n\n  useEffect(() => {\n    if (!items.length) return;\n    const { params, changed } = sanitizeCompanySearchParams(searchParams, validValues);\n    if (changed) setSearchParams(params, { replace: true });\n  }, [items.length, searchParams, setSearchParams, validValues]);\n\n  const values = useMemo(() => ({\n    q: searchParams.get("q") || "",\n    role: getValidParam(searchParams, "role", ["all", ...validValues.roles], "all"),\n    sort: getValidParam(searchParams, "sort", COMPANY_SORT_VALUES, "name"),\n  }), [searchParams, validValues]);\n\n  const setParam = useCallback((key, value) => {\n    const next = new URLSearchParams(searchParams);\n    const defaults = { q: "", role: "all", sort: "name" };\n    if (!value || value === defaults[key]) next.delete(key);\n    else next.set(key, value);\n    if (next.toString() === searchParams.toString()) return;\n    setSearchParams(next, { replace: true });\n  }, [searchParams, setSearchParams]);\n\n  const setComparisonSelection = useCallback((ids) => {\n    const normalized = normalizeComparisonSelection(ids, items);\n    const next = new URLSearchParams(searchParams);\n    if (normalized.length) next.set("compare", serializeCompareSelection(normalized));\n    else next.delete("compare");\n    setSearchParams(next);\n    if (normalized.length < 2) setComparisonOpen(false);\n  }, [items, searchParams, setSearchParams]);\n\n  const selectedIds = useMemo(() => normalizeComparisonSelection(parseCompareParam(searchParams.get("compare")), items), [items, searchParams]);\n  const selectedCompanies = useMemo(() => selectedIds\n    .map((id) => items.find((company) => company.company_id === id))\n    .filter(Boolean), [items, selectedIds]);\n\n  const toggleCompare = useCallback((companyId) => {\n    if (selectedIds.includes(companyId)) {\n      setComparisonSelection(selectedIds.filter((id) => id !== companyId));\n      return;\n    }\n    if (selectedIds.length >= MAX_COMPARISON_COMPANIES) return;\n    setComparisonSelection([...selectedIds, companyId]);\n  }, [selectedIds, setComparisonSelection]);\n\n  const reset = () => {\n    const next = new URLSearchParams(searchParams);\n    ["q", "role", "sort"].forEach((key) => next.delete(key));\n    setSearchParams(next, { replace: true });\n  };\n\n  const filtered = useMemo(() => items\n    .filter((company) => companyMatchesFilters(company, values))\n    .sort((a, b) => {\n      if (values.sort === "recent_activity") {\n        const latest = (company) => (activitiesByCompany.get(company.company_id) || [])[0]?.publishedAt || "";\n        return String(latest(b)).localeCompare(String(latest(a))) || compareCompanies(a, b, "name");\n      }\n      return compareCompaniesForMvp(a, b, values.sort, compareCompanies);\n    }), [activitiesByCompany, items, values]);\n\n  return (\n    <Layout>\n      <section className="page-heading">\n        <p className="eyebrow">COMPANY</p>\n        <h1>스틸 모듈러 기업정보</h1>\n        <p>건설사와 모듈러 제작 전문 업체의 사업 역량과 경쟁 현황을 확인합니다.</p>\n      </section>\n      <div className="content-layout company-list-layout">\n        <CompanyDiscoveryToolbar\n          values={values}\n          setParam={setParam}\n          roleOptions={roleOptions}\n          filteredCount={filtered.length}\n          onReset={reset}\n        />\n        <section className="results" aria-live="polite">\n          {loading && <div className="state">기업정보를 불러오는 중입니다.</div>}\n          {error && <div className="state error">기업정보 데이터를 불러오지 못했습니다.</div>}\n          {!loading && !error && items.length === 0 && <div className="state">등록된 기업정보가 없습니다.</div>}\n          {!loading && !error && items.length > 0 && filtered.length === 0 && <div className="state">현재 검색조건에 맞는 기업정보가 없습니다.</div>}\n          <CompanyCardGrid companies={filtered} selectedIds={selectedIds} onToggleCompare={toggleCompare} activitiesByCompany={activitiesByCompany} reportInsightsByCompany={reportInsightsByCompany} />\n        </section>\n      </div>\n      <CompanyComparisonPanel\n        open={comparisonOpen}\n        companies={selectedCompanies}\n        onClose={() => {\n          setComparisonOpen(false);\n          compareButtonRef.current?.focus();\n        }}\n        triggerRef={compareButtonRef}\n      />\n      <CompanyComparisonBar\n        selectedCompanies={selectedCompanies}\n        onRemove={(companyId) => setComparisonSelection(selectedIds.filter((id) => id !== companyId))}\n        onClear={() => setComparisonSelection([])}\n        onOpen={() => setComparisonOpen(true)}\n        compareButtonRef={compareButtonRef}\n      />\n    </Layout>\n  );\n}\n\n'''
    text = replace_between(text, "function CompanyListingPage", "function CompanyDetailPage", listing, "CompanyListingPage")
    write(path, text)


def patch_company_card() -> None:
    path = "frontend/src/components/company/CompanyComparisonMvp.jsx"
    text = read(path)
    text = text.replace("  getCompanyVerificationLevel,\n", "").replace("  getVerificationLevelLabel,\n", "")
    text = re.sub(r"\n\s*const verificationLevel = getVerificationLevelLabel\(getCompanyVerificationLevel\(company\)\);", "", text, count=1)
    text = re.sub(
        r'<div className="badge-row">\s*<span>\{metric\.typeLabel\}</span>\s*<span>\{metric\.relationshipLabel\}</span>\s*<span className=\{`company-status \$\{metric\.dataStatus\}`\}>\{metric\.dataStatusLabel\}</span>\s*</div>',
        '<div className="badge-row">\n          <span>{metric.typeLabel}</span>\n        </div>',
        text,
        count=1,
    )
    text = re.sub(r'<p className="company-card-meta">[^<]*latestVerifiedAt\}[^<]*</p>', '<p className="company-card-meta">최근 검증일 {latestVerifiedAt}</p>', text, count=1)
    text = text.replace("<span>{metric.tierLabel}</span>", "<span>{metric.typeLabel}</span>", 1)
    write(path, text)


def patch_url_params() -> None:
    path = "frontend/src/companyUrlParams.js"
    write(path, '''export const COMPANY_SORT_VALUES = ["name", "recent_activity", "revenue", "verified_projects"];\nconst LEGACY_ROLE_ALIASES = {\n  specialist_manufacturer: "modular_specialist",\n  modular_integrator: "modular_specialist",\n  producer_group: "modular_specialist",\n};\nconst OBSOLETE_FILTER_KEYS = ["relationship", "tier", "status", "audit", "facility"];\n\nexport function sanitizeCompanySearchParams(searchParams, validValues) {\n  const next = new URLSearchParams(searchParams);\n  let changed = false;\n  for (const key of OBSOLETE_FILTER_KEYS) {\n    if (next.has(key)) {\n      next.delete(key);\n      changed = true;\n    }\n  }\n  const legacyRole = next.get("role");\n  if (LEGACY_ROLE_ALIASES[legacyRole]) {\n    next.set("role", LEGACY_ROLE_ALIASES[legacyRole]);\n    changed = true;\n  }\n  const rules = {\n    role: ["all", ...(validValues.roles || [])],\n    sort: COMPANY_SORT_VALUES,\n  };\n  for (const [key, allowed] of Object.entries(rules)) {\n    const value = next.get(key);\n    if (!value) continue;\n    if (!allowed.includes(value)) {\n      next.delete(key);\n      changed = true;\n    }\n  }\n  for (const key of [...next.keys()]) {\n    if (!["q", "role", "sort", "compare"].includes(key)) {\n      next.delete(key);\n      changed = true;\n    }\n  }\n  const compare = next.get("compare");\n  if (compare && Array.isArray(validValues.companyIds)) {\n    const allowed = new Set(validValues.companyIds);\n    const normalized = [];\n    for (const id of compare.split(",").map((item) => item.trim()).filter(Boolean)) {\n      if (!allowed.has(id) || normalized.includes(id)) continue;\n      normalized.push(id);\n      if (normalized.length === 4) break;\n    }\n    const serialized = normalized.join(",");\n    if (!serialized) next.delete("compare");\n    else next.set("compare", serialized);\n    if (serialized !== compare) changed = true;\n  }\n  return { params: next, changed };\n}\n''')


def patch_builder() -> None:
    path = "scripts/build_company_report_insights.py"
    text = read(path)
    text = replace_once(text, 'DEFAULT_OUTPUT = ROOT / "frontend" / "public" / "data" / "companies" / "company_report_insights.json"\n', 'DEFAULT_OUTPUT = ROOT / "frontend" / "public" / "data" / "companies" / "company_report_insights.json"\nDEFAULT_COMPANY_MASTER = ROOT / "frontend" / "public" / "data" / "companies" / "companies.json"\n', "company master constant")
    marker = 'SOURCE_SCHEMA_VERSION = "company_audit_financials_v1"\n'
    groups = '''SOURCE_SCHEMA_VERSION = "company_audit_financials_v1"\nCOMPARISON_GROUPS = {\n    "general_contractor": {\n        "group_id": "general_contractor",\n        "label": "건설사",\n        "company_types": ["general_contractor"],\n    },\n    "modular_specialist": {\n        "group_id": "modular_specialist",\n        "label": "모듈러 제작 전문 업체",\n        "company_types": ["specialist_manufacturer", "modular_integrator", "modular_specialist", "producer_group"],\n    },\n}\n'''
    text = replace_once(text, marker, groups, "comparison groups")
    helper_marker = '\ndef discover_source_files(input_root: Path = DEFAULT_INPUT_ROOT) -> list[Path]:\n'
    helpers = '''\ndef comparison_group_for_company_type(company_type: str | None) -> dict[str, Any] | None:\n    for group in COMPARISON_GROUPS.values():\n        if company_type in group["company_types"]:\n            return group\n    return None\n\n\ndef load_company_comparison_groups(path: Path = DEFAULT_COMPANY_MASTER) -> dict[str, dict[str, Any]]:\n    payload = json.loads(path.read_text(encoding="utf-8"))\n    rows = payload.get("companies") if isinstance(payload, dict) else payload\n    mapping: dict[str, dict[str, Any]] = {}\n    for company in rows:\n        company_id = company.get("company_id")\n        if not company_id:\n            continue\n        group = comparison_group_for_company_type(company.get("company_type"))\n        mapping[company_id] = {\n            "company_type": company.get("company_type"),\n            "group_id": group["group_id"] if group else None,\n            "group_label": group["label"] if group else None,\n        }\n    return mapping\n\n'''
    text = replace_once(text, helper_marker, helpers + helper_marker, "comparison group helpers")
    peer_start = "def build_peer_benchmarks(companies: list[dict[str, Any]]) -> None:\n"
    peer_end = "def public_attribution(source_payload: dict[str, Any]) -> dict[str, Any]:\n"
    peer = '''def benchmark_difference_display(company_value: int | float | None, median_value: int | float | None, source: str) -> str | None:\n    if company_value is None or median_value is None:\n        return None\n    difference = float(company_value) - float(median_value)\n    if difference == 0:\n        return "중앙값과 같음"\n    direction = "높음" if difference > 0 else "낮음"\n    if source == "derived_metrics":\n        return f"중앙값보다 {abs(difference):,.1f}%p {direction}"\n    eok = Decimal(str(abs(difference))) / Decimal(100_000_000)\n    return f"중앙값보다 {eok.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP):,.1f}억원 {direction}"\n\n\ndef build_peer_benchmarks(companies: list[dict[str, Any]]) -> None:\n    for company in companies:\n        benchmarks = []\n        company_context = company.get("comparison_context", {})\n        comparison_group_id = company_context.get("group_id")\n        for config in PEER_BENCHMARK_METRICS:\n            metric_id = config["metric_id"]\n            source = config["source"]\n            scoped_peers = [\n                peer for peer in companies\n                if comparison_group_id is not None\n                and peer.get("comparison_context", {}).get("group_id") == comparison_group_id\n                and peer.get("latest_year") == company.get("latest_year")\n                and peer.get("currency") == company.get("currency")\n                and peer.get("financial_scope") == company.get("financial_scope")\n                and comparable_metric_value(peer, metric_id, source) is not None\n            ]\n            value = comparable_metric_value(company, metric_id, source)\n            comparable = value is not None and len(scoped_peers) >= 3\n            if comparable:\n                reverse = config["comparison_direction"] == "higher_is_larger"\n                ordered = sorted(scoped_peers, key=lambda item: comparable_metric_value(item, metric_id, source), reverse=reverse)\n                rank = [peer["company_id"] for peer in ordered].index(company["company_id"]) + 1\n                values = [comparable_metric_value(peer, metric_id, source) for peer in scoped_peers]\n                best_value = comparable_metric_value(ordered[0], metric_id, source)\n                median_value = float(median(values))\n                comparison_label = f"{len(scoped_peers)}개 중 {rank}위"\n                reason = None\n            else:\n                rank = None\n                best_value = None\n                median_value = None\n                comparison_label = "동일 유형 재무 비교 준비 중"\n                if value is None:\n                    reason = "현재 기업의 해당 지표값이 확인되지 않았습니다."\n                elif comparison_group_id is None:\n                    reason = "canonical 기업유형이 자동 재무 비교 그룹에 포함되지 않습니다."\n                else:\n                    reason = "같은 기업유형의 비교 가능한 감사재무가 3개 미만이라 상대 위치를 표시하지 않습니다."\n            benchmarks.append({\n                "metric_id": metric_id,\n                "comparison_group_id": comparison_group_id,\n                "comparison_group_label": company_context.get("group_label"),\n                "comparison_year": company.get("latest_year"),\n                "comparison_currency": company.get("currency"),\n                "comparison_financial_scope": company.get("financial_scope"),\n                "company_value": value,\n                "company_display": metric_display_for_peer(company, metric_id, source),\n                "peer_count": len(scoped_peers),\n                "comparison_universe_count": len(scoped_peers),\n                "other_peer_count": max(len(scoped_peers) - (1 if value is not None else 0), 0),\n                "current_company_included": value is not None and any(peer["company_id"] == company["company_id"] for peer in scoped_peers),\n                "rank": rank,\n                "median": median_value,\n                "median_display": peer_value_display(median_value, source),\n                "median_difference_display": benchmark_difference_display(value, median_value, source),\n                "best_value": best_value,\n                "reference_value": best_value,\n                "reference_value_display": peer_value_display(best_value, source),\n                "reference_value_label": "비교 범위 최대값" if config["comparison_direction"] == "higher_is_larger" else "비교 범위 최소값",\n                "comparison_direction": config["comparison_direction"],\n                "comparison_label": comparison_label,\n                "comparable": comparable,\n                "not_comparable_reason": reason,\n                "source_ids": metric_source_refs(comparable_metric(company, metric_id, source)),\n                "calculation_basis": "same_company_group_latest_year_currency_financial_scope_minimum_three_values",\n            })\n        company["peer_benchmarks"] = benchmarks\n\n\n'''
    text = replace_between(text, peer_start, peer_end, peer + peer_end, "peer benchmark builder")
    build_start = "def build_view_model(input_root: Path = DEFAULT_INPUT_ROOT, base_ref: str | None = \"origin/main\") -> dict[str, Any]:\n"
    build_end = "def main() -> int:\n"
    build_block = '''def apply_comparison_context(company: dict[str, Any], group_map: dict[str, dict[str, Any]]) -> None:\n    group = group_map.get(company["company_id"], {})\n    company["comparison_context"] = {\n        "company_type": group.get("company_type", "unknown"),\n        "group_id": group.get("group_id"),\n        "group_label": group.get("group_label"),\n        "minimum_peer_count": 3,\n        "calculation_basis": "canonical_company_type_same_latest_year_currency_financial_scope",\n    }\n\n\ndef build_view_model(input_root: Path = DEFAULT_INPUT_ROOT, base_ref: str | None = "origin/main", company_master: Path = DEFAULT_COMPANY_MASTER) -> dict[str, Any]:\n    group_map = load_company_comparison_groups(company_master)\n    companies = []\n    for path in discover_source_files(input_root):\n        payload = load_payload(path)\n        validation = validate(payload, base_ref=base_ref)\n        if not validation["valid"]:\n            raise ValueError(f"source validation failed for {path}: {validation['issues']}")\n        insight = build_company_insight(payload)\n        apply_comparison_context(insight, group_map)\n        companies.append(insight)\n    companies.sort(key=lambda item: item["company_id"])\n    build_peer_benchmarks(companies)\n    return {"schema_version": SCHEMA_VERSION, "companies": companies}\n\n\n'''
    text = replace_between(text, build_start, build_end, build_block + build_end, "build_view_model")
    text = replace_once(text, '    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)\n', '    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)\n    parser.add_argument("--company-master", type=Path, default=DEFAULT_COMPANY_MASTER)\n', "company master cli")
    text = replace_once(text, '    payload = build_view_model(args.input_root, base_ref=args.base_ref)\n', '    payload = build_view_model(args.input_root, base_ref=args.base_ref, company_master=args.company_master)\n', "build view model call")
    write(path, text)


def patch_schema() -> None:
    path = ROOT / "schemas/company_reports/company_report_insights_v1.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    defs = schema["$defs"]
    company = defs["companyReportInsight"]
    if "comparison_context" not in company["required"]:
        company["required"].insert(company["required"].index("peer_benchmarks"), "comparison_context")
    company["properties"]["comparison_context"] = {"$ref": "#/$defs/comparisonContext"}
    defs["comparisonContext"] = {
        "type": "object",
        "required": ["company_type", "group_id", "group_label", "minimum_peer_count", "calculation_basis"],
        "properties": {
            "company_type": {"type": "string", "minLength": 1},
            "group_id": {"type": ["string", "null"]},
            "group_label": {"type": ["string", "null"]},
            "minimum_peer_count": {"type": "integer", "minimum": 3},
            "calculation_basis": {"const": "canonical_company_type_same_latest_year_currency_financial_scope"},
        },
        "additionalProperties": False,
    }
    peer = defs["peerBenchmark"]
    new_required = [
        "comparison_group_id", "comparison_group_label", "comparison_year", "comparison_currency",
        "comparison_financial_scope", "median_difference_display",
    ]
    for key in reversed(new_required):
        if key not in peer["required"]:
            peer["required"].insert(1, key)
    peer["properties"].update({
        "comparison_group_id": {"type": ["string", "null"]},
        "comparison_group_label": {"type": ["string", "null"]},
        "comparison_year": {"type": "integer"},
        "comparison_currency": {"const": "KRW"},
        "comparison_financial_scope": {"enum": ["standalone", "consolidated", "standalone_and_consolidated"]},
        "median_difference_display": {"type": ["string", "null"]},
    })
    peer["properties"]["calculation_basis"] = {"const": "same_company_group_latest_year_currency_financial_scope_minimum_three_values"}
    path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def patch_overview() -> None:
    path = "frontend/src/components/company/CompanyOverviewTab.jsx"
    text = read(path)
    start = "function PeerPositionRows({ reportInsight, onTabChange }) {\n"
    end = "function RecentActivityPreview({ activities }) {\n"
    block = '''function PeerPositionRows({ reportInsight, onTabChange }) {\n  const rows = (reportInsight?.peer_benchmarks || []).slice(0, 3);\n  if (!rows.length) return null;\n  const groupLabel = reportInsight?.comparison_context?.group_label || "동일 유형";\n  return (\n    <div className="company-subsection compact-company-section">\n      <div className="company-subsection-heading">\n        <div>\n          <h3>동일 유형 기업 대비 재무 위치</h3>\n          <span className="comparison-group-label">비교 그룹 · {groupLabel}</span>\n        </div>\n        <button type="button" className="text-button" onClick={() => onTabChange?.("financial")}>재무 비교 자세히</button>\n      </div>\n      <p className="finance-note">같은 기업유형·연도·통화·재무제표 기준의 감사재무를 비교합니다.</p>\n      <div className="company-peer-compact-list" aria-label="동일 유형 기업 대비 재무 위치">\n        {rows.map((item) => (\n          <div key={item.metric_id}>\n            <strong>{peerBenchmarkLabel(item.metric_id)}</strong>\n            <span>{item.company_display || "확인되지 않음"}</span>\n            <span>{item.comparable ? `${item.comparison_universe_count ?? item.peer_count}개 중 ${item.rank}위` : "비교 준비 중"}</span>\n            <small>같은 유형 중앙값 {item.median_display || "확인되지 않음"}</small>\n            {item.median_difference_display && <small>{item.median_difference_display}</small>}\n          </div>\n        ))}\n      </div>\n    </div>\n  );\n}\n\n'''
    text = replace_between(text, start, end, block + end, "PeerPositionRows")
    write(path, text)


def patch_financial_panel() -> None:
    path = "frontend/src/components/company/CompanyAuditFinancialPanel.jsx"
    text = read(path)
    text = text.replace(
        'limitation: "동일 연도·통화·재무제표 범위에서 최소 3개 기업 값이 있을 때만 순위를 표시하며 종합 경쟁력 점수가 아닙니다.",',
        'limitation: "같은 기업유형·연도·통화·재무제표 범위에서 최소 3개 기업 값이 있을 때만 상대 위치를 표시하며 종합 경쟁력 점수가 아닙니다.",',
    )
    start = "function PeerBenchmarkPanel({ insight, benchmarks = [], onShowEvidence }) {\n"
    end = "export default function CompanyAuditFinancialPanel"
    block = '''function benchmarkRankText(item) {\n  if (!item.comparable || !item.rank) return "비교 준비 중";\n  const count = item.comparison_universe_count ?? item.peer_count;\n  return `${count}개 중 ${item.rank}위`;\n}\n\nfunction comparisonGroupLabel(insight, item) {\n  return item.comparison_group_label || insight?.comparison_context?.group_label || "동일 유형";\n}\n\nfunction PeerBenchmarkPanel({ insight, benchmarks = [], onShowEvidence }) {\n  if (!benchmarks.length) return null;\n  return (\n    <div className="company-subsection">\n      <div className="company-subsection-heading">\n        <div>\n          <h3>동일 유형 기업 재무 비교</h3>\n          <span>같은 기업유형·연도·통화·재무제표 범위에서만 비교합니다.</span>\n        </div>\n        <span className="comparison-group-label">비교 그룹 · {insight?.comparison_context?.group_label || "확인 중"}</span>\n      </div>\n      <div className="company-peer-grid" aria-label="동일 유형 기업 재무 비교">\n        {benchmarks.map((item) => (\n          <article className={`company-peer-card ${item.comparable ? "is-comparable" : "is-not-comparable"}`} key={item.metric_id}>\n            <span>{peerBenchmarkLabel(item.metric_id)}</span>\n            <strong>{item.company_display}</strong>\n            <p>{item.comparable ? benchmarkRankText(item) : item.not_comparable_reason}</p>\n            <dl className="company-mini-detail-list">\n              <div><dt>현재</dt><dd>{item.company_display}</dd></div>\n              <div><dt>같은 유형 중앙값</dt><dd>{item.median_display || "확인되지 않음"}</dd></div>\n              <div><dt>위치</dt><dd>{benchmarkRankText(item)}</dd></div>\n              <div><dt>중앙값과의 차이</dt><dd>{item.median_difference_display || "비교 준비 중"}</dd></div>\n            </dl>\n            <small>{item.comparable ? `${comparisonGroupLabel(insight, item)} 그룹 · ${item.comparison_direction === "higher_is_larger" ? "값이 큰 순" : "값이 낮은 순"}` : "다른 기업유형으로 대체 비교하지 않습니다."}</small>\n            <details className="comparison-basis-details">\n              <summary>비교 기준 보기</summary>\n              <dl className="company-mini-detail-list">\n                <div><dt>기업 유형</dt><dd>{comparisonGroupLabel(insight, item)}</dd></div>\n                <div><dt>기준 연도</dt><dd>{item.comparison_year || insight.latest_year}</dd></div>\n                <div><dt>재무제표 범위</dt><dd>{financialScopeLabel(item.comparison_financial_scope || insight.financial_scope)}</dd></div>\n                <div><dt>통화</dt><dd>{item.comparison_currency || insight.currency}</dd></div>\n                <div><dt>비교 가능 기업 수</dt><dd>{formatNumber(item.comparison_universe_count ?? item.peer_count, "개")}</dd></div>\n                <div><dt>최소 비교 기준</dt><dd>{formatNumber(insight.comparison_context?.minimum_peer_count || 3, "개")}</dd></div>\n                <div><dt>현재 기업 포함</dt><dd>{item.current_company_included ? "예" : "아니오"}</dd></div>\n              </dl>\n            </details>\n            {onShowEvidence && (\n              <button type="button" className="text-button evidence-inline-button" onClick={() => onShowEvidence(peerEvidence(insight, item))}>\n                근거 보기\n              </button>\n            )}\n          </article>\n        ))}\n      </div>\n    </div>\n  );\n}\n\n'''
    text = replace_between(text, start, end, block + end, "PeerBenchmarkPanel")
    write(path, text)


def patch_styles() -> None:
    path = "frontend/src/styles.css"
    text = read(path)
    addition = '''\n/* Phase 8B-1: simplified company discovery + same-type financial comparison */\n.company-list-layout {\n  display: block;\n}\n.company-discovery-toolbar {\n  border: 1px solid var(--border, #dfe3df);\n  border-radius: 14px;\n  background: #fff;\n  padding: 18px;\n  margin-bottom: 18px;\n}\n.company-discovery-primary {\n  display: grid;\n  grid-template-columns: minmax(360px, 1fr) minmax(280px, 1.6fr) minmax(180px, .55fr);\n  gap: 14px;\n  align-items: end;\n}\n.company-toolbar-label, .company-toolbar-search, .company-toolbar-sort {\n  display: grid;\n  gap: 8px;\n  font-weight: 700;\n}\n.company-type-segmented {\n  display: flex;\n  gap: 8px;\n  flex-wrap: wrap;\n}\n.company-type-segmented button {\n  display: inline-flex;\n  gap: 8px;\n  align-items: center;\n  border: 1px solid var(--border, #d7ddd8);\n  border-radius: 999px;\n  background: #fff;\n  padding: 10px 14px;\n  cursor: pointer;\n}\n.company-type-segmented button.active, .company-type-segmented button[aria-checked="true"] {\n  border-color: #16794a;\n  box-shadow: inset 0 0 0 1px #16794a;\n}\n.company-discovery-meta {\n  display: flex;\n  justify-content: space-between;\n  align-items: center;\n  margin-top: 14px;\n}\n.company-discovery-meta p { margin: 0; color: #59645d; }\n.comparison-group-label { font-weight: 700; color: #176b45; }\n.comparison-basis-details { margin-top: 10px; }\n.comparison-basis-details summary { cursor: pointer; font-weight: 700; }\n@media (max-width: 780px) {\n  .company-discovery-primary { grid-template-columns: 1fr; }\n  .company-type-segmented { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); }\n  .company-type-segmented button { justify-content: center; padding: 9px 8px; }\n}\n@media (max-width: 420px) {\n  .company-type-segmented { grid-template-columns: 1fr; }\n}\n'''
    if "Phase 8B-1: simplified company discovery" not in text:
        text += addition
    write(path, text)


def patch_tests() -> None:
    # URL contract test: remove obsolete hidden filters and require simplified sort values.
    path = "frontend/scripts/test-company-url.mjs"
    text = read(path)
    text = text.replace('assert.ok(COMPANY_SORT_VALUES.includes("tier"));', 'assert.equal(COMPANY_SORT_VALUES.includes("tier"), false);')
    text = text.replace('assert.ok(COMPANY_SORT_VALUES.includes("production"));', 'assert.equal(COMPANY_SORT_VALUES.includes("production"), false);')
    write(path, text)

    path = "frontend/scripts/test-company-detail-ui.mjs"
    text = read(path)
    text = text.replace('"동료 비교"', '"동일 유형 기업 재무 비교"')
    text = text.replace('"reference_value_label"', '"median_difference_display"')
    write(path, text)


def main() -> None:
    patch_app()
    patch_company_card()
    patch_url_params()
    patch_builder()
    patch_schema()
    patch_overview()
    patch_financial_panel()
    patch_styles()
    patch_tests()
    print("Phase 8B-1 migration applied")


if __name__ == "__main__":
    main()
