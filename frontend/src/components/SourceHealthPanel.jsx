import { useState } from "react";
import { getSourceHealth, getSourceHealthSummary, SOURCE_SEVERITY_LABELS } from "../sourceHealth";

export default function SourceHealthPanel({ meta }) {
  const [expanded, setExpanded] = useState(false);
  const sources = getSourceHealth(meta || {});
  const summary = getSourceHealthSummary(sources, meta || {});
  const workflow = summary.workflow;
  return (
    <section className="dashboard-section source-health-panel">
      <div className="section-heading compact-heading">
        <div>
          <h2>수집원 상태</h2>
          <p>마지막 갱신 {summary.lastUpdatedAt || "-"}</p>
        </div>
        <button
          type="button"
          className="text-button"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? "상세 닫기" : "상세 보기"}
        </button>
      </div>
      <div className="source-health-summary">
        <div><span>정상 수집원</span><strong>{summary.successCount}</strong></div>
        <div><span>일부 제한</span><strong>{summary.limitedCount}</strong></div>
        <div><span>미수집</span><strong>{summary.notCollectedCount}</strong></div>
        <div>
          <span>전체 Workflow</span>
          <strong className={`health-badge ${workflow?.severity || "warning"}`}>{workflow?.label || "확인 필요"}</strong>
        </div>
      </div>
      {workflow?.description && <p className="source-health-note">{workflow.description}</p>}
      {expanded && (
        <div className="source-health-grid">
          {sources.map((source) => (
            <div key={source.id} className="source-health-row">
              <strong>{source.name}</strong>
              <span className={`health-badge ${source.severity}`}>{source.label || SOURCE_SEVERITY_LABELS[source.severity]}</span>
              <p>{source.description || "-"}</p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
