from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one replacement target, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> int:
    insights = ROOT / "frontend/src/companyInsights.js"
    app = ROOT / "frontend/src/App.jsx"

    replace_once(
        insights,
        '''export function getStrategicCompetitiveRole(company) {\n  if (isModularSpecialistCompany(company)) return "direct_competitor";\n  return company?.competitive_role || "unknown";\n}\n''',
        '''export function getStrategicCompetitiveRole(company) {\n  const overrideRole = company?.strategy_override?.strategic_role;\n  if (overrideRole && overrideRole !== "inherit") return overrideRole;\n  return company?.competitive_role || "unknown";\n}\n''',
    )

    replace_once(
        app,
        '''} from "./companyInsights";\nimport {\n  MAX_COMPARISON_COMPANIES,\n''',
        '''} from "./companyInsights";\nimport { applyCompanyStrategy } from "./companyStrategy";\nimport {\n  MAX_COMPARISON_COMPANIES,\n''',
    )

    replace_once(
        app,
        '''  const companyState = useDataset("companies/companies");\n  const favorites = useFavorites();\n''',
        '''  const companyState = useDataset("companies/companies");\n  const strategyState = useDataset("companies/company_strategy");\n  const favorites = useFavorites();\n''',
    )

    replace_once(
        app,
        '''  const companyItems = getCompanyItems(companyState.data);\n  const companySummary = getCompanySummary(companyItems);\n''',
        '''  const companyItems = useMemo(\n    () => applyCompanyStrategy(getCompanyItems(companyState.data), strategyState.data),\n    [companyState.data, strategyState.data],\n  );\n  const companySummary = getCompanySummary(companyItems);\n''',
    )

    replace_once(
        app,
        '''function CompanyListingPage() {\n  const { loading, error, data } = useDataset("companies/companies");\n  const activityState = useDataset("companies/company-activities");\n''',
        '''function CompanyListingPage() {\n  const { loading, error, data } = useDataset("companies/companies");\n  const strategyState = useDataset("companies/company_strategy");\n  const activityState = useDataset("companies/company-activities");\n''',
    )

    replace_once(
        app,
        '''  const compareButtonRef = useRef(null);\n  const items = getCompanyItems(data);\n  const activitiesByCompany = useMemo(() => {\n''',
        '''  const compareButtonRef = useRef(null);\n  const items = useMemo(\n    () => applyCompanyStrategy(getCompanyItems(data), strategyState.data),\n    [data, strategyState.data],\n  );\n  const activitiesByCompany = useMemo(() => {\n''',
    )

    replace_once(
        app,
        '''function CompanyDetailPage() {\n  const { companyId } = useParams();\n  const [searchParams, setSearchParams] = useSearchParams();\n  const { loading, error, data } = useDataset("companies/companies");\n  const activityState = useDataset("companies/company-activities");\n  const reportInsightState = useDataset("companies/company_report_insights");\n  const company = getCompanyItems(data).find((item) => item.company_id === companyId);\n''',
        '''function CompanyDetailPage() {\n  const { companyId } = useParams();\n  const [searchParams, setSearchParams] = useSearchParams();\n  const { loading, error, data } = useDataset("companies/companies");\n  const strategyState = useDataset("companies/company_strategy");\n  const activityState = useDataset("companies/company-activities");\n  const reportInsightState = useDataset("companies/company_report_insights");\n  const strategyCompanies = useMemo(\n    () => applyCompanyStrategy(getCompanyItems(data), strategyState.data),\n    [data, strategyState.data],\n  );\n  const company = strategyCompanies.find((item) => item.company_id === companyId);\n''',
    )

    print("Phase 8C-3 strategy overlay migration applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
