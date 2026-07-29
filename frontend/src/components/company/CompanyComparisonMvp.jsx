import { useEffect, useMemo, useRef } from "react";
import { Link } from "react-router-dom";
import {
  MAX_COMPARISON_COMPANIES,
  MIN_COMPARISON_COMPANIES,
  getComparisonMetric,
  serializeCompareSelection,
} from "../../companyComparison";
import {
  getCompanyResearchGapCount,
  getCompanyCompactSummary,
  getCompanyDataGapCount,
  getCompanyVerificationLevel,
  getLatestVerifiedAt,
  getVerificationLevelLabel,
} from "../../companyInsights";
import { formatDate, formatKrw, formatNumber, formatPercent, labelValue } from "./companyDetailHelpers";

function joinLabels(values, emptyText = "확인되지 않음") {
  const labels = (Array.isArray(values) ? values : []).map((value) => labelValue(value, "")).filter(Boolean);
  return labels.length ? labels.join(", ") : emptyText;
}

function formatMargin(value) {
  return value === null || value === undefined ? "확인되지 않음" : formatPercent(value);
}

function facilityText(metric) {
  if (metric.productionConfirmed === null) return "확인되지 않음";
  if (metric.productionConfirmed === 0) {
    return metric.productionPlanned > 0 ? `확인 시설 없음 · 계획 ${formatNumber(metric.productionPlanned, "개")}` : "확인 시설 없음";
  }
  const parts = [`확인 ${formatNumber(metric.productionConfirmed, "개")}`];
  if (metric.productionPlanned > 0) parts.push(`계획 ${formatNumber(metric.productionPlanned, "개")}`);
  return parts.join(" · ");
}

function projectText(metric) {
  const parts = [`검증 ${formatNumber(metric.verifiedProjects, "건")}`];
  if (metric.pipelineProjects > 0) parts.push(`파이프라인 ${formatNumber(metric.pipelineProjects, "건")}`);
  return parts.join(" · ");
}

export function CompanySummaryCard({ company, selected, selectionDisabled, onToggleCompare, activities = [] }) {
  const metric = getComparisonMetric(company);
  const gapCount = getCompanyDataGapCount(company);
  const verificationLevel = getVerificationLevelLabel(getCompanyVerificationLevel(company));
  const latestVerifiedAt = formatDate(getLatestVerifiedAt(company));
  const latestActivity = activities[0];
  const cautionText = gapCount > 0
    ? `보완 필요 ${formatNumber(gapCount, "건")}`
    : (getCompanyResearchGapCount(company) > 0 ? `조사 공백 ${formatNumber(getCompanyResearchGapCount(company), "건")}` : "");
  return (
    <article className="result-card company-card company-summary-card" tabIndex="0">
      <div className="card-topline">
        <div className="badge-row">
          <span>{metric.typeLabel}</span>
          <span>{metric.relationshipLabel}</span>
          <span className={`company-status ${metric.dataStatus}`}>{metric.dataStatusLabel}</span>
        </div>
      </div>
      <div className="company-card-title-row">
        <div>
          <h2><Link to={`/companies/${company.company_id}`}>{company.company_name}</Link></h2>
          {metric.company_name_en && <p className="company-name-en">{metric.company_name_en}</p>}
        </div>
        <label className="compare-check">
          <input
            type="checkbox"
            checked={selected}
            disabled={!selected && selectionDisabled}
            onChange={() => onToggleCompare(company.company_id)}
            aria-label={`${company.company_name} 비교 선택`}
          />
          비교
        </label>
      </div>
      <p className="company-card-summary">{getCompanyCompactSummary(company)}</p>
      <dl className="company-kpi-list">
        <div><dt>최근 매출</dt><dd>{metric.revenue === null ? "확인되지 않음" : `${metric.latestFinancialYear}년 ${formatKrw(metric.revenue)}`}</dd></div>
        <div><dt>영업이익률</dt><dd>{formatMargin(metric.operatingMargin)}</dd></div>
        <div><dt>생산시설</dt><dd>{facilityText(metric)}</dd></div>
        <div><dt>검증 실적</dt><dd>{projectText(metric)}</dd></div>
      </dl>
      <div className="company-card-decision">
        <div>
          <span>최근 변화</span>
          <strong>{latestActivity ? latestActivity.title : "최근 90일 주요 변화 없음"}</strong>
          {latestActivity?.publishedAt && <small>{formatDate(latestActivity.publishedAt)}</small>}
        </div>
        {cautionText && (
          <div>
            <span>주의사항</span>
            <strong>{cautionText}</strong>
            <small>{latestVerifiedAt} 기준</small>
          </div>
        )}
      </div>
      <div className="company-tag-block">
        <span>{joinLabels(metric.targetMarkets.slice(0, 3))}</span>
        <span>{joinLabels(metric.modularMethods.slice(0, 2))}</span>
      </div>
      <p className="company-card-meta">검증 수준 {verificationLevel} · 최신 검증일 {latestVerifiedAt}</p>
      <div className="card-footer">
        <span>{metric.tierLabel}</span>
        <div className="card-actions">
          <Link to={`/companies/${company.company_id}`}>상세보기</Link>
        </div>
      </div>
    </article>
  );
}

