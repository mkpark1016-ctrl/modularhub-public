from pathlib import Path


overview_path = Path("frontend/src/components/company/CompanyOverviewTab.jsx")
overview = overview_path.read_text(encoding="utf-8")
import_anchor = 'import { buildCompanyDecisionModel } from "../../companyDecisionModel";\n'
import_replacement = import_anchor + 'import { getActivitySourceName, getActivitySourceUrl } from "../../companyActivities";\n'
if "getActivitySourceName" not in overview:
    if import_anchor not in overview:
        raise SystemExit("overview import anchor not found")
    overview = overview.replace(import_anchor, import_replacement, 1)

old_block = '''function RecentActivityPreview({ activities }) {
  const visible = (activities || []).slice(0, 3);
  return (
    <div className="company-subsection compact-company-section">
      <div className="company-subsection-heading">
        <h3>최근 활동</h3>
        <span>최대 3건</span>
      </div>
      {visible.length ? (
        <div className="company-compact-row-list">
          {visible.map((activity) => (
            <div key={activity.activityId || activity.url || activity.title}>
              <b>{activity.title}</b>
              <span>{activity.source || activity.publisher || "공개자료"}</span>
              <em>{formatDate(activity.publishedAt)}</em>
            </div>
          ))}
        </div>
      ) : (
        <p className="finance-note">최근 공개 활동 신호가 확인되지 않았습니다.</p>
      )}
    </div>
  );
}
'''
new_block = '''function RecentActivityPreview({ activities }) {
  const visible = (activities || []).slice(0, 3);
  return (
    <div className="company-subsection compact-company-section">
      <div className="company-subsection-heading">
        <h3>최근 활동</h3>
        <span>최대 3건</span>
      </div>
      {visible.length ? (
        <div className="company-compact-row-list">
          {visible.map((activity) => {
            const sourceName = getActivitySourceName(activity);
            const sourceUrl = getActivitySourceUrl(activity);
            return (
              <div key={activity.activityId || activity.url || activity.title}>
                <b>{activity.title}</b>
                <span>
                  {sourceUrl ? (
                    <a className="inline-link" href={sourceUrl} target="_blank" rel="noopener noreferrer" aria-label={`${sourceName} 원문 열기`}>
                      {sourceName} <ExternalLink size={12} />
                    </a>
                  ) : sourceName}
                </span>
                <em>{formatDate(activity.publishedAt)}</em>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="finance-note">최근 공개 활동 신호가 확인되지 않았습니다.</p>
      )}
    </div>
  );
}
'''
if old_block in overview:
    overview = overview.replace(old_block, new_block, 1)
elif "const sourceName = getActivitySourceName(activity);" not in overview:
    raise SystemExit("overview RecentActivityPreview anchor not found")
overview_path.write_text(overview, encoding="utf-8")

test_path = Path("frontend/scripts/test-company-activities.mjs")
test = test_path.read_text(encoding="utf-8")
old_import = """  filterCompanyActivities,\n  getActivityFilterGroup,\n  getCompanyActivities,\n  isValidActivity,\n"""
new_import = """  filterCompanyActivities,\n  getActivityFilterGroup,\n  getActivitySourceName,\n  getActivitySourceUrl,\n  getCompanyActivities,\n  isValidActivity,\n"""
if "getActivitySourceName" not in test:
    if old_import not in test:
        raise SystemExit("test import anchor not found")
    test = test.replace(old_import, new_import, 1)

activity_assert_anchor = '    assert.equal(isValidActivity(activity), true, `invalid public activity ${activity.activityId}`);\n'
activity_assert_replacement = activity_assert_anchor + '    assert.equal(typeof activity.sourceName, "string", `missing sourceName for ${activity.activityId}`);\n    assert.ok(activity.sourceName.trim(), `empty sourceName for ${activity.activityId}`);\n'
if "missing sourceName for" not in test:
    if activity_assert_anchor not in test:
        raise SystemExit("activity assertion anchor not found")
    test = test.replace(activity_assert_anchor, activity_assert_replacement, 1)

yuchang_anchor = 'assert.ok(yuchangActivities.length > 0, "expected yuchang activities");\n'
helper_assertions = '''assert.ok(yuchangActivities.length > 0, "expected yuchang activities");
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
'''
if "expected at least one source-backed yuchang activity" not in test:
    if yuchang_anchor not in test:
        raise SystemExit("yuchang assertion anchor not found")
    test = test.replace(yuchang_anchor, helper_assertions, 1)

static_anchor = "assert.match(overviewSource, /company-compact-row-list/);\n"
static_replacement = static_anchor + '''assert.match(overviewSource, /getActivitySourceName/);
assert.match(overviewSource, /getActivitySourceUrl/);
assert.match(overviewSource, /href={sourceUrl}/);
assert.match(overviewSource, /target="_blank"/);
assert.match(overviewSource, /rel="noopener noreferrer"/);
'''
if "assert.match(overviewSource, /getActivitySourceName/);" not in test:
    if static_anchor not in test:
        raise SystemExit("static overview assertion anchor not found")
    test = test.replace(static_anchor, static_replacement, 1)

timeline_anchor = "assert.match(timelineSource, /최근 확인된 공개 활동이 없습니다/);\n"
timeline_replacement = timeline_anchor + "assert.match(timelineSource, /{sourceName} 원문 보기/);\nassert.match(timelineSource, /getActivitySourceUrl/);\n"
if "assert.match(timelineSource, /{sourceName} 원문 보기/);" not in test:
    if timeline_anchor not in test:
        raise SystemExit("timeline assertion anchor not found")
    test = test.replace(timeline_anchor, timeline_replacement, 1)
test_path.write_text(test, encoding="utf-8")
