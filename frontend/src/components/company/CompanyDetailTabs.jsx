import { COMPANY_DETAIL_TABS } from "./companyDetailHelpers";

export default function CompanyDetailTabs({ activeTab, onChange }) {
  const activeIndex = Math.max(0, COMPANY_DETAIL_TABS.findIndex((tab) => tab.value === activeTab));

  const onKeyDown = (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    let nextIndex = activeIndex;
    if (event.key === "ArrowLeft") nextIndex = activeIndex === 0 ? COMPANY_DETAIL_TABS.length - 1 : activeIndex - 1;
    if (event.key === "ArrowRight") nextIndex = activeIndex === COMPANY_DETAIL_TABS.length - 1 ? 0 : activeIndex + 1;
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = COMPANY_DETAIL_TABS.length - 1;
    onChange(COMPANY_DETAIL_TABS[nextIndex].value);
  };

  return (
    <div className="company-tabs" role="tablist" aria-label="기업 상세 정보 탭" onKeyDown={onKeyDown}>
      {COMPANY_DETAIL_TABS.map((tab) => (
        <button
          aria-controls={`company-tab-panel-${tab.value}`}
          aria-selected={activeTab === tab.value}
          className={activeTab === tab.value ? "active" : ""}
          id={`company-tab-${tab.value}`}
          key={tab.value}
          onClick={() => onChange(tab.value)}
          role="tab"
          tabIndex={activeTab === tab.value ? 0 : -1}
          type="button"
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
