import { findCompanySources } from "./companyEvidence.js";

export const TECHNOLOGY_FIELD_ORDER = [
  "구조·접합",
  "고층화",
  "시공성·안전",
  "외장·기밀",
  "공법·건설신기술",
  "기타",
];

export function normalizeTechnologyText(value) {
  return String(value || "").normalize("NFC").toLowerCase();
}

export function technologyField(item) {
  const text = normalizeTechnologyText([item?.name, item?.technology_area, item?.summary].join(" "));
  if (/(접합|체결|연결|커넥터|구조)/.test(text)) return "구조·접합";
  if (/(고층|적층|층간)/.test(text)) return "고층화";
  if (/(시공|안전|고소작업|공기)/.test(text)) return "시공성·안전";
  if (/(외장|기밀|수밀|단열)/.test(text)) return "외장·기밀";
  if (/(신기술|공법|인증)/.test(text)) return "공법·건설신기술";
  return "기타";
}

export function isPatentClassificationCode(value) {
  const text = String(value || "").trim();
  if (!text) return false;
  const tokens = text.split(/[|·,;]/).map((token) => token.trim()).filter(Boolean);
  return tokens.length > 0 && tokens.every((token) => /^[A-HY]\d{2}[A-Z](?:\s+\d+(?:\/\d+)?)?(?:\s+.*)?$/i.test(token));
}

export function formatPatentClassification(value) {
  return isPatentClassificationCode(value)
    ? String(value).split("|").map((token) => token.trim()).filter(Boolean).join(" · ")
    : String(value || "");
}

export function technologyPrimaryNumber(item) {
  if (item?.registration_number) return { label: "등록번호", value: item.registration_number };
  if (item?.application_number) return { label: "출원번호", value: item.application_number };
  if (item?.patent_number) return { label: "특허번호", value: item.patent_number };
  return { label: "번호", value: "번호 확인 중" };
}

export function isKiprisLinkedTechnology(item) {
  return (Array.isArray(item?.source_ids) ? item.source_ids : [])
    .some((sourceId) => String(sourceId).startsWith("official:kipris:"));
}

export function resolvedTechnologySources(company, item) {
  return findCompanySources(company, item?.source_ids);
}

export function technologyOverview(company, items) {
  const rows = Array.isArray(items) ? items : [];
  return {
    total: rows.length,
    registered: rows.filter((item) => item.status === "registered").length,
    kipris: rows.filter(isKiprisLinkedTechnology).length,
    evidenceLinked: rows.filter((item) => resolvedTechnologySources(company, item).length > 0).length,
  };
}

export function technologyFieldDistribution(items) {
  const counts = new Map();
  for (const item of Array.isArray(items) ? items : []) {
    const field = technologyField(item);
    counts.set(field, (counts.get(field) || 0) + 1);
  }
  return TECHNOLOGY_FIELD_ORDER
    .map((field) => ({ field, count: counts.get(field) || 0 }))
    .filter((entry) => entry.count > 0);
}

export function filterTechnologyItems(items, filters = {}) {
  const term = normalizeTechnologyText(filters.query);
  return (Array.isArray(items) ? items : []).filter((item) => {
    if (filters.recordType && filters.recordType !== "all" && (item.record_type || item.group) !== filters.recordType) return false;
    if (filters.status && filters.status !== "all" && item.status !== filters.status) return false;
    if (filters.field && filters.field !== "all" && technologyField(item) !== filters.field) return false;
    if (!term) return true;
    return normalizeTechnologyText([
      item.name,
      item.registration_number,
      item.application_number,
      item.patent_number,
      item.technology_area,
      item.summary,
    ].join(" ")).includes(term);
  });
}
