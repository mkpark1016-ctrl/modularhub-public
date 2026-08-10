import { useCallback, useEffect, useState } from "react";
import { getCompanyActivityHistory } from "../../companyActivities";
import CompanyActivityTimeline from "./CompanyActivityTimeline";
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

const DATA_BASE = import.meta.env.VITE_DATA_BASE_URL || "/data";

export default function CompanyDetailView({ company, activeTab, onTabChange, activities = [], reportInsight = null }) {
  const tab = normalizeCompanyTab(activeTab);
  const [evidence, setEvidence] = useState(null);
  const [historyActivities, setHistoryActivities] = useState(null);
  const showEvidence = useCallback((nextEvidence) => setEvidence(nextEvidence), []);

  useEffect(() => {
    let active = true;
    if (tab !== "activity" || !company?.company_id) return () => { active = false; };

    setHistoryActivities(null);
    const historyUrl = `${DATA_BASE}/companies/company-activity-history/${encodeURIComponent(company.company_id)}.json`;
    fetch(historyUrl)
      .then((response) => {
        if (!response.ok) throw new Error(`history unavailable (${response.status})`);
        return response.json();
      })
      .then((payload) => {
        if (!active) return;
        const history = getCompanyActivityHistory(payload, company.company_id);
        if (history) setHistoryActivities(history);
      })
      .catch(() => {
        if (active) setHistoryActivities(null);
      });

    return () => { active = false; };
  }, [company?.company_id, tab]);

  const timelineActivities = historyActivities ?? activities;

  return (
    <article className="detail-page company-detail">
      <CompanyDetailHeader company={company} activeTab={tab} reportInsight={reportInsight} />
      <CompanyDetailTabs activeTab={tab} onChange={onTabChange} />
      {tab === "overview" && <CompanyOverviewTab company={company} activities={activities} reportInsight={reportInsight} onShowEvidence={showEvidence} onTabChange={onTabChange} />}
      {tab === "activity" && (
        <section className="summary company-tab-panel" id="company-tab-panel-activity" role="tabpanel" aria-labelledby="company-tab-activity">
          <h2>활동·동향</h2>
          <p className="finance-note">공개 뉴스와 사업정보에서 확인된 기업 활동을 최신순으로 누적해 보여줍니다.</p>
          <CompanyActivityTimeline activities={timelineActivities} />
        </section>
      )}
      {tab === "financial" && <CompanyFinancialTab company={company} reportInsight={reportInsight} onShowEvidence={showEvidence} />}
      {tab === "production" && <CompanyProductionTab company={company} onShowEvidence={showEvidence} />}
      {tab === "projects" && <CompanyProjectTab company={company} onShowEvidence={showEvidence} />}
      {tab === "technology" && <CompanyTechnologyTab company={company} onShowEvidence={showEvidence} />}
      {tab === "evidence" && <CompanyEvidenceTab company={company} reportInsight={reportInsight} onShowEvidence={showEvidence} onTabChange={onTabChange} />}
      <EvidenceDrawer evidence={evidence} onClose={() => setEvidence(null)} />
    </article>
  );
}
