export const OVERSEAS_RSS_SOURCE = "해외 모듈러 RSS";

function textValue(value) {
  return String(value || "").trim();
}

function combinedSourceText(item) {
  return [item?.collection_source, item?.source, item?.source_name].map(textValue).filter(Boolean).join(" ").toLowerCase();
}

function sourceSuggestsDomestic(item) {
  const text = combinedSourceText(item);
  return text.includes("국내") || text.includes("네이버") || text.includes("naver");
}

function sourceSuggestsOverseas(item) {
  const text = combinedSourceText(item);
  return text.includes("해외") || text.includes("rss") || text.includes("overseas");
}

export function getNewsPublisherLabel(item) {
  return (
    textValue(item?.publisher_name) ||
    textValue(item?.media) ||
    textValue(item?.source_name) ||
    textValue(item?.source) ||
    "출처 미확인"
  );
}

export function getNewsPublisherDomain(item) {
  const domain = textValue(item?.publisher_domain);
  return domain && domain !== "news.google.com" ? domain : "";
}

export function getNewsCollectionLabel(item) {
  if (item?.collection_pipeline === "rss_overseas_pipeline") return "해외 RSS 수집";
  if (item?.collection_pipeline === "domestic_pipeline") return "국내 뉴스 검색 수집";
  if (textValue(item?.collection_source)) return `${item.collection_source} 수집`;
  return "";
}

export function getNewsDisplayRegionReason(item) {
  if (item?.publisher_region === "domestic" || item?.publisher_region === "overseas") {
    return { region: item.publisher_region, reason: "publisher_region" };
  }
  if (item?.collection_pipeline === "domestic_pipeline") {
    return { region: "domestic", reason: "collection_pipeline" };
  }
  if (item?.collection_pipeline === "rss_overseas_pipeline") {
    return { region: "overseas", reason: "collection_pipeline" };
  }
  if (sourceSuggestsDomestic(item)) return { region: "domestic", reason: "collection_source" };
  if (sourceSuggestsOverseas(item)) return { region: "overseas", reason: "collection_source" };
  return { region: "domestic", reason: "fallback_default_domestic" };
}

export function getNewsDisplayRegion(item) {
  return getNewsDisplayRegionReason(item).region;
}

export function getNewsRegionType(item) {
  return getNewsDisplayRegion(item);
}

export function newsDisplayRegionCounts(items) {
  const counts = {
    all: items.length,
    domestic: 0,
    overseas: 0,
  };
  items.forEach((item) => {
    const region = getNewsDisplayRegion(item);
    counts[region] += 1;
  });
  return counts;
}

export function newsDisplayRegionDiagnostics(items) {
  const diagnostics = {
    publisher_region: 0,
    collection_pipeline: 0,
    collection_source: 0,
    fallback_default_domestic: 0,
  };
  items.forEach((item) => {
    const { reason } = getNewsDisplayRegionReason(item);
    diagnostics[reason] = (diagnostics[reason] || 0) + 1;
  });
  return diagnostics;
}

export function newsRegionCounts(items) {
  return newsDisplayRegionCounts(items);
}

export function newsDisplayRegionMatches(item, region) {
  return region === "all" || getNewsDisplayRegion(item) === region;
}

export function newsRegionMatches(item, region) {
  return newsDisplayRegionMatches(item, region);
}

export function getNewsDisplayRegionLabel(item) {
  return getNewsDisplayRegion(item) === "overseas" ? "해외" : "국내";
}

export function getNewsRegionLabel(item) {
  return getNewsDisplayRegionLabel(item);
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
