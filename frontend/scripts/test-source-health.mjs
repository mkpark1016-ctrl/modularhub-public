import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { getSourceHealth, getSourceHealthSummary, mapSourceStatus } from "../src/sourceHealth.js";

assert.deepEqual(mapSourceStatus("success"), { status: "success", label: "정상", severity: "success", description: "" });
assert.equal(mapSourceStatus("success_no_matches").label, "정상·현재 대상 없음");
assert.equal(mapSourceStatus("not_collected").label, "미수집");
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
assert.equal(sh.label, "미수집");
assert.equal(sh.severity, "notice");
assert.ok(!JSON.stringify(sh).includes("현재 공고 없음"));
assert.equal(d2b.label, "중지");
assert.equal(d2b.severity, "limited");
assert.match(d2b.description, /GW API 전환 필요/);
assert.equal(workflow.label, "일부 제한");
assert.equal(workflow.severity, "limited");
assert.match(workflow.description, /D2B 기존 API는 중지 상태/);

const summary = getSourceHealthSummary(sources, meta);
assert.equal(summary.successCount, 5);
assert.equal(summary.limitedCount, 1);
assert.equal(summary.notCollectedCount, 1);
assert.equal(summary.workflow.label, "일부 제한");

const appSource = readFileSync(new URL("../src/components/SourceHealthPanel.jsx", import.meta.url), "utf8");
assert.match(appSource, /aria-expanded/);
assert.match(appSource, /상세 보기/);
assert.match(appSource, /상세 닫기/);

console.log("SOURCE HEALTH TESTS PASSED");
