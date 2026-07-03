export const OVERSEAS_RSS_SOURCE = "해외 모듈러 RSS";

export function getNewsRegionType(item) {
  return item?.source === OVERSEAS_RSS_SOURCE ? "overseas" : "domestic";
}

export function newsRegionCounts(items) {
  const counts = {
    all: items.length,
    domestic: 0,
    overseas: 0,
  };
  items.forEach((item) => {
    counts[getNewsRegionType(item)] += 1;
  });
  return counts;
}

export function newsRegionMatches(item, region) {
  return region === "all" || getNewsRegionType(item) === region;
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
