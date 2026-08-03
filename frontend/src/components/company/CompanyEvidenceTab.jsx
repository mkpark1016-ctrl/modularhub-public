import { ExternalLink } from "lucide-react";
import {
  detailModel,
  domainStatusRows,
  formatDate,
  formatNumber,
  labelValue,
} from "./companyDetailHelpers";
import { buildSourceRows, sourceHasPublicUrl, sourceTypeSummaryForDomain } from "../../companyEvidence";
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

function DataTrustCenter({ reportInsight, matrixRows }) {
  const financialRows = Array.isArray(reportInsight?.evidence_health) ? reportInsight.evidence_health : [];
  const rows = [
    ...financialRows.map((row) => ({
      key: row.domain,
      label: evidenceDomainLabel(row.domain),
      status: verificationStatusLabel(row.verification_status),
      sourceCount: row.source_count,
      verifiedCount: row.verified_item_count,
      pendingCount: row.pending_item_count,
      unavailableCount: row.unavailable_item_count,
      latest: row.latest_verified_at,
    })),
    ...matrixRows
      .filter((row) => row.key !== "financial")
      .map((row) => ({
        key: row.key,
        label: row.label,
        status: row.status,
        sourceCount: row.sourceTypes === "출처 없음" ? 0 : row.sourceTypes.split(",").length,
        verifiedCount: row.status === "검증 완료" ? 1 : 0,
        pendingCount: row.gapSummary === "보완 공백 없음" ? 0 : 1,
        unavailableCount: 0,
        latest: row.verifiedAt,
      })),
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
              <div><dt>미공시</dt><dd>{formatNumber(row.unavailableCount, "건")}</dd></div>
            </dl>
            <small>최신 기준 {formatDate(row.latest)}</small>
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
        <div><dt>전체 데이터 상태</dt><dd>{model.header.dataStatusLabel}</dd></div>
        <div><dt>데이터 신뢰도</dt><dd>{model.header.confidenceLabel}</dd></div>
        <div><dt>최신 검증일</dt><dd>{formatDate(model.header.latestVerifiedAt)}</dd></div>
        <div><dt>DART corp_code</dt><dd>{company.dart_identity?.dart_corp_code || "확인되지 않음"}</dd></div>
        <div><dt>최근 감사보고서</dt><dd>{model.latestAudit?.receipt_number || "공개자료 없음"}</dd></div>
        <div><dt>데이터 공백</dt><dd>{formatNumber(gapRows.length, "건")}</dd></div>
      </dl>

      <DataTrustCenter reportInsight={reportInsight} matrixRows={matrixRows} />

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
    </section>
  );
}
