export const REVIEW_QUEUE_SCHEMA_VERSION = "company-intelligence-review-queue.public.v1";

export const REVIEW_STATUS_LABELS = {
  pending: "검토 대기",
  duplicate: "중복",
  rejected: "제외",
  conflict: "충돌",
  accepted: "승인됨",
};

export const REVIEW_SOURCE_LABELS = {
  dart: "DART",
  opendart: "DART",
  naver: "NAVER",
  naver_search: "NAVER",
};

export const REVIEW_SORT_OPTIONS = [
  { value: "published_desc", label: "게시일 최신순" },
  { value: "published_asc", label: "게시일 오래된 순" },
  { value: "collected_desc", label: "수집일 최신순" },
  { value: "company", label: "기업명순" },
];

export const REVIEW_PAGE_SIZES = [20, 50, 100];
export const REVIEW_STALE_DAYS = 7;

const REQUIRED_ITEM_FIELDS = [
  "candidateId",
  "companyId",
  "companyName",
  "source",
  "status",
  "title",
  "originalUrl",
  "publishedAt",
  "collectedAt",
  "matchedKeyword",
  "matchedAlias",
  "matchReason",
  "duplicateType",
  "duplicateOf",
  "rejectionReason",
];

function normalizeText(value) {
  return String(value || "").trim().toLowerCase().replace(/\s+/g, " ");
}

function timeValue(value) {
  const time = Date.parse(value || "");
  return Number.isFinite(time) ? time : null;
}

export function getReviewStatusLabel(status) {
  return REVIEW_STATUS_LABELS[status] || "미확인";
}

export function getReviewSourceLabel(source) {
  return REVIEW_SOURCE_LABELS[source] || source || "출처 미확인";
}

export function isValidHttpUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

export function formatReviewDate(value) {
  if (!value) return "확인되지 않음";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 10);
  return new Intl.DateTimeFormat("ko-KR", { year: "numeric", month: "2-digit", day: "2-digit" }).format(date);
}

export function validateReviewQueuePayload(payload, manifest = null) {
  if (!payload || typeof payload !== "object") return { valid: false, reason: "payload_missing" };
  if (payload.schemaVersion !== REVIEW_QUEUE_SCHEMA_VERSION) return { valid: false, reason: "schema_version_mismatch" };
  if (!Array.isArray(payload.items)) return { valid: false, reason: "items_missing" };
  for (const item of payload.items) {
    const missing = REQUIRED_ITEM_FIELDS.filter((field) => !(field in item));
    if (missing.length) return { valid: false, reason: "required_field_missing", missing, candidateId: item.candidateId };
  }
  if (manifest && Number.isFinite(Number(manifest.itemCount)) && Number(manifest.itemCount) !== payload.items.length) {
    return { valid: false, reason: "manifest_item_count_mismatch" };
  }
  return { valid: true, reason: "" };
}

export function normalizeReviewQueuePayload(payload, manifest = null) {
  const validation = validateReviewQueuePayload(payload, manifest);
  if (!validation.valid) {
    return { valid: false, reason: validation.reason, items: [], manifest: null };
  }
  const items = payload.items.map((item) => ({
    candidateId: String(item.candidateId || ""),
    companyId: String(item.companyId || ""),
    companyName: String(item.companyName || item.companyId || ""),
    source: String(item.source || ""),
    status: String(item.status || "pending"),
    title: String(item.title || ""),
    originalUrl: String(item.originalUrl || ""),
    publishedAt: String(item.publishedAt || ""),
    collectedAt: String(item.collectedAt || ""),
    matchedKeyword: String(item.matchedKeyword || ""),
    matchedAlias: String(item.matchedAlias || ""),
    matchReason: String(item.matchReason || ""),
    duplicateType: String(item.duplicateType || ""),
    duplicateOf: String(item.duplicateOf || ""),
    rejectionReason: String(item.rejectionReason || ""),
  }));
  return {
    valid: true,
    reason: "",
    items,
    manifest: manifest || {
      schemaVersion: payload.schemaVersion,
      generatedAt: payload.generatedAt || "",
      counts: { pending: items.filter((item) => item.status === "pending").length },
      itemCount: items.length,
      companies: [],
      sources: [],
    },
  };
}

