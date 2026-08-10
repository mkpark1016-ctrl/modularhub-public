import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  filterCompanyActivities,
  getActivityFilterGroup,
  getActivitySourceName,
  getActivitySourceUrl,
  getCompanyActivities,
  isValidActivity,
} from "../src/companyActivities.js";
import { COMPANY_DETAIL_TABS, normalizeCompanyTab } from "../src/components/company/companyDetailHelpers.js";

const companiesPayload = JSON.parse(readFileSync(new URL("../public/data/companies/companies.json", import.meta.url), "utf8"));
const activityPayload = JSON.parse(readFileSync(new URL("../public/data/companies/company-activities.json", import.meta.url), "utf8"));
const companies = companiesPayload.companies;
const companyIds = new Set(companies.map((company) => company.company_id));

assert.equal(activityPayload.schemaVersion, "company-activities-v1");
assert.equal(activityPayload.companyCount, 11);
assert.equal(activityPayload.companies.length, 11);

for (const row of activityPayload.companies) {
  assert.ok(companyIds.has(row.companyId), `unknown companyId: ${row.companyId}`);
  assert.equal(row.activityCount, row.activities.length, `activity count mismatch for ${row.companyId}`);
  assert.ok(row.activities.length <= 100, `activity cap exceeded for ${row.companyId}`);
  for (const activity of row.activities) {
    assert.equal(activity.companyId, row.companyId);
    assert.ok(["high", "medium"].includes(activity.confidence), `invalid confidence for ${activity.activityId}`);
    assert.equal(isValidActivity(activity), true, `invalid public activity ${activity.activityId}`);
    assert.equal(typeof activity.sourceName, "string", `missing sourceName for ${activity.activityId}`);
    assert.ok(activity.sourceName.trim(), `empty sourceName for ${activity.activityId}`);
    if (activity.sourceUrl) assert.match(activity.sourceUrl, /^https?:\/\//);
    assert.doesNotMatch(JSON.stringify(activity), /raw_response|request_headers|Authorization|DART_API_KEY|NAVER_API_HUB_CLIENT_SECRET/);
  }
}

const yuchangActivities = getCompanyActivities(activityPayload, "yuchang-enc");
assert.ok(yuchangActivities.length > 0, "expected yuchang activities");
const sourceBackedActivity = yuchangActivities.find((activity) => activity.sourceUrl);
assert.ok(sourceBackedActivity, "expected at least one source-backed yuchang activity");
assert.equal(getActivitySourceName(sourceBackedActivity), sourceBackedActivity.sourceName);
assert.equal(getActivitySourceUrl(sourceBackedActivity), sourceBackedActivity.sourceUrl);
assert.equal(getActivitySourceName({ source: "기존 출처" }), "기존 출처");
assert.equal(getActivitySourceName({ publisher: "기존 언론사" }), "기존 언론사");
assert.equal(getActivitySourceName({}), "공개자료");
assert.equal(getActivitySourceUrl({ sourceUrl: "https://example.com/original" }), "https://example.com/original");
assert.equal(getActivitySourceUrl({ sourceUrl: "javascript:alert(1)" }), null);
assert.equal(getActivitySourceUrl({ sourceUrl: "not-a-url" }), null);
assert.deepEqual(getCompanyActivities(activityPayload, "missing-company"), []);
assert.ok(filterCompanyActivities(yuchangActivities, "all").length === yuchangActivities.length);
assert.ok(["projects", "investment_factory", "technology_financial", "general"].includes(getActivityFilterGroup(yuchangActivities[0].activityType)));

assert.equal(COMPANY_DETAIL_TABS[1]?.value, "activity");
assert.equal(COMPANY_DETAIL_TABS[1]?.label, "활동·동향");
assert.equal(normalizeCompanyTab("activity"), "activity");
assert.equal(normalizeCompanyTab("not-a-tab"), "overview");

const detailViewSource = readFileSync(new URL("../src/components/company/CompanyDetailView.jsx", import.meta.url), "utf8");
const overviewSource = readFileSync(new URL("../src/components/company/CompanyOverviewTab.jsx", import.meta.url), "utf8");
const timelineSource = readFileSync(new URL("../src/components/company/CompanyActivityTimeline.jsx", import.meta.url), "utf8");
assert.match(detailViewSource, /activities=\{activities\}/);
assert.match(detailViewSource, /CompanyActivityTimeline/);
assert.match(detailViewSource, /tab === "activity"/);
assert.match(detailViewSource, /company-tab-panel-activity/);
assert.match(detailViewSource, /공개 뉴스와 사업정보에서 확인된 기업 활동을 최신순으로 누적/);
assert.match(overviewSource, /RecentActivityPreview/);
assert.match(overviewSource, /company-compact-row-list/);
assert.match(overviewSource, /getActivitySourceName/);
assert.match(overviewSource, /getActivitySourceUrl/);
assert.match(overviewSource, /href={sourceUrl}/);
assert.match(overviewSource, /target="_blank"/);
assert.match(overviewSource, /rel="noopener noreferrer"/);
assert.match(overviewSource, /최신 3건 미리보기/);
assert.match(overviewSource, /활동·동향 전체 보기/);
assert.match(overviewSource, /onTabChange\?\.\("activity"\)/);
assert.doesNotMatch(overviewSource, /<span>최대 3건<\/span>/);
assert.match(timelineSource, /기업 활동 타임라인/);
assert.doesNotMatch(timelineSource, /최근 90일 변화/);
assert.match(timelineSource, /INITIAL_VISIBLE_COUNT = 10/);
assert.match(timelineSource, /확인된 활동/);
assert.match(timelineSource, /기업 활동 필터/);
assert.match(timelineSource, /\.sort\(\(a, b\) => String\(b\.publishedAt/);
assert.match(timelineSource, /확인된 공개 활동이 없습니다/);
assert.match(timelineSource, /{sourceName} 원문 보기/);
assert.match(timelineSource, /getActivitySourceUrl/);

console.log("COMPANY ACTIVITY FRONTEND TESTS PASSED");
