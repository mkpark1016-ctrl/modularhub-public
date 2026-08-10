import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  COMPANY_ACTIVITY_PERIOD_FILTERS,
  COMPANY_ACTIVITY_SORT_OPTIONS,
  filterCompanyActivities,
  filterCompanyActivitiesByPeriod,
  getActivityFilterGroup,
  getActivitySourceName,
  getActivitySourceUrl,
  getCompanyActivities,
  getCompanyActivityFilterCounts,
  getCompanyActivityHistory,
  isValidActivity,
  searchCompanyActivities,
  sortCompanyActivities,
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

const historyPayload = {
  schemaVersion: "company-activity-history-v1",
  companyId: "yuchang-enc",
  activityCount: yuchangActivities.length,
  activities: yuchangActivities,
};
assert.equal(getCompanyActivityHistory(historyPayload, "yuchang-enc"), yuchangActivities);
assert.equal(getCompanyActivityHistory({ ...historyPayload, schemaVersion: "wrong" }, "yuchang-enc"), null);
assert.equal(getCompanyActivityHistory(historyPayload, "other-company"), null);
assert.equal(getCompanyActivityHistory({ ...historyPayload, activities: null }, "yuchang-enc"), null);

assert.deepEqual(COMPANY_ACTIVITY_PERIOD_FILTERS.map((option) => option.value), ["all", "90", "180", "365"]);
assert.deepEqual(COMPANY_ACTIVITY_SORT_OPTIONS.map((option) => option.value), ["newest", "oldest"]);

const syntheticActivities = [
  {
    activityId: "a-new",
    companyId: "test-company",
    activityType: "project",
    title: "모듈러 프로젝트 수주",
    summary: "서울 현장 계약",
    publishedAt: "2026-08-09",
    sourceName: "건설일보",
    confidence: "high",
  },
  {
    activityId: "a-factory",
    companyId: "test-company",
    activityType: "factory",
    title: "모듈러 공장 증설",
    summary: "스마트 생산라인 확대",
    publishedAt: "2026-06-01",
    sourceName: "산업일보",
    confidence: "high",
  },
  {
    activityId: "a-financial",
    companyId: "test-company",
    activityType: "financial",
    title: "연간 실적 발표",
    summary: "매출 증가",
    publishedAt: "2026-01-01",
    sourceName: "공시자료",
    confidence: "medium",
  },
  {
    activityId: "a-partnership",
    companyId: "test-company",
    activityType: "partnership",
    title: "기술 협력 업무협약",
    summary: "공동 연구개발",
    publishedAt: "2025-09-01",
    sourceName: "기업 보도자료",
    confidence: "medium",
  },
];

assert.equal(filterCompanyActivitiesByPeriod(syntheticActivities, "all", "2026-08-10").length, 4);
assert.deepEqual(filterCompanyActivitiesByPeriod(syntheticActivities, "90", "2026-08-10").map((item) => item.activityId), ["a-new", "a-factory"]);
assert.deepEqual(filterCompanyActivitiesByPeriod(syntheticActivities, "180", "2026-08-10").map((item) => item.activityId), ["a-new", "a-factory"]);
assert.equal(filterCompanyActivitiesByPeriod(syntheticActivities, "365", "2026-08-10").length, 4);
assert.deepEqual(searchCompanyActivities(syntheticActivities, "공장 산업일보").map((item) => item.activityId), ["a-factory"]);
assert.deepEqual(searchCompanyActivities(syntheticActivities, "공동 연구개발").map((item) => item.activityId), ["a-partnership"]);
assert.equal(searchCompanyActivities(syntheticActivities, "없는검색어").length, 0);
const beforeSort = syntheticActivities.map((item) => item.activityId);
assert.deepEqual(sortCompanyActivities(syntheticActivities, "newest").map((item) => item.activityId), ["a-new", "a-factory", "a-financial", "a-partnership"]);
assert.deepEqual(sortCompanyActivities(syntheticActivities, "oldest").map((item) => item.activityId), ["a-partnership", "a-financial", "a-factory", "a-new"]);
assert.deepEqual(syntheticActivities.map((item) => item.activityId), beforeSort, "sorting must not mutate input activities");
assert.deepEqual(getCompanyActivityFilterCounts(syntheticActivities), {
  all: 4,
  projects: 1,
  investment_factory: 1,
  technology_financial: 1,
  general: 1,
});

