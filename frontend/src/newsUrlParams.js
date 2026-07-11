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

  return { params: next, changed };
}
