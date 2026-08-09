import { ExternalLink } from "lucide-react";
import {
  detailModel,
  domainStatusRows,
  formatDate,
  formatNumber,
  labelValue,
} from "./companyDetailHelpers";
import {
  buildSourceRows,
  distinctSourceRows,
  reportSourcesByIds,
  sourceHasPublicUrl,
  sourceSummaryForDomain,
  sourceTypeSummaryForDomain,
  sourcesForDomain,
} from "../../companyEvidence";
import {
  evidenceDomainLabel,
  sourceSectionCounts,
  verificationStatusLabel,
} from "../../companyReportInsights";
import { companyDataGapRows, dataGapSummaryForDomain } from "../../companyDataGaps";

const MATRIX_AREAS = [
  { key: "identity", label: "법인정보", tab: "overview" },
  { key: "financial", label: "재무", tab: "financial" },
  { key: "production", label: "생산시설", tab: "production" },
  { key: "project", label: "프로젝트", tab: "projects" },
  { key: "technology", label: "기술·특허", tab: "technology" },
  { key: "recent_signal", label: "최근 활동", tab: "overview" },
];

function sourceTypeCountLabel(counts = {}) {
  const entries = Object.entries(counts).filter(([, count]) => Number(count) > 0);
  return entries.length ? entries.map(([label, count]) => `${label} ${count}`).join(" · ") : "출처 유형 없음";
}

function latestSourceDate(rows, fallback) {
  const dates = rows
    .map((row) => row.publishedAt)
    .filter(Boolean)
    .sort((a, b) => String(b).localeCompare(String(a)));
  return dates[0] || fallback || "";
}

function countPresent(values) {
  return values.filter((value) => (
    value !== null
    && value !== undefined
    && value !== ""
    && !(Array.isArray(value) && value.length === 0)
  )).length;
}

function nonFinancialTrustRows({ company, model, gapRows, sourceRows }) {
  const profile = company.company_profile || {};
  const gapsFor = (domain) => gapRows.filter((row) => row.domain === domain).length;
  const productionItems = Array.isArray(company.production) ? company.production : [];
  const projectSummary = model.projectSummary || {};
  const technologyItems = model.technologyItems || [];
  const recentSignals = [
    ...(Array.isArray(company.recent_signals) ? company.recent_signals : []),
    ...(Array.isArray(model.events) ? model.events : []),
  ];
  const rows = [
    {
      domain: "identity",
      verified_item_count: countPresent([
        company.company_name,
        company.legal_name,
        profile.representative,
        profile.established_at,
        company.headquarters,
        company.website_url,
        company.dart_identity?.dart_corp_code,
      ]),
      pending_item_count: gapsFor("identity"),
    },
    {
      domain: "production",
      verified_item_count: productionItems.filter((item) => Array.isArray(item.source_ids) && item.source_ids.length > 0).length,
      pending_item_count: gapsFor("production"),
    },
    {
      domain: "project",
      verified_item_count: Number(projectSummary.verified || 0),
      pending_item_count: Number(projectSummary.candidates || 0) + gapsFor("project"),
    },
    {
      domain: "technology",
      verified_item_count: technologyItems.filter((item) => Array.isArray(item.source_ids) && item.source_ids.length > 0).length,
      pending_item_count: gapsFor("technology"),
    },
    {
      domain: "recent_signal",
      verified_item_count: recentSignals.filter((item) => Array.isArray(item.source_ids) && item.source_ids.length > 0).length,
      pending_item_count: gapsFor("recent_signal"),
    },
  ];

  return rows.map((row) => {
    const domainSources = sourcesForDomain(sourceRows, row.domain);
    const summary = sourceSummaryForDomain(sourceRows, row.domain);
    const status = row.pending_item_count > 0
      ? "검증 보류 포함"
      : row.verified_item_count > 0
        ? "검증 완료"
        : summary.sourceCount > 0
          ? "자료 확인 중"
          : "확인되지 않음";
    return {
      key: row.domain,
      domain: row.domain,
      label: evidenceDomainLabel(row.domain),
      status,
      sourceCount: summary.sourceCount,
      verifiedCount: row.verified_item_count,
      pendingCount: row.pending_item_count,
      notDisclosedCount: 0,
      notApplicableCount: 0,
      verificationPendingCount: row.pending_item_count,
      latest: latestSourceDate(domainSources, model.header.latestVerifiedAt),
      sourceTypeCounts: summary.sourceTypeCounts,
      sources: distinctSourceRows(domainSources),
    };
  });
}

