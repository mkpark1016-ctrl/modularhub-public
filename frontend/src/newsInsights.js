export const NEWS_TOPICS = [
  "전체 주제",
  "정책·제도",
  "시장·투자",
  "기업·공장",
  "프로젝트·수주",
  "기술·제품",
  "주거·주택",
  "교육·학교",
  "데이터센터",
  "기타",
];

const TOPIC_KEYWORDS = {
  "정책·제도": ["policy", "regulation", "law", "government", "council", "permit", "planning", "zoning", "정책", "제도", "정부", "규제"],
  "시장·투자": ["market", "investment", "investor", "funding", "finance", "growth", "demand", "sales", "시장", "투자", "수요"],
  "기업·공장": ["company", "factory", "plant", "manufacturer", "manufacturing", "facility", "business", "acquisition", "기업", "공장", "제조"],
  "프로젝트·수주": ["project", "contract", "award", "wins", "deliver", "development", "construction starts", "site", "프로젝트", "수주", "착공"],
  "기술·제품": ["technology", "product", "system", "module", "volumetric", "DfMA", "MMC", "innovation", "기술", "제품"],
  "주거·주택": ["housing", "home", "homes", "residential", "apartment", "affordable", "주택", "주거", "아파트"],
  "교육·학교": ["school", "campus", "classroom", "education", "student", "university", "학교", "교육", "캠퍼스"],
  "데이터센터": ["data center", "datacentre", "data centre", "server", "데이터센터"],
};

export function normalizeNewsText(value) {
  return String(value || "").toLowerCase().replace(/\s+/g, " ").trim();
}

export function newsSearchText(item) {
  const keywords = Array.isArray(item?.keywords) ? item.keywords.join(" ") : item?.keywords;
  return normalizeNewsText([item?.title, item?.summary, item?.media, item?.source, keywords].filter(Boolean).join(" "));
}

export function getNewsTopic(item) {
  const text = newsSearchText(item);
  for (const [topic, keywords] of Object.entries(TOPIC_KEYWORDS)) {
    if (keywords.some((keyword) => text.includes(normalizeNewsText(keyword)))) return topic;
  }
  return "기타";
}

export function parseSearchQuery(query) {
  const text = String(query || "").trim();
  if (!text) return { phrases: [], terms: [] };
  const phrases = [];
  const withoutPhrases = text.replace(/"([^"]+)"/g, (_, phrase) => {
    const normalized = normalizeNewsText(phrase);
    if (normalized) phrases.push(normalized);
    return " ";
  });
  const terms = withoutPhrases.split(/\s+/).map(normalizeNewsText).filter(Boolean);
  return { phrases, terms };
}

export function matchesNewsSearch(item, query) {
  const { phrases, terms } = parseSearchQuery(query);
  if (!phrases.length && !terms.length) return true;
  const text = newsSearchText(item);
  return phrases.every((phrase) => text.includes(phrase)) && terms.every((term) => text.includes(term));
}

export function newsScore(item) {
  const score = Number(item?.relevance_score);
  return Number.isFinite(score) ? score : 0;
}

export function newsTime(item) {
  if (!item?.published_at) return null;
  const date = new Date(item.published_at);
  return Number.isNaN(date.getTime()) ? null : date.getTime();
}

export function compareNewsBySort(a, b, sort = "newest") {
  if (sort === "relevance") {
    const scoreDelta = newsScore(b) - newsScore(a);
    if (scoreDelta !== 0) return scoreDelta;
  }
  const aTime = newsTime(a);
  const bTime = newsTime(b);
  if (aTime !== null && bTime !== null && aTime !== bTime) {
    return sort === "oldest" ? aTime - bTime : bTime - aTime;
  }
  if (aTime !== null && bTime === null) return -1;
  if (aTime === null && bTime !== null) return 1;
  if (sort !== "relevance") {
    const scoreDelta = newsScore(b) - newsScore(a);
    if (scoreDelta !== 0) return scoreDelta;
  }
  return String(a?.title || "").localeCompare(String(b?.title || ""), "ko-KR");
}

export function getNewsSummary(items, now = new Date()) {
  const threshold = new Date(now);
  threshold.setDate(threshold.getDate() - 7);
  const recent7 = items.filter((item) => {
    const time = newsTime(item);
    return time !== null && time >= threshold.getTime();
  }).length;
  return { total: items.length, recent7 };
}
