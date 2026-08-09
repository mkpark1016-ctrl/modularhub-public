export const COMPANY_SORT_VALUES = ["name", "recent_activity", "revenue", "verified_projects"];
const LEGACY_ROLE_ALIASES = {
  specialist_manufacturer: "modular_specialist",
  modular_integrator: "modular_specialist",
  producer_group: "modular_specialist",
};
const OBSOLETE_FILTER_KEYS = ["relationship", "tier", "status", "audit", "facility"];

export function sanitizeCompanySearchParams(searchParams, validValues) {
  const next = new URLSearchParams(searchParams);
  let changed = false;
  for (const key of OBSOLETE_FILTER_KEYS) {
    if (next.has(key)) {
      next.delete(key);
      changed = true;
    }
  }
  const legacyRole = next.get("role");
  if (LEGACY_ROLE_ALIASES[legacyRole]) {
    next.set("role", LEGACY_ROLE_ALIASES[legacyRole]);
    changed = true;
  }
  const rules = {
    role: ["all", ...(validValues.roles || [])],
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
  for (const key of [...next.keys()]) {
    if (!["q", "role", "sort", "compare"].includes(key)) {
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
