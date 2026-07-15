export const COMPANY_SORT_VALUES = ["tier", "verified", "name"];
export const COMPANY_STATUS_VALUES = ["all", "core_verified", "partially_verified", "research_in_progress", "watchlist", "insufficient_public_data"];
const LEGACY_STATUS_ALIASES = {
  verified: "core_verified",
  partial: "partially_verified",
  collecting: "research_in_progress",
};

export function sanitizeCompanySearchParams(searchParams, validValues) {
  const next = new URLSearchParams(searchParams);
  let changed = false;
  const legacyStatus = next.get("status");
  if (LEGACY_STATUS_ALIASES[legacyStatus]) {
    next.set("status", LEGACY_STATUS_ALIASES[legacyStatus]);
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
  return { params: next, changed };
}
