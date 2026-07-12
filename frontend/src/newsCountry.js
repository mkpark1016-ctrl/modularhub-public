export function getPublisherCountryCode(item) {
  return String(item?.publisher_country_code || "").trim().toUpperCase();
}

export function getPublisherCountryName(item) {
  return String(item?.publisher_country_name || "국가 미확인").trim() || "국가 미확인";
}

export function getPublisherCountryLabel(item) {
  const code = getPublisherCountryCode(item);
  const name = getPublisherCountryName(item);
  return code ? `${name} (${code})` : name;
}

function isKnownOverseasCountry(item) {
  const code = getPublisherCountryCode(item);
  const confidence = String(item?.publisher_country_confidence || "").trim();
  return Boolean(code && code !== "KR" && confidence !== "unknown");
}

export function getNewsCountryFilterValue(item) {
  return isKnownOverseasCountry(item) ? getPublisherCountryCode(item) : "unknown";
}

export function getNewsCountryDisplayName(item) {
  return isKnownOverseasCountry(item) ? getPublisherCountryName(item) : "국가 미확인";
}

export function getNewsCountryBadgeLabel(item, displayRegion) {
  if (displayRegion !== "overseas") return "국내";
  return isKnownOverseasCountry(item) ? getPublisherCountryName(item) : "해외";
}

export function getNewsDetailCountryLabel(item) {
  const code = getPublisherCountryCode(item);
  if (!code || String(item?.publisher_country_confidence || "").trim() === "unknown") return "확인되지 않음";
  return getPublisherCountryName(item);
}

export function getOverseasCountryOptions(items, getDisplayRegion) {
  const groups = new Map();
  for (const item of items || []) {
    if (getDisplayRegion(item) !== "overseas") continue;
    const value = getNewsCountryFilterValue(item);
    const label = value === "unknown" ? "국가 미확인" : getNewsCountryDisplayName(item);
    const current = groups.get(value) || { value, label, count: 0 };
    current.count += 1;
    groups.set(value, current);
  }
  const known = [...groups.values()]
    .filter((option) => option.value !== "unknown")
    .sort((a, b) => (b.count - a.count) || a.label.localeCompare(b.label, "ko-KR"));
  const unknown = groups.get("unknown");
  return unknown ? [...known, unknown] : known;
}

export function newsCountryMatches(item, country) {
  if (!country || country === "all") return true;
  return getNewsCountryFilterValue(item) === country;
}

export function countryOptionLabel(option) {
  return `${option.label} ${Number(option.count || 0).toLocaleString("ko-KR")}`;
}
