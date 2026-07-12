export const NEWS_REGION_VALUES = ["all", "domestic", "overseas"];

export function sanitizeNewsSearchParams(params) {
  const next = new URLSearchParams(params);
  let changed = false;

  if (next.has("source")) {
    next.delete("source");
    changed = true;
  }

  const region = next.get("region");
  if (region === "unknown" || (region && !NEWS_REGION_VALUES.includes(region))) {
    next.delete("region");
    changed = true;
  }

  const resolvedRegion = NEWS_REGION_VALUES.includes(next.get("region")) ? next.get("region") : "all";
  const country = next.get("country");
  if (country && resolvedRegion !== "overseas") {
    next.delete("country");
    changed = true;
  } else if (country && country !== "unknown") {
    const normalized = country.toUpperCase();
    if (/^[A-Z]{2}$/.test(normalized)) {
      if (normalized !== country) {
        next.set("country", normalized);
        changed = true;
      }
    } else {
      next.delete("country");
      changed = true;
    }
  }

  return { params: next, changed };
}
