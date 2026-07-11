export const OVERSEAS_RSS_SOURCE = "�ؿ� ��ⷯ RSS";

export function getNewsRegionType(item) {
  if (item?.publisher_region === "domestic" || item?.publisher_region === "overseas") {
    return item.publisher_region;
  }
  if (item?.publisher_region === "unknown") return "unknown";
  return item?.source === OVERSEAS_RSS_SOURCE ? "overseas" : "domestic";
}

export function newsRegionCounts(items) {
  const counts = {
    all: items.length,
    domestic: 0,
    overseas: 0,
    unknown: 0,
  };
  items.forEach((item) => {
    const region = getNewsRegionType(item);
    counts[region] = (counts[region] || 0) + 1;
  });
  return counts;
}

export function newsRegionMatches(item, region) {
  return region === "all" || getNewsRegionType(item) === region;
}

export function getNewsRegionLabel(item) {
  const region = getNewsRegionType(item);
  if (region === "overseas") return "해외뉴스";
  if (region === "domestic") return "국내뉴스";
  return "지역 미확인";
}

export function newsSortTime(item) {
  if (!item?.published_at) return null;
  const date = new Date(item.published_at);
  return Number.isNaN(date.getTime()) ? null : date.getTime();
}

function newsScore(item) {
  const score = Number(item?.relevance_score);
  return Number.isFinite(score) ? score : 0;
}

export function compareNewsItems(a, b) {
  const aTime = newsSortTime(a);
  const bTime = newsSortTime(b);
  if (aTime !== null && bTime !== null && aTime !== bTime) return bTime - aTime;
  if (aTime === null && bTime !== null) return 1;
  if (aTime !== null && bTime === null) return -1;

  const scoreDelta = newsScore(b) - newsScore(a);
  if (scoreDelta !== 0) return scoreDelta;

  return String(a?.title || "").localeCompare(String(b?.title || ""), "ko-KR");
}
