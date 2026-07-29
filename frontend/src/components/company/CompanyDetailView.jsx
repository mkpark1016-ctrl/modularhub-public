import { useCallback, useState } from "react";
import CompanyDetailHeader from "./CompanyDetailHeader";
import CompanyDetailTabs from "./CompanyDetailTabs";
import CompanyEvidenceTab from "./CompanyEvidenceTab";
import CompanyFinancialTab from "./CompanyFinancialTab";
import CompanyOverviewTab from "./CompanyOverviewTab";
import CompanyProductionTab from "./CompanyProductionTab";
import CompanyProjectTab from "./CompanyProjectTab";
import CompanyTechnologyTab from "./CompanyTechnologyTab";
import EvidenceDrawer from "./EvidenceDrawer";
import { normalizeCompanyTab } from "./companyDetailHelpers";

export default function CompanyDetailView({ company, activeTab, onTabChange, activities = [], reportInsight = null }) {
  const tab = normalizeCompanyTab(activeTab);
  const [evidence, setEvidence] = useState(null);
  const showEvidence = useCallback((nextEvidence) => setEvidence(nextEvidence), []);
  return (
    <article className="detail-page company-detail">
      <CompanyDetailHeader company={company} activeTab={tab} reportInsight={reportInsight} />
      <CompanyDetailTabs activeTab={tab} onChange={onTabChange} />
      {tab === "overview" && <CompanyOverviewTab company={company} activities={activities} reportInsight={reportInsight} onShowEvidence={showEvidence} onTabChange={onTabChange} />}
      {tab === "financial" && <CompanyFinancialTab company={company} reportInsight={reportInsight} onShowEvidence={showEvidence} />}
      {tab === "production" && <CompanyProductionTab company={company} onShowEvidence={showEvidence} />}
      {tab === "projects" && <CompanyProjectTab company={company} onShowEvidence={showEvidence} />}
      {tab === "technology" && <CompanyTechnologyTab company={company} onShowEvidence={showEvidence} />}
      {tab === "evidence" && <CompanyEvidenceTab company={company} reportInsight={reportInsight} onShowEvidence={showEvidence} onTabChange={onTabChange} />}
      <EvidenceDrawer evidence={evidence} onClose={() => setEvidence(null)} />
    </article>
  );
}
