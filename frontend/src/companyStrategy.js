export const COMPANY_STRATEGY_SCHEMA_VERSION = "company_strategy_v1";

const VALID_STRATEGIC_ROLES = new Set([
  "inherit",
  "direct_competitor",
  "substitute_competitor",
  "strategic_benchmark",
  "design_influencer",
  "internal_baseline",
  "watchlist",
]);

const VALID_BASES = new Set(["user_business_judgment", "canonical_fallback"]);
const VALID_PRIORITIES = new Set(["high", "medium", "low", null]);

function isIsoDate(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

export function getCompanyStrategyRecords(payload) {
  return Array.isArray(payload?.records) ? payload.records : [];
}

export function validateCompanyStrategyPayload(payload, companies = []) {
  const errors = [];
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return { valid: false, errors: ["strategy payload must be an object"] };
  }
  if (payload.schema_version !== COMPANY_STRATEGY_SCHEMA_VERSION) {
    errors.push(`unexpected schema_version: ${String(payload.schema_version || "")}`);
  }
  if (!isIsoDate(payload.as_of_date)) errors.push("as_of_date must be YYYY-MM-DD");

  const records = getCompanyStrategyRecords(payload);
  if (!Array.isArray(payload.records)) errors.push("records must be an array");

  const canonicalIds = new Set(
    (Array.isArray(companies) ? companies : [])
      .map((company) => String(company?.company_id || "").trim())
      .filter(Boolean),
  );
  const seen = new Set();

  records.forEach((record, index) => {
    const prefix = `records[${index}]`;
    const companyId = String(record?.company_id || "").trim();
    if (!companyId) errors.push(`${prefix}.company_id is required`);
    if (companyId && seen.has(companyId)) errors.push(`duplicate company_id: ${companyId}`);
    if (companyId) seen.add(companyId);
    if (canonicalIds.size && companyId && !canonicalIds.has(companyId)) errors.push(`unknown company_id: ${companyId}`);
    if (!VALID_STRATEGIC_ROLES.has(record?.strategic_role)) errors.push(`${prefix}.strategic_role is invalid`);
    if (!VALID_BASES.has(record?.basis)) errors.push(`${prefix}.basis is invalid`);
    if (!VALID_PRIORITIES.has(record?.priority ?? null)) errors.push(`${prefix}.priority is invalid`);
    if (record?.reviewed_at !== null && record?.reviewed_at !== undefined && !isIsoDate(record.reviewed_at)) {
      errors.push(`${prefix}.reviewed_at must be YYYY-MM-DD or null`);
    }
    if (record?.basis === "canonical_fallback" && record?.strategic_role !== "inherit") {
      errors.push(`${prefix}: canonical_fallback must use strategic_role=inherit`);
    }
    if (record?.basis === "user_business_judgment") {
      if (record?.strategic_role === "inherit") errors.push(`${prefix}: user_business_judgment cannot inherit`);
      if (!isIsoDate(record?.reviewed_at)) errors.push(`${prefix}: user_business_judgment requires reviewed_at`);
    }
  });

  if (canonicalIds.size) {
    const missing = [...canonicalIds].filter((companyId) => !seen.has(companyId)).sort();
    if (missing.length) errors.push(`strategy records missing canonical companies: ${missing.join(", ")}`);
    if (seen.size !== canonicalIds.size) {
      errors.push(`strategy company count mismatch: strategy=${seen.size} canonical=${canonicalIds.size}`);
    }
  }

  return { valid: errors.length === 0, errors };
}

export function applyCompanyStrategy(companies, payload) {
  const list = Array.isArray(companies) ? companies : [];
  const validation = validateCompanyStrategyPayload(payload, list);
  if (!validation.valid) return list;

  const recordsByCompany = new Map(
    getCompanyStrategyRecords(payload).map((record) => [record.company_id, record]),
  );

  return list.map((company) => {
    const strategy = recordsByCompany.get(company.company_id);
    if (!strategy) return company;
    return {
      ...company,
      strategy_override: { ...strategy },
    };
  });
}

export function getStrategyOverride(company) {
  const strategy = company?.strategy_override;
  return strategy && typeof strategy === "object" ? strategy : null;
}