export function CompanyCardGrid({ companies, selectedIds, onToggleCompare, activitiesByCompany = new Map() }) {
  const selectionDisabled = selectedIds.length >= MAX_COMPARISON_COMPANIES;
  return (
    <div className="company-card-grid">
      {companies.map((company) => (
        <CompanySummaryCard
          key={company.company_id}
          company={company}
          selected={selectedIds.includes(company.company_id)}
          selectionDisabled={selectionDisabled}
          onToggleCompare={onToggleCompare}
          activities={activitiesByCompany.get(company.company_id) || []}
        />
      ))}
    </div>
  );
}

export function CompanyComparisonBar({ selectedCompanies, onRemove, onClear, onOpen, compareButtonRef }) {
  if (!selectedCompanies.length) return null;
  const canCompare = selectedCompanies.length >= MIN_COMPARISON_COMPANIES;
  return (
    <aside className="company-comparison-bar" aria-label="기업 비교 선택">
      <div>
        <strong>비교 선택 {selectedCompanies.length}/{MAX_COMPARISON_COMPANIES}</strong>
        <div className="comparison-chip-row">
          {selectedCompanies.map((company) => (
            <button key={company.company_id} type="button" onClick={() => onRemove(company.company_id)} aria-label={`${company.company_name} 비교 선택 해제`}>
              {company.company_name} ×
            </button>
          ))}
        </div>
      </div>
      <div className="comparison-bar-actions">
        {selectedCompanies.length >= MAX_COMPARISON_COMPANIES && <span>최대 4개까지 비교할 수 있습니다.</span>}
        <button type="button" className="reset-button" onClick={onClear}>전체 해제</button>
        <button ref={compareButtonRef} type="button" className="primary-button" disabled={!canCompare} onClick={onOpen}>
          비교하기
        </button>
      </div>
    </aside>
  );
}

export function CompanyComparisonPanel({ open, companies, onClose, triggerRef }) {
  const headingRef = useRef(null);
  const rows = useMemo(() => companies.map((company) => ({ company, metric: getComparisonMetric(company) })), [companies]);

  useEffect(() => {
    if (!open) return undefined;
    headingRef.current?.focus();
    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        onClose();
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose, open, triggerRef]);

  if (!open) return null;
  return (
    <section className="comparison-panel" role="dialog" aria-modal="false" aria-labelledby="comparison-panel-title">
      <div className="comparison-panel-header">
        <div>
          <p className="eyebrow">COMPARE</p>
          <h2 id="comparison-panel-title" ref={headingRef} tabIndex="-1">경쟁사 비교</h2>
          <p>선택 기업 {companies.length}개를 검증 데이터 기준으로 비교합니다.</p>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="비교 패널 닫기">×</button>
      </div>
      <div className="comparison-table-wrap">
        <table className="comparison-table">
          <thead>
            <tr>
              <th scope="row">지표</th>
              {rows.map(({ company }) => (
                <th key={company.company_id} scope="col"><Link to={`/companies/${company.company_id}`}>{company.company_name}</Link></th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr><th scope="row">기업 유형</th>{rows.map(({ metric }) => <td key={metric.company_id}>{metric.typeLabel}</td>)}</tr>
            <tr><th scope="row">경쟁 관계</th>{rows.map(({ metric }) => <td key={metric.company_id}>{metric.relationshipLabel}</td>)}</tr>
            <tr><th scope="row">최근 재무연도</th>{rows.map(({ metric }) => <td key={metric.company_id}>{metric.latestFinancialYear || "확인되지 않음"}</td>)}</tr>
            <tr><th scope="row">최근 매출액</th>{rows.map(({ metric }) => <td key={metric.company_id}>{metric.revenue === null ? "확인되지 않음" : formatKrw(metric.revenue)}</td>)}</tr>
            <tr><th scope="row">영업이익</th>{rows.map(({ metric }) => <td key={metric.company_id}>{metric.operatingProfit === null ? "확인되지 않음" : formatKrw(metric.operatingProfit)}</td>)}</tr>
            <tr><th scope="row">영업이익률</th>{rows.map(({ metric }) => <td key={metric.company_id}>{formatMargin(metric.operatingMargin)}</td>)}</tr>
            <tr><th scope="row">생산시설</th>{rows.map(({ metric }) => <td key={metric.company_id}>{facilityText(metric)}</td>)}</tr>
            <tr><th scope="row">검증 프로젝트</th>{rows.map(({ metric }) => <td key={metric.company_id}>{projectText(metric)}</td>)}</tr>
            <tr><th scope="row">기술·특허</th>{rows.map(({ metric }) => <td key={metric.company_id}>{formatNumber(metric.technologyCount, "건")}</td>)}</tr>
            <tr><th scope="row">주요 목표 시장</th>{rows.map(({ metric }) => <td key={metric.company_id}>{joinLabels(metric.targetMarkets)}</td>)}</tr>
            <tr><th scope="row">모듈러 공법</th>{rows.map(({ metric }) => <td key={metric.company_id}>{joinLabels(metric.modularMethods)}</td>)}</tr>
            <tr><th scope="row">데이터 상태</th>{rows.map(({ metric }) => <td key={metric.company_id}>{metric.dataStatusLabel} · {metric.comparisonStatus}</td>)}</tr>
          </tbody>
        </table>
      </div>
      <p className="finance-note">후보, MOU, Pre-Con, R&D, 전시는 검증 프로젝트 실적 수에 합산하지 않습니다. 미확인 값은 0으로 대체하지 않습니다.</p>
      <input type="hidden" aria-hidden="true" value={serializeCompareSelection(companies.map((company) => company.company_id))} readOnly />
    </section>
  );
}
