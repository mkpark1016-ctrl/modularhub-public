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

export const NEWS_RELEVANCE_LEVELS = {
  direct: { label: "직접 관련", order: 0 },
  adjacent: { label: "연관 산업", order: 1 },
  reference: { label: "참고 정보", order: 2 },
  excluded: { label: "제외", order: 3 },
};

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

const DIRECT_PHRASES = [
  "모듈러 주택",
  "모듈러 건축",
  "모듈러 건설",
  "모듈러 공동주택",
  "modular construction",
  "modular housing",
  "modular building",
  "modular buildings",
  "prefabricated building",
  "prefabricated buildings",
  "prefab housing",
  "offsite construction",
  "off-site construction",
  "volumetric construction",
  "volumetric modular",
  "modern methods of construction",
  "factory-built housing",
];

const WEAK_MODULAR_TERMS = [
  "modular",
  "prefab",
  "prefabricated",
  "offsite",
  "off-site",
  "volumetric",
  "모듈러",
  "프리패브",
  "조립식",
];

const CONSTRUCTION_CONTEXT = [
  "construction",
  "building",
  "housing",
  "residential",
  "facility",
  "project",
  "development",
  "contractor",
  "factory",
  "manufacturing",
  "건축",
  "건설",
  "시공",
  "주택",
  "시설",
  "공사",
  "공급",
  "착공",
  "공장",
];

const ADJACENT_APPLICATION_TERMS = [
  "data center",
  "datacentre",
  "data centre",
  "dormitory",
  "school",
  "hotel",
  "hospital",
  "factory",
  "military facility",
  "apartment",
  "residential",
  "공동주택",
  "기숙사",
  "학교",
  "호텔",
  "병원",
  "공장",
  "군 시설",
  "데이터센터",
];

const REFERENCE_TERMS = [
  "construction policy",
  "construction technology",
  "smart construction",
  "robot construction",
  "ai construction",
  "건설 정책",
  "건설 기술",
  "스마트 건설",
  "스마트건설",
  "로봇 건설",
  "ai 건설",
  "건설산업",
  "전문건설",
  "데이터센터",
];

const EXCLUDED_CONTEXT = [
  "software module",
  "software component",
  "python module",
  "modular software",
  "open systems architecture",
  "modular open systems",
  "electronic module",
  "electronics module",
  "automotive module",
  "vehicle module",
  "modular synthesizer",
  "small modular reactor",
  "nuclear reactor",
  "일반 ai 제품",
  "홈 ai",
  "전자부품",
  "소프트웨어 모듈",
];

export function normalizeNewsText(value) {
  return String(value || "").toLowerCase().replace(/\s+/g, " ").trim();
}

export function newsSearchText(item) {
  const keywords = Array.isArray(item?.keywords) ? item.keywords.join(" ") : item?.keywords;
  return normalizeNewsText([
    item?.title,
    item?.summary,
    item?.media,
    item?.source,
    item?.source_name,
    item?.publisher_name,
    item?.publisher_domain,
    item?.collection_source,
    keywords,
  ].filter(Boolean).join(" "));
}

function newsRelevanceText(item) {
  return normalizeNewsText([item?.title, item?.summary, item?.media, item?.source].filter(Boolean).join(" "));
}

function newsTitleText(item) {
  return normalizeNewsText(item?.title);
}

function includesAny(text, terms) {
  return terms.some((term) => text.includes(normalizeNewsText(term)));
}

function hasStandaloneCode(text, code) {
  return new RegExp(`(^|[^a-z0-9])${code.toLowerCase()}([^a-z0-9]|$)`).test(text);
}

export function getNewsRelevance(item) {
  if (NEWS_RELEVANCE_LEVELS[item?.relevance_level]) return item.relevance_level;
  const text = newsRelevanceText(item);
  const title = newsTitleText(item);
  if (!text) return "excluded";
  if (includesAny(text, EXCLUDED_CONTEXT)) return "excluded";
  if (includesAny(text, DIRECT_PHRASES)) return "direct";
  if ((hasStandaloneCode(text, "mmc") || hasStandaloneCode(text, "dfma")) && includesAny(text, CONSTRUCTION_CONTEXT)) return "direct";
  if ((title.includes("데이터센터") || title.includes("data center")) && !includesAny(title, DIRECT_PHRASES)) return "reference";
  const hasWeakModular = includesAny(text, WEAK_MODULAR_TERMS);
  const hasConstructionContext = includesAny(text, CONSTRUCTION_CONTEXT);
  const hasApplication = includesAny(text, ADJACENT_APPLICATION_TERMS);
  if (hasWeakModular && hasConstructionContext && hasApplication) return "adjacent";
  if (includesAny(text, REFERENCE_TERMS) || hasConstructionContext) return "reference";
  return "excluded";
}

export function getNewsRelevanceLabel(itemOrLevel) {
  const level = typeof itemOrLevel === "string" ? itemOrLevel : getNewsRelevance(itemOrLevel);
  return NEWS_RELEVANCE_LEVELS[level]?.label || NEWS_RELEVANCE_LEVELS.excluded.label;
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
  if (!Number.isFinite(score)) return 0;
  return Math.max(0, Math.min(100, Math.round(score)));
}

export function newsTime(item) {
  if (!item?.published_at) return null;
  const date = new Date(item.published_at);
  return Number.isNaN(date.getTime()) ? null : date.getTime();
}

export function compareNewsBySort(a, b, sort = "newest") {
  if (sort === "relevance") {
    const aLevel = getNewsRelevance(a);
    const bLevel = getNewsRelevance(b);
    const levelDelta = (NEWS_RELEVANCE_LEVELS[aLevel]?.order ?? 9) - (NEWS_RELEVANCE_LEVELS[bLevel]?.order ?? 9);
    if (levelDelta !== 0) return levelDelta;
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
  const recentItems = items.filter((item) => {
    const time = newsTime(item);
    return time !== null && time >= threshold.getTime();
  });
  return {
    total: items.length,
    recent7: recentItems.length,
    recentDirect7: recentItems.filter((item) => getNewsRelevance(item) === "direct").length,
    recentAdjacent7: recentItems.filter((item) => getNewsRelevance(item) === "adjacent").length,
  };
}

function normalizedTitle(item) {
  return normalizeNewsText(item?.title).replace(/[^\p{Letter}\p{Number}\s]/gu, "").trim();
}

export function compareNewsByRelevance(a, b) {
  return compareNewsBySort(a, b, "relevance");
}

export function selectHomeBriefingNews(items, limit = 5) {
  const seen = new Set();
  return [...items]
    .filter((item) => ["direct", "adjacent"].includes(getNewsRelevance(item)))
    .sort(compareNewsByRelevance)
    .filter((item) => {
      const key = normalizedTitle(item);
      if (!key) return true;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, limit);
}
