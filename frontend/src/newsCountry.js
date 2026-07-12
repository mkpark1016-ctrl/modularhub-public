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
