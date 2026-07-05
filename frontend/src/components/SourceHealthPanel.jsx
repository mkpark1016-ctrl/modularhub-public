import { getSourceHealth } from "../businessInsights";

const STATUS_LABELS = {
  ok: "정상",
  warning: "경고",
  stopped: "중지",
  not_collected: "미수집",
  empty: "현재 공고 없음",
};

export default function SourceHealthPanel({ meta }) {
  const sources = getSourceHealth(meta || {});
  return (
    <section className="dashboard-section">
      <div className="section-heading">
        <h2>수집원 상태</h2>
        <p>마지막 갱신 {meta?.last_updated_at || meta?.generated_at || "-"}</p>
      </div>
      <div className="source-health-grid">
        {sources.map((source) => (
          <div key={source.id} className="source-health-row">
            <strong>{source.name}</strong>
            <span className={`health-badge ${source.status}`}>{STATUS_LABELS[source.status] || source.status}</span>
            <p>{source.message || "-"}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