assert.equal(COMPANY_DETAIL_TABS[1]?.value, "activity");
assert.equal(COMPANY_DETAIL_TABS[1]?.label, "활동·동향");
assert.equal(normalizeCompanyTab("activity"), "activity");
assert.equal(normalizeCompanyTab("not-a-tab"), "overview");

const detailViewSource = readFileSync(new URL("../src/components/company/CompanyDetailView.jsx", import.meta.url), "utf8");
const overviewSource = readFileSync(new URL("../src/components/company/CompanyOverviewTab.jsx", import.meta.url), "utf8");
const timelineSource = readFileSync(new URL("../src/components/company/CompanyActivityTimeline.jsx", import.meta.url), "utf8");
const companyUiOverridesSource = readFileSync(new URL("../src/companyUiOverrides.css", import.meta.url), "utf8");
assert.match(detailViewSource, /activities=\{activities\}/);
assert.match(detailViewSource, /CompanyActivityTimeline/);
assert.match(detailViewSource, /tab === "activity"/);
assert.match(detailViewSource, /company-tab-panel-activity/);
assert.match(detailViewSource, /company-activity-history/);
assert.match(detailViewSource, /getCompanyActivityHistory/);
assert.match(detailViewSource, /encodeURIComponent\(companyId\)/);
assert.match(detailViewSource, /historyActivities \?\? activities/);
assert.match(detailViewSource, /CompanyActivityTimeline activities=\{timelineActivities\}/);
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
assert.match(timelineSource, /제목·요약·출처 검색/);
assert.match(timelineSource, /COMPANY_ACTIVITY_PERIOD_FILTERS/);
assert.match(timelineSource, /COMPANY_ACTIVITY_SORT_OPTIONS/);
assert.match(timelineSource, /getCompanyActivityFilterCounts/);
assert.match(timelineSource, /검색·필터 결과/);
assert.match(timelineSource, /setVisibleCount\(\(count\) => count \+ INITIAL_VISIBLE_COUNT\)/);
assert.match(timelineSource, /건 더 보기 ·/);
assert.doesNotMatch(timelineSource, /setExpanded/);
assert.match(timelineSource, /검색·필터 조건에 맞는 활동이 없습니다/);
assert.match(timelineSource, /확인된 공개 활동이 없습니다/);
assert.match(timelineSource, /{sourceName} 원문 보기/);
assert.match(timelineSource, /getActivitySourceUrl/);
assert.match(timelineSource, /company-activity-search-control/);
assert.match(timelineSource, /company-activity-period-control/);
assert.match(timelineSource, /company-activity-sort-control/);
assert.match(timelineSource, /company-activity-toolbar-label">활동 검색/);
assert.match(timelineSource, /company-activity-toolbar-label">기간/);
assert.match(timelineSource, /company-activity-toolbar-label">정렬/);
assert.match(companyUiOverridesSource, /@media \(min-width: 960px\)/);
assert.match(companyUiOverridesSource, /grid-template-columns: minmax\(360px, 2\.2fr\) minmax\(210px, 1fr\) minmax\(210px, 1fr\)/);
assert.match(companyUiOverridesSource, /@media \(min-width: 761px\) and \(max-width: 959px\)/);
assert.match(companyUiOverridesSource, /company-activity-search-control/);
assert.match(companyUiOverridesSource, /grid-column: 1 \/ -1/);
assert.match(companyUiOverridesSource, /@media \(max-width: 760px\)/);

console.log("COMPANY ACTIVITY FRONTEND TESTS PASSED");
