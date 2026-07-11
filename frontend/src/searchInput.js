export function normalizeSearchCommitValue(value) {
  return String(value || "").normalize("NFC");
}

export function shouldCommitSearchValue(nextValue, currentValue) {
  return normalizeSearchCommitValue(nextValue) !== String(currentValue || "");
}
