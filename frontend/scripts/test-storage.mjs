import assert from "node:assert/strict";
import {
  addRecentId,
  getLastVisitAt,
  isStoredId,
  readIdList,
  setLastVisitAt,
  toggleId,
  writeIdList,
} from "../src/storage.js";

function makeStorage({ throwOnWrite = false, throwOnRead = false } = {}) {
  const data = new Map();
  return {
    getItem(key) {
      if (throwOnRead) throw new Error("read blocked");
      return data.has(key) ? data.get(key) : null;
    },
    setItem(key, value) {
      if (throwOnWrite) throw new Error("write blocked");
      data.set(key, value);
    },
    removeItem(key) {
      data.delete(key);
    },
    clear() {
      data.clear();
    },
  };
}

const oldWindow = globalThis.window;

try {
  globalThis.window = { localStorage: makeStorage() };
  assert.deepEqual(readIdList("favoriteBusinessIds"), []);

  let ids = toggleId("favoriteBusinessIds", 10);
  assert.deepEqual(ids, ["10"]);
  assert.equal(isStoredId("favoriteBusinessIds", 10), true);

  ids = toggleId("favoriteBusinessIds", 10);
  assert.deepEqual(ids, []);
  assert.equal(isStoredId("favoriteBusinessIds", 10), false);

  writeIdList("favoriteNewsIds", ["7", "7", "8"]);
  assert.deepEqual(readIdList("favoriteNewsIds"), ["7", "8"]);

  addRecentId("recentlyViewedBusinessIds", "a", 3);
  addRecentId("recentlyViewedBusinessIds", "b", 3);
  addRecentId("recentlyViewedBusinessIds", "c", 3);
  addRecentId("recentlyViewedBusinessIds", "d", 3);
  assert.deepEqual(readIdList("recentlyViewedBusinessIds"), ["d", "c", "b"]);

  setLastVisitAt("2026-07-05T00:00:00+09:00");
  assert.equal(getLastVisitAt(), "2026-07-05T00:00:00+09:00");

  globalThis.window = { localStorage: makeStorage({ throwOnRead: true, throwOnWrite: true }) };
  assert.doesNotThrow(() => readIdList("favoriteBusinessIds"));
  assert.doesNotThrow(() => toggleId("favoriteBusinessIds", "x"));

  delete globalThis.window;
  assert.deepEqual(readIdList("favoriteBusinessIds"), []);
  assert.doesNotThrow(() => addRecentId("recentlyViewedNewsIds", "1"));
} finally {
  if (oldWindow === undefined) {
    delete globalThis.window;
  } else {
    globalThis.window = oldWindow;
  }
}

console.log("STORAGE TESTS PASSED");