export function getReviewQueueMetadata(manifest = {}) {
  return {
    generatedAt: manifest?.generatedAt || "",
    sourceRunId: manifest?.sourceRunId || "",
    sourceCommit: manifest?.sourceCommit || manifest?.sourceRunCommit || "",
    sourceWorkflow: manifest?.sourceWorkflow || "",
    sourceBranch: manifest?.sourceBranch || "",
    lookbackDays: Number(manifest?.lookbackDays || 0),
  };
}

export function isReviewQueueStale(generatedAt, now = new Date(), staleDays = REVIEW_STALE_DAYS) {
  const generated = Date.parse(generatedAt || "");
  const current = now instanceof Date ? now.getTime() : Date.parse(now || "");
  if (!Number.isFinite(generated) || !Number.isFinite(current)) return false;
  return current - generated > staleDays * 24 * 60 * 60 * 1000;
}

export function getReviewQueueKpis(items, manifest) {
  const counts = manifest?.counts || {};
  const statusCounts = items.reduce((acc, item) => {
    acc[item.status] = (acc[item.status] || 0) + 1;
    return acc;
  }, {});
  return {
    total: Number(counts.normalizedUniqueCandidates ?? counts.rawCandidateRecords ?? items.length),
    pending: Number(counts.pending ?? statusCounts.pending ?? 0),
    duplicate: Number(counts.duplicate ?? statusCounts.duplicate ?? 0),
    qualityRejected: Number(counts.qualityRejected ?? counts.rawRejectedRecords ?? 0),
    generatedAt: manifest?.generatedAt || "",
    sourceCounts: counts.sourceCounts || {},
  };
}

export function getReviewFilterOptions(items, manifest) {
  const companies = new Map();
  for (const company of manifest?.companies || []) {
    companies.set(company.companyId, company.companyName || company.companyId);
  }
  for (const item of items) {
    companies.set(item.companyId, item.companyName || item.companyId);
  }
  const sources = new Set([...(manifest?.sources || []), ...items.map((item) => item.source)]);
  return {
    companies: [...companies.entries()].map(([value, label]) => ({ value, label })).sort((a, b) => a.label.localeCompare(b.label, "ko-KR")),
    sources: [...sources].filter(Boolean).map((source) => ({ value: source, label: getReviewSourceLabel(source) })).sort((a, b) => a.label.localeCompare(b.label, "ko-KR")),
  };
}

export function filterReviewItems(items, filters) {
  const query = normalizeText(filters.query);
  const start = filters.startDate ? timeValue(filters.startDate) : null;
  const end = filters.endDate ? timeValue(`${filters.endDate}T23:59:59`) : null;
  return items.filter((item) => {
    if (filters.company && item.companyId !== filters.company) return false;
    if (filters.source && item.source !== filters.source) return false;
    if (filters.status && item.status !== filters.status) return false;
    const published = timeValue(item.publishedAt);
    if (start !== null && (published === null || published < start)) return false;
    if (end !== null && (published === null || published > end)) return false;
    if (query) {
      const haystack = normalizeText([item.title, item.companyName, item.matchedKeyword, item.matchedAlias].join(" "));
      if (!haystack.includes(query)) return false;
    }
    return true;
  });
}

export function sortReviewItems(items, sortValue = "published_desc") {
  return [...items].sort((a, b) => {
    if (sortValue === "company") {
      return a.companyName.localeCompare(b.companyName, "ko-KR") || a.title.localeCompare(b.title, "ko-KR");
    }
    const field = sortValue === "collected_desc" ? "collectedAt" : "publishedAt";
    const left = timeValue(a[field]);
    const right = timeValue(b[field]);
    if (left === null && right === null) return a.companyName.localeCompare(b.companyName, "ko-KR");
    if (left === null) return 1;
    if (right === null) return -1;
    return sortValue === "published_asc" ? left - right : right - left;
  });
}

export function paginateReviewItems(items, page = 1, pageSize = 20) {
  const safePageSize = REVIEW_PAGE_SIZES.includes(Number(pageSize)) ? Number(pageSize) : 20;
  const pageCount = Math.max(1, Math.ceil(items.length / safePageSize));
  const currentPage = Math.min(Math.max(1, Number(page) || 1), pageCount);
  const start = (currentPage - 1) * safePageSize;
  return {
    page: currentPage,
    pageSize: safePageSize,
    pageCount,
    items: items.slice(start, start + safePageSize),
  };
}
