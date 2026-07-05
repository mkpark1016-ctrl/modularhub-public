const KEYS = {
  favoriteBusinessIds: "modularhub.favoriteBusinessIds",
  favoriteNewsIds: "modularhub.favoriteNewsIds",
  recentlyViewedBusinessIds: "modularhub.recentlyViewedBusinessIds",
  recentlyViewedNewsIds: "modularhub.recentlyViewedNewsIds",
  lastVisitAt: "modularhub.lastVisitAt",
};

function storageAvailable() {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function readJson(key, fallback) {
  if (!storageAvailable()) return fallback;
  try {
    const value = window.localStorage.getItem(key);
    return value ? JSON.parse(value) : fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key, value) {
  if (!storageAvailable()) return false;
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

export function readIdList(keyName) {
  const value = readJson(KEYS[keyName], []);
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

export function writeIdList(keyName, ids) {
  const unique = [...new Set((ids || []).map(String).filter(Boolean))];
  return writeJson(KEYS[keyName], unique);
}

export function toggleId(keyName, id) {
  const textId = String(id);
  const ids = readIdList(keyName);
  const next = ids.includes(textId) ? ids.filter((value) => value !== textId) : [textId, ...ids];
  writeIdList(keyName, next);
  return next;
}

export function addRecentId(keyName, id, limit = 12) {
  const textId = String(id);
  const ids = readIdList(keyName).filter((value) => value !== textId);
  const next = [textId, ...ids].slice(0, limit);
  writeIdList(keyName, next);
  return next;
}

export function isStoredId(keyName, id) {
  return readIdList(keyName).includes(String(id));
}

export function setLastVisitAt(value = new Date().toISOString()) {
  return writeJson("modularhub.lastVisitAt", value);
}

export function getLastVisitAt() {
  const value = readJson(KEYS.lastVisitAt, "");
  return typeof value === "string" ? value : "";
}

export function getStorageKeys() {
  return { ...KEYS };
}
