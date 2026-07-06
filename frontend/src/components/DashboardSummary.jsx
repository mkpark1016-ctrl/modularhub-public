import { Link } from "react-router-dom";
import { getNewsRelevance, getNewsRelevanceLabel, selectHomeBriefingNews } from "../newsInsights";
import { getNewsRegionType } from "../newsRegion";
import FavoriteButton from "./FavoriteButton";

function Kpi({ label, value }) {
  return (
    <div className="kpi-tile">
      <span>{label}</span>
      <strong>{Number(value || 0).toLocaleString("ko-KR")}</strong>
    </div>
  );
}

export default function DashboardSummary({
  summary,
  newsItems,
  formatDate,
  isNewsFavorite,
  onToggleNewsFavorite,
}) {
  const latestNews = selectHomeBriefingNews(newsItems, 5);
  const directCount = latestNews.filter((item) => getNewsRelevance(item) === "direct").length;
  const adjacentCount = latestNews.filter((item) => getNewsRelevance(item) === "adjacent").length;
  return (
    <>
      <section className="dashboard-section">
        <div className="section-heading">
          <h2>오늘의 영업 브리핑</h2>
          <p>공개 데이터 기준으로 매일 확인할 항목을 정리했습니다.</p>
        </div>
        <div className="kpi-grid">
          <Kpi label="진행 중 사업" value={summary.active} />
          <Kpi label="마감 7일 이내" value={summary.dueWithin7} />
          <Kpi label="최근 7일 신규 사업" value={summary.recentlyPosted7} />
          <Kpi label="중요공고" value={summary.important} />
          <Kpi label="최근 7일 직접 관련 뉴스" value={summary.recentDirect7} />
        </div>
        <p className="kpi-helper">최근 7일 전체 뉴스 {Number(summary.recentNews7 || 0).toLocaleString("ko-KR")}건 · 연관 산업 {Number(summary.recentAdjacent7 || 0).toLocaleString("ko-KR")}건</p>
      </section>

      <section className="dashboard-section">
        <div className="section-heading">
          <h2>최신 시장 뉴스</h2>
          <Link to="/news?relevance=direct&sort=newest">직접 관련 뉴스 보기</Link>
        </div>
        <p className="brief-helper">직접 관련 {directCount}건을 우선 표시하고, 부족한 경우 연관 산업 {adjacentCount}건으로 보충합니다.</p>
        <div className="news-brief-list">
          {latestNews.map((item) => (
            <article key={item.id} className="news-brief-item">
              <div>
                <div className="badge-row">
                  <span>{getNewsRegionType(item) === "overseas" ? "해외뉴스" : "국내뉴스"}</span>
                  <span className={`relevance-badge ${getNewsRelevance(item)}`}>{getNewsRelevanceLabel(item)}</span>
                  <span>{item.topic || "기타"}</span>
                  <span>{item.media || item.source || "출처 미확인"}</span>
                </div>
                <h3><Link to={`/news/${item.id}`}>{item.title}</Link></h3>
                <p>{formatDate(item.published_at)}</p>
              </div>
              <div className="priority-actions">
                <FavoriteButton active={isNewsFavorite(item.id)} onClick={() => onToggleNewsFavorite(item.id)} label="관심 뉴스" />
                <Link className="text-button" to={`/news/${item.id}`}>상세보기</Link>
              </div>
            </article>
          ))}
        </div>
      </section>
    </>
  );
}
