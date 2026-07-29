export const COMPANY_SORT_VALUES = ["tier", "recent_activity", "verified", "name", "revenue", "operating_margin", "production", "verified_projects", "technology"];
export const COMPANY_STATUS_VALUES = ["all", "core_verified", "partially_verified", "research_in_progress", "watchlist", "insufficient_public_data"];
const LEGACY_STATUS_ALIASES = {
  verified: "core_verified",
  partial: "partially_verified",
  collecting: "research_in_progress",
};
const LEGACY_ROLE_ALIASES = {
  specialist_manufacturer: "modular_specialist",
  modular_integrator: "modular_specialist",
  producer_group: "modular_specialist",
};

export function sanitizeCompanySearchParams(searchParams, validValues) {
  const next = new URLSearchParams(searchParams);
  let changed = false;
  const legacyStatus = next.get("status");
  if (LEGACY_STATUS_ALIASES[legacyStatus]) {
    next.set("status", LEGACY_STATUS_ALIASES[legacyStatus]);
    changed = true;
  }
  const legacyRole = next.get("role");
  if (LEGACY_ROLE_ALIASES[legacyRole]) {
    next.set("role", LEGACY_ROLE_ALIASES[legacyRole]);
    changed = true;
  }
  const rules = {
    role: ["all", ...(validValues.roles || [])],
    relationship: ["all", ...(validValues.relationships || [])],
    tier: ["all", ...(validValues.tiers || [])],
    status: COMPANY_STATUS_VALUES,
    sort: COMPANY_SORT_VALUES,
  };
  for (const [key, allowed] of Object.entries(rules)) {
    const value = next.get(key);
    if (!value) continue;
    if (!allowed.includes(value)) {
      next.delete(key);
      changed = true;
    }
  }
  const compare = next.get("compare");
  if (compare && Array.isArray(validValues.companyIds)) {
    const allowed = new Set(validValues.companyIds);
    const normalized = [];
    for (const id of compare.split(",").map((item) => item.trim()).filter(Boolean)) {
      if (!allowed.has(id) || normalized.includes(id)) continue;
      normalized.push(id);
      if (normalized.length === 4) break;
    }
    const serialized = normalized.join(",");
    if (!serialized) next.delete("compare");
    else next.set("compare", serialized);
    if (serialized !== compare) changed = true;
  }
  return { params: next, changed };
}
