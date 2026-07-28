import CompanyDetailHeader from "./CompanyDetailHeader";
import CompanyDetailTabs from "./CompanyDetailTabs";
import CompanyEvidenceTab from "./CompanyEvidenceTab";
import CompanyFinancialTab from "./CompanyFinancialTab";
import CompanyOverviewTab from "./CompanyOverviewTab";
import CompanyProductionTab from "./CompanyProductionTab";
import CompanyProjectTab from "./CompanyProjectTab";
import CompanyTechnologyTab from "./CompanyTechnologyTab";
import { normalizeCompanyTab } from "./companyDetailHelpers";

export default function CompanyDetailView({ company, activeTab, onTabChange, activities = [] }) {
  const tab = normalizeCompanyTab(activeTab);
  return (
    <article className="detail-page company-detail">
      <CompanyDetailHeader company={company} />
      <CompanyDetailTabs activeTab={tab} onChange={onTabChange} />
      {tab === "overview" && <CompanyOverviewTab company={company} activities={activities} />}
      {tab === "financial" && <CompanyFinancialTab company={company} />}
      {tab === "production" && <CompanyProductionTab company={company} />}
      {tab === "projects" && <CompanyProjectTab company={company} />}
      {tab === "technology" && <CompanyTechnologyTab company={company} />}
      {tab === "evidence" && <CompanyEvidenceTab company={company} />}
    </article>
  );
}