function trustEvidencePayload(row) {
  return {
    title: `${row.label} Data Trust`,
    value: row.status,
    note: "고유 출처 수와 항목 상태를 실제 데이터 기준으로 집계한 읽기 전용 근거입니다.",
    details: [
      ["영역", row.label],
      ["실제 출처 수", formatNumber(row.sourceCount, "개")],
      ["검증 항목", formatNumber(row.verifiedCount, "건")],
      ["보류 항목", formatNumber(row.pendingCount, "건")],
      ["미공시 항목", formatNumber(row.notDisclosedCount, "건")],
      ["해당 없음 항목", formatNumber(row.notApplicableCount, "건")],
      ["검증 보류 항목", formatNumber(row.verificationPendingCount, "건")],
      ["출처 유형", sourceTypeCountLabel(row.sourceTypeCounts)],
      ["최신 기준", formatDate(row.latest)],
    ],
    sources: row.sources,
  };
}

function DataTrustCenter({ company, model, reportInsight, gapRows, sourceRows, onShowEvidence }) {
  const financialRows = Array.isArray(reportInsight?.evidence_health) ? reportInsight.evidence_health : [];
  const rows = [
    ...financialRows.map((row) => ({
      key: row.domain,
      domain: row.domain,
      label: evidenceDomainLabel(row.domain),
      status: verificationStatusLabel(row.verification_status),
      sourceCount: row.distinct_source_count ?? row.source_count ?? 0,
      verifiedCount: row.verified_item_count ?? 0,
      pendingCount: row.pending_item_count ?? 0,
      notDisclosedCount: row.not_disclosed_item_count ?? row.unavailable_item_count ?? 0,
      notApplicableCount: row.not_applicable_item_count ?? 0,
      verificationPendingCount: row.verification_pending_item_count ?? 0,
      latest: row.latest_verified_at,
      sourceTypeCounts: row.source_type_counts || {},
      sources: reportSourcesByIds(reportInsight, row.source_ids),
    })),
    ...nonFinancialTrustRows({ company, model, gapRows, sourceRows }),
  ];

  return (
    <div className="company-subsection">
      <div className="company-subsection-heading">
        <h3>Data Trust Center</h3>
        <span>공개 화면의 판단 근거와 공백을 영역별로 구분합니다.</span>
      </div>
      <div className="company-trust-grid" aria-label="데이터 신뢰도 센터">
        {rows.map((row) => (
          <article className="company-trust-card" key={row.key}>
            <span>{row.label}</span>
            <strong>{row.status}</strong>
            <dl>
              <div><dt>출처</dt><dd>{formatNumber(row.sourceCount, "개")}</dd></div>
              <div><dt>검증</dt><dd>{formatNumber(row.verifiedCount, "건")}</dd></div>
              <div><dt>보류</dt><dd>{formatNumber(row.pendingCount, "건")}</dd></div>
              <div><dt>미공시</dt><dd>{formatNumber(row.notDisclosedCount, "건")}</dd></div>
              <div><dt>해당 없음</dt><dd>{formatNumber(row.notApplicableCount, "건")}</dd></div>
              <div><dt>검증 보류</dt><dd>{formatNumber(row.verificationPendingCount, "건")}</dd></div>
            </dl>
            <small>출처 유형 {sourceTypeCountLabel(row.sourceTypeCounts)}</small>
            <small>최신 기준 {formatDate(row.latest)}</small>
            {onShowEvidence && (
              <button
                type="button"
                className="text-button evidence-inline-button"
                onClick={() => onShowEvidence(trustEvidencePayload(row))}
              >
                상세 근거 보기
              </button>
            )}
          </article>
        ))}
      </div>
    </div>
  );
}

