export const COMPANY_SORT_VALUES = ["tier", "verified", "name"];
export const COMPANY_STATUS_VALUES = ["all", "verified", "partial", "collecting"];

export function sanitizeCompanySearchParams(searchParams, validValues) {
  const next = new URLSearchParams(searchParams);
  let changed = false;
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
