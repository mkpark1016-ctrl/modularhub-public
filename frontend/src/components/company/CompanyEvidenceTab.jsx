import { ExternalLink } from "lucide-react";
import {
  detailModel,
  domainStatusRows,
  formatDate,
  labelValue,
} from "./companyDetailHelpers";

function sourceLabel(groupType) {
  return labelValue(groupType, "기타 공개자료");
}

export default function CompanyEvidenceTab({ company }) {
  const model = detailModel(company);
  const gaps = Array.isArray(company.research_gaps) ? company.research_gaps : [];

  return (
    <section className="summary company-tab-panel" id="company-tab-panel-evidence" role="tabpanel" aria-labelledby="company-tab-evidence">
      <h2>근거·출처</h2>
      <dl className="detail-grid compact-detail-grid">
        <div><dt>전체 데이터 상태</dt><dd>{model.header.dataStatusLabel}</dd></div>
        <div><dt>데이터 신뢰도</dt><dd>{model.header.confidenceLabel}</dd></div>
        <div><dt>최신 검증일</dt><dd>{formatDate(model.header.latestVerifiedAt)}</dd></div>
        <div><dt>DART corp_code</dt><dd>{company.dart_identity?.dart_corp_code || "확인되지 않음"}</dd></div>
        <div><dt>최근 감사보고서</dt><dd>{model.latestAudit?.receipt_number || "공개자료 없음"}</dd></div>
      </dl>

      <div className="company-subsection">
        <h3>영역별 검증 상태</h3>
        <div className="company-domain-grid">
          {domainStatusRows(company).map((row) => (
            <span key={row.label}>{row.label}<b>{row.value}</b></span>
          ))}
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
        <h3>출처</h3>
        {model.sourceGroups.length ? (
          <div className="source-group-list">
            {model.sourceGroups.map((group) => (
              <details className="source-group" key={group.group_type}>
                <summary>{sourceLabel(group.group_type)} · {group.count.toLocaleString("ko-KR")}건</summary>
                <div className="source-list">
                  {group.sources.map((source) => (
                    <div key={source.source_id}>
                      <strong>{source.title || source.publisher || sourceLabel(group.group_type)}</strong>
                      <span>{[source.publisher, source.published_at || source.retrieved_at, source.document_id ? `문서번호 ${source.document_id}` : null].filter(Boolean).join(" · ") || "기준일 확인 중"}</span>
                      {(source.url || source.source_url) && <a href={source.url || source.source_url} target="_blank" rel="noopener noreferrer">원문 보기 <ExternalLink size={13} /></a>}
                    </div>
                  ))}
                </div>
              </details>
            ))}
          </div>
        ) : (
          <p>공개 출처를 추가 정리 중입니다.</p>
        )}
      </div>
    </section>
  );
}
