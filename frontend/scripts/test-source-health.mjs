import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { getSourceHealth, getSourceHealthSummary, mapSourceStatus } from "../src/sourceHealth.js";

assert.equal(mapSourceStatus("success").severity, "success");
assert.equal(mapSourceStatus("success_no_matches").severity, "success");
assert.equal(mapSourceStatus("not_collected").severity, "notice");
assert.equal(mapSourceStatus("disabled_stopped", { description: "GW API 전환 필요" }).severity, "limited");
assert.equal(mapSourceStatus("failed").severity, "error");

const meta = {
  workflow_last_run_status: "warning",
  d2b_status: "disabled_stopped",
  d2b_gw_migration_required: true,
  g2b_order_plan_status: "success",
  procurement_plan_collection_status: "success",
  lh_contest_status: "success",
  gh_contest_status: "success",
  ih_contest_status: "success",
  sh_contest_status: "not_collected",
  sh_public_count: 0,
  generated_at: "2026-07-06T07:52:22+09:00",
};

const sources = getSourceHealth(meta);
const sh = sources.find((source) => source.id === "sh");
const d2b = sources.find((source) => source.id === "d2b");
const workflow = sources.find((source) => source.id === "workflow");
assert.equal(sh.severity, "notice");
assert.equal(d2b.severity, "limited");
assert.match(d2b.description, /GW API/);
assert.equal(workflow.severity, "limited");

const summary = getSourceHealthSummary(sources, meta);
assert.equal(summary.successCount, 5);
assert.equal(summary.limitedCount, 1);
assert.equal(summary.notCollectedCount, 1);
assert.equal(summary.workflow.id, "workflow");

const migratedD2bSources = getSourceHealth({
  ...meta,
  workflow_last_run_status: "success",
  d2b_status: "success",
  d2b_message: "Unified D2B GW 공개 데이터가 유지되고 있습니다.",
  d2b_legacy_status: "disabled_stopped",
  d2b_gw_migration_required: false,
});
const migratedD2b = migratedD2bSources.find((source) => source.id === "d2b");
assert.equal(migratedD2b.status, "success");
assert.equal(migratedD2b.label, "정상");
assert.match(migratedD2b.description, /Unified D2B GW/);
assert.equal(migratedD2bSources.find((source) => source.id === "workflow").status, "success");

const newsSourceMeta = {
  ...meta,
  news_source_statuses: [
    {
      id: "naver_api_hub",
      name: "NAVER API HUB",
      state: "success",
      latest_item_published_at: "2026-07-22T10:00:00+09:00",
      fetched_count: 12,
      accepted_count: 4,
      duplicate_count: 8,
    },
    {
      id: "overseas_rss",
      name: "해외 RSS",
      state: "success_no_public_match",
      fetched_count: 0,
      accepted_count: 0,
      duplicate_count: 0,
    },
  ],
};
const dynamicSources = getSourceHealth(newsSourceMeta);
const naver = dynamicSources.find((source) => source.id === "naver_api_hub");
const overseasRss = dynamicSources.find((source) => source.id === "overseas_rss");
assert.equal(naver.name, "NAVER API HUB");
assert.equal(naver.severity, "success");
assert.match(naver.description, /2026-07-22/);
assert.equal(naver.acceptedCount, 4);
assert.equal(overseasRss.severity, "success");

const companyChangeMeta = {
  ...meta,
  company_change_source_statuses: [
    {
      source_id: "public_news",
      name: "공개 뉴스",
      source_type: "snapshot",
      state: "success_empty_valid",
      last_run_at: "2026-07-27T00:00:00Z",
      accepted_count: 0,
      filtered_count: 0,
      simple_status: "신규 매칭 없음",
    },
  ],
  company_change_source_concentration: {
    state: "history_insufficient",
    history_state: "history_insufficient",
    dominant_source: "naver_api_hub",
    raw_dominant_source_share: 0.9955,
    unique_dominant_source_share: 0.991,
    comparable_run_count: 2,
    concentration_sustained: false,
  },
};
const companyChangeSources = getSourceHealth(companyChangeMeta);
const publicNewsChange = companyChangeSources.find((source) => source.id === "company-change-public_news");
const concentration = companyChangeSources.find((source) => source.id === "company-change-source-concentration");
assert.equal(publicNewsChange.severity, "success");
assert.match(publicNewsChange.description, /snapshot/);
assert.equal(concentration.severity, "warning");
assert.match(concentration.description, /naver_api_hub/);
assert.match(concentration.description, /99\.6%/);
assert.ok(!JSON.stringify(publicNewsChange).includes("candidate queue"));
assert.ok(!JSON.stringify(publicNewsChange).includes("fingerprint"));
assert.ok(!JSON.stringify(publicNewsChange).includes("secret"));
assert.ok(!JSON.stringify(concentration).includes("review_queue"));
assert.ok(!JSON.stringify(concentration).includes("raw_response"));
assert.ok(!JSON.stringify(concentration).includes("Authorization"));

const appSource = readFileSync(new URL("../src/components/SourceHealthPanel.jsx", import.meta.url), "utf8");
assert.match(appSource, /aria-expanded/);

console.log("SOURCE HEALTH TESTS PASSED");