export default function CompanyEvidenceTab({ company, reportInsight = null, onShowEvidence, onTabChange }) {
  const model = detailModel(company);
  const gaps = Array.isArray(company.research_gaps) ? company.research_gaps : [];
  const gapRows = companyDataGapRows(company, reportInsight);
  const sourceRows = buildSourceRows(company, reportInsight);
  const sectionRows = reportInsight ? sourceSectionCounts(reportInsight).filter((item) => item.count > 0) : [];
  const matrixRows = domainStatusRows(company).map((row, index) => ({
    ...MATRIX_AREAS[index],
    status: row.value,
    sourceTypes: sourceTypeSummaryForDomain(sourceRows, MATRIX_AREAS[index]?.key),
    verifiedAt: model.header.latestVerifiedAt,
    gapSummary: dataGapSummaryForDomain(gapRows, MATRIX_AREAS[index]?.key),
  }));

  return (
    <section className="summary company-tab-panel" id="company-tab-panel-evidence" role="tabpanel" aria-labelledby="company-tab-evidence">
      <h2>근거·출처</h2>
      <dl className="detail-grid compact-detail-grid">
        <div><dt>데이터 신뢰도</dt><dd>{model.header.confidenceLabel} · {model.header.dataStatusLabel}</dd></div>
        <div><dt>최신 검증일</dt><dd>{formatDate(model.header.latestVerifiedAt)}</dd></div>
        <div><dt>최근 감사보고서</dt><dd>{model.latestAudit?.receipt_number || "공개자료 없음"}</dd></div>
        <div><dt>데이터 공백</dt><dd>{formatNumber(gapRows.length, "건")}</dd></div>
      </dl>

      <DataTrustCenter
        company={company}
        model={model}
        reportInsight={reportInsight}
        gapRows={gapRows}
        sourceRows={sourceRows}
        onShowEvidence={onShowEvidence}
      />

      <details className="company-report-details evidence-secondary-details">
        <summary>영역별 검증 매트릭스와 출처 목록 보기</summary>

        <div className="company-subsection">
          <h3>식별 출처 메타</h3>
          <dl className="detail-grid compact-detail-grid">
            <div><dt>DART corp_code</dt><dd>{company.dart_identity?.dart_corp_code || "확인되지 않음"}</dd></div>
            <div><dt>최근 감사보고서 접수번호</dt><dd>{model.latestAudit?.receipt_number || "공개자료 없음"}</dd></div>
          </dl>
        </div>

        <div className="company-subsection">
          <h3>영역별 검증 매트릭스</h3>
          <div className="company-table-wrap evidence-matrix-wrap">
            <table className="company-financial-table evidence-matrix-table">
              <thead>
                <tr><th>영역</th><th>상태</th><th>주요 출처</th><th>최신 검증</th><th>보완 필요</th><th>이동</th></tr>
              </thead>
              <tbody>
                {matrixRows.map((row) => (
                  <tr key={row.key}>
                    <th>{row.label}</th>
                    <td>{row.status}</td>
                    <td>{row.sourceTypes}</td>
                    <td>{formatDate(row.verifiedAt)}</td>
                    <td>{row.gapSummary}</td>
                    <td><button type="button" className="text-button" onClick={() => onTabChange?.(row.tab)}>탭 열기</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {gaps.length > 0 && (
          <div className="company-subsection">
            <h3>추가 확인 필요 사항</h3>
            <div className="company-section-list">
              {gaps.map((gap, index) => (
                <div key={`${gap.area || "gap"}-${index}`}>
                  <strong>{gap.area ? labelValue(gap.area, gap.area) : "추가 확인 필요"}</strong>
                  <span>{gap.description || gap.note || "공개자료를 추가 확인 중입니다."}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="company-subsection">
          <h3>실제 출처 목록</h3>
          {sourceRows.length ? (
            <div className="source-list evidence-source-list">
              {sourceRows.map((source) => (
                <div key={source.id || source.title}>
                  <strong>{source.title}</strong>
                  <span>{[source.publisher, source.sourceType, formatDate(source.publishedAt), source.documentId ? `문서 ${source.documentId}` : null].filter(Boolean).join(" · ")}</span>
                  {source.supportedClaims?.length ? <span>연결 데이터 {formatNumber(source.supportedClaims.length, "개")}</span> : null}
                  <div className="evidence-source-actions">
                    {sourceHasPublicUrl(source) ? (
                      <a href={source.url} target="_blank" rel="noopener noreferrer">원문 보기 <ExternalLink size={13} /></a>
                    ) : (
                      <span className="disabled-link">원문 링크 없음</span>
                    )}
                    {onShowEvidence && (
                      <button type="button" className="text-button evidence-inline-button" onClick={() => onShowEvidence({ title: source.title, value: source.sourceType, note: source.note || "출처 상세", sources: [source] })}>
                        근거보기
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p>공개 출처를 추가 정리 중입니다.</p>
          )}
        </div>

        {sectionRows.length > 0 && (
          <div className="company-subsection">
            <h3>재무 출처 섹션</h3>
            <div className="company-report-section-tags">
              {sectionRows.map((row) => <span key={row.section}>{row.label} <small>{row.count}건</small></span>)}
            </div>
          </div>
        )}
      </details>
    </section>
  );
}
