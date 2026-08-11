import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const timelineSource = readFileSync(new URL("../src/components/company/CompanyActivityTimeline.jsx", import.meta.url), "utf8");
const overridesSource = readFileSync(new URL("../src/companyUiOverrides.css", import.meta.url), "utf8");

assert.match(timelineSource, /import \{ ExternalLink \} from "lucide-react"/);
assert.doesNotMatch(timelineSource, /ExternalLink, Search|<Search\b/);
assert.match(timelineSource, /className="company-activity-search-input"/);
assert.match(timelineSource, /placeholder="제목·요약·출처 검색"/);
assert.match(overridesSource, /\.company-activity-toolbar \.company-activity-search-input/);
assert.match(overridesSource, /height: 50px/);
assert.match(overridesSource, /min-height: 50px/);
assert.match(overridesSource, /grid-template-columns: max-content minmax\(0, 1fr\)/);
assert.match(overridesSource, /align-items: center/);

console.log("COMPANY ACTIVITY TOOLBAR ALIGNMENT TESTS PASSED");
