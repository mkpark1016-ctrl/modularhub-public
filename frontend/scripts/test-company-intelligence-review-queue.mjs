import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  filterReviewItems,
  getReviewQueueMetadata,
  getReviewFilterOptions,
  getReviewQueueKpis,
  isReviewQueueStale,
  isValidHttpUrl,
  normalizeReviewQueuePayload,
  paginateReviewItems,
  sortReviewItems,
  validateReviewQueuePayload,
} from "../src/companyIntelligenceReviewQueue.js";

const queue = JSON.parse(readFileSync(new URL("../public/data/company-intelligence/review-queue.json", import.meta.url), "utf8"));
const manifest = JSON.parse(readFileSync(new URL("../public/data/company-intelligence/manifest.json", import.meta.url), "utf8"));
const fixture = JSON.parse(readFileSync(new URL("../src/fixtures/company-intelligence-review-queue.json", import.meta.url), "utf8"));
const componentSource = readFileSync(new URL("../src/components/company/CompanyIntelligenceReviewQueuePage.jsx", import.meta.url), "utf8");
const appSource = readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");

assert.equal(validateReviewQueuePayload(queue).valid, true);
assert.equal(validateReviewQueuePayload(fixture).valid, true);
assert.equal(queue.items.length, 357);

const serialized = JSON.stringify(queue);
for (const forbidden of ["raw_ref", "promotion_blockers", "summary", "source_id", "evidence_hash", "crtfc_key", "NAVER_API_HUB_CLIENT_SECRET"]) {
  assert.equal(serialized.includes(forbidden), false, `${forbidden} leaked into public queue`);
}

const normalized = normalizeReviewQueuePayload(queue, manifest);
assert.equal(normalized.valid, true);
const { items } = normalized;
const kpis = getReviewQueueKpis(items, manifest);
assert.equal(kpis.total, 694);
assert.equal(kpis.pending, 357);
assert.equal(kpis.duplicate, 337);
assert.equal(kpis.qualityRejected, 124);
assert.equal(kpis.sourceCounts.dart, 0);
assert.equal(kpis.sourceCounts.naver_search, 694);
assert.equal(manifest.sourceRunId, "local-live-pilot");
assert.equal(manifest.sourceWorkflow, "Company Intelligence Monitor");
assert.equal(manifest.sourceBranch, "main");
assert.equal(manifest.lookbackDays, 30);
assert.equal(manifest.sourceCounts.dart, 0);
assert.equal(manifest.sourceCounts.naver, 694);
assert.equal(manifest.itemCount, queue.items.length);

const metadata = getReviewQueueMetadata(manifest);
assert.equal(metadata.sourceRunId, "local-live-pilot");
assert.equal(metadata.lookbackDays, 30);
assert.equal(isReviewQueueStale("2026-07-01T00:00:00Z", new Date("2026-07-18T00:00:00Z")), true);
assert.equal(isReviewQueueStale("2026-07-17T00:00:00Z", new Date("2026-07-18T00:00:00Z")), false);
const mismatch = normalizeReviewQueuePayload(queue, { ...manifest, itemCount: queue.items.length + 1 });
assert.equal(mismatch.valid, false);
assert.equal(mismatch.reason, "manifest_item_count_mismatch");

const options = getReviewFilterOptions(items, manifest);
assert.ok(options.companies.some((option) => option.value === "kumkang-kind"));
assert.ok(options.companies.some((option) => option.value === "yuchang-enc"));
assert.ok(options.sources.some((option) => option.value === "dart"));
assert.ok(options.sources.some((option) => option.value === "naver_search"));

const pending = filterReviewItems(items, { status: "pending", company: "", source: "", query: "", startDate: "", endDate: "" });
assert.equal(pending.length, 357);
const kumkang = filterReviewItems(items, { status: "", company: "kumkang-kind", source: "", query: "", startDate: "", endDate: "" });
assert.ok(kumkang.length > 0);
assert.ok(kumkang.every((item) => item.companyId === "kumkang-kind"));
const naver = filterReviewItems(items, { status: "", company: "", source: "naver_search", query: "", startDate: "", endDate: "" });
assert.equal(naver.length, 357);
const dart = filterReviewItems(items, { status: "", company: "", source: "dart", query: "", startDate: "", endDate: "" });
assert.equal(dart.length, 0);
const keyword = items.find((item) => item.matchedKeyword)?.matchedKeyword;
if (keyword) {
  const searched = filterReviewItems(items, { status: "", company: "", source: "", query: keyword.slice(0, 2), startDate: "", endDate: "" });
  assert.ok(searched.length > 0);
}

const sortedDesc = sortReviewItems(items, "published_desc");
assert.ok(Date.parse(sortedDesc[0].publishedAt) >= Date.parse(sortedDesc[sortedDesc.length - 1].publishedAt));
const sortedAsc = sortReviewItems(items, "published_asc");
assert.ok(Date.parse(sortedAsc[0].publishedAt) <= Date.parse(sortedAsc[sortedAsc.length - 1].publishedAt));
const page = paginateReviewItems(sortedDesc, 1, 20);
assert.equal(page.items.length, 20);
assert.ok(page.pageCount > 1);
const largePage = paginateReviewItems(sortedDesc, 999, 100);
assert.equal(largePage.page, largePage.pageCount);

assert.equal(isValidHttpUrl("https://example.com/a"), true);
assert.equal(isValidHttpUrl("javascript:alert(1)"), false);
assert.equal(isValidHttpUrl(""), false);

assert.ok(componentSource.includes("VITE_COMPANY_INTELLIGENCE_DATA_URL"));
assert.ok(componentSource.includes("import.meta.env.DEV || import.meta.env.MODE === \"test\""));
assert.equal(componentSource.includes("import.meta.env.PROD &&"), false);
assert.ok(componentSource.includes("manifest_missing"));
assert.ok(componentSource.includes("DataProvenance"));
assert.ok(componentSource.includes("최신 수집 데이터가 7일 이상 경과했습니다."));
assert.ok(appSource.includes("/company-intelligence"));
assert.ok(appSource.includes("기업 모니터링"));

console.log("COMPANY INTELLIGENCE REVIEW QUEUE TESTS PASSED");
