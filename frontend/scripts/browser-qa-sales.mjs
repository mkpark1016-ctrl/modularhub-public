import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { parseDate } from "../src/businessInsights.js";
import { getNewsSummary } from "../src/newsInsights.js";
import { getNewsDisplayRegion, newsRegionCounts } from "../src/newsRegion.js";
import { getOverseasCountryOptions, newsCountryMatches } from "../src/newsCountry.js";

const baseUrl = process.env.QA_BASE_URL || "http://127.0.0.1:5173";
const artifactDir = fileURLToPath(new URL("../qa-artifacts/", import.meta.url));

function check(condition, message) {
  if (!condition) throw new Error(message);
}

function itemsFrom(data) {
  return Array.isArray(data) ? data : data.items || [];
}

async function countCards(page) {
  return page.locator("article.result-card").count();
}

async function waitForCardCount(page, expected, message) {
  await page.waitForFunction(
    (count) => document.querySelectorAll("article.result-card").length === count,
    expected,
    { timeout: 8000 },
  );
  check(await countCards(page) === expected, message);
}

async function checkNoBadDisplayText(page, scope, label) {
  const text = await page.locator(scope).innerText();
  for (const token of ["undefined", "null", "NaN", "Invalid Date"]) {
    check(!text.includes(token), `${label} contains ${token}`);
  }
}

function escapedRegex(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function selectForLabel(page, label) {
  return page.locator("label").filter({ hasText: new RegExp(`^${escapedRegex(label)}`) }).locator("select").first();
}

async function selectFilter(page, label, value) {
  await selectForLabel(page, label).selectOption(value);
}

async function selectedFilterValue(page, label) {
  return selectForLabel(page, label).inputValue();
}

function statusOf(item) {
  return item.lifecycle_status || item.opportunity_status || "unknown";
}

function agencyForItem(item) {
  const code = item.source_code;
  if (code === "LH_CONTEST") return "LH";
  if (code === "GH_CONTEST") return "GH";
  if (code === "IH_NOTICE") return "iH";
  if (code === "SH_CONTEST") return "SH";
  const combined = `${item.source || ""} ${item.source_name || ""}`.toLowerCase();
  if (combined.includes("d2b")) return "D2B";
  if (item.source_type === "bid" || item.source_type === "procurement_plan") return "G2B";
  return item.source_name || item.source || "";
}

function countBy(items, predicate) {
  return items.filter(predicate).length;
}

function displayedNumber(value) {
  const digits = String(value || "").replace(/[^\d]/g, "");
  return digits ? Number(digits) : 0;
}

async function kpiNumber(page, id) {
  const text = await page.locator(`[data-kpi="${id}"] strong`).innerText();
  return displayedNumber(text);
}

const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

try {
  await mkdir(artifactDir, { recursive: true });

  const businessResponse = await page.request.get(`${baseUrl}/data/business.json`);
  const newsResponse = await page.request.get(`${baseUrl}/data/news.json`);
  const metaResponse = await page.request.get(`${baseUrl}/data/meta.json`);
  check(businessResponse.ok() && newsResponse.ok() && metaResponse.ok(), "public data JSON failed to load");

  const businessData = await businessResponse.json();
  const newsData = await newsResponse.json();
  const metaData = await metaResponse.json();
  const businessItems = itemsFrom(businessData);
  const newsItems = itemsFrom(newsData);
  const dashboardAsOf = parseDate(metaData.generated_at) || parseDate(metaData.last_updated_at) || new Date();
  const expectedNewsSummary = getNewsSummary(newsItems, dashboardAsOf);
  check(businessItems.length === metaData.business_count, "business count does not match meta");
  check(newsItems.length === metaData.news_count, "news count does not match meta");
  check(businessItems.length > 0, "business data is empty");
  check(newsItems.length > 0, "news data is empty");

  await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
  await page.evaluate(() => localStorage.clear());
  await page.getByRole("heading", { name: /오늘 확인할 사업과\s*모듈러 시장 뉴스/ }).waitFor();
  const homeText = await page.locator("main").innerText();
  for (const label of ["오늘의 영업 브리핑", "지금 확인할 사업", "최신 시장 뉴스", "수집원 상태"]) {
    check(homeText.includes(label), `home briefing missing ${label}`);
  }
  check(await page.locator(".intro h1 span").count() === 2, "hero heading should be two explicit lines");
  check((await page.locator(".intro h1").evaluate((node) => getComputedStyle(node).wordBreak)) === "keep-all", "hero heading should keep Korean words together");
  const directNewsKpi = await kpiNumber(page, "recent-direct-news");
  check(directNewsKpi === expectedNewsSummary.recentDirect7, `recent direct news KPI mismatch: expected ${expectedNewsSummary.recentDirect7}, got ${directNewsKpi}`);
  if (expectedNewsSummary.recentDirect7 > 0) {
    check(directNewsKpi > 0, "recent direct news KPI must not display zero when direct news exists");
  }
  const kpiHelperText = await page.locator(".kpi-helper").innerText();
  check(kpiHelperText.includes(`최근 7일 전체 뉴스 ${expectedNewsSummary.recent7.toLocaleString("ko-KR")}건`), "recent total news helper count mismatch");
  check(kpiHelperText.includes(`연관 산업 ${expectedNewsSummary.recentAdjacent7.toLocaleString("ko-KR")}건`), "recent adjacent news helper count mismatch");
  check(homeText.includes("일부 제한"), "workflow should be displayed as partially limited");
  const healthToggle = page.locator(".source-health-panel button").first();
  check(await healthToggle.getAttribute("aria-expanded") === "false", "source health details should start collapsed");
  await healthToggle.click();
  check(await healthToggle.getAttribute("aria-expanded") === "true", "source health details should expand");
  const healthText = await page.locator(".source-health-panel").innerText();
  check(healthText.includes("D2B"), "source health details should include D2B");
  check(healthText.includes("중지"), "D2B should be displayed as stopped, not a generic error");
  check(healthText.includes("SH"), "source health details should include SH");
  check(healthText.includes("해외 RSS"), "source health details should include overseas RSS");
  check(healthText.includes("미수집") || healthText.includes("수집 기록 없음"), "SH not_collected should be shown as not collected");
  check(!healthText.includes("SH\n현재 공고 없음"), "SH not_collected must not be shown as no current notices");
  check(healthText.includes("GW API 전환 필요"), "D2B migration note missing");
  check(await page.locator(".news-brief-item .relevance-badge.reference, .news-brief-item .relevance-badge.excluded").count() === 0, "home latest news should exclude reference/excluded items");

  await page.goto(`${baseUrl}/business`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "모듈러 사업정보" }).waitFor();
  await page.locator("article.result-card").first().waitFor();
  await waitForCardCount(page, businessItems.length, "business default card count mismatch");
  await checkNoBadDisplayText(page, "main", "business list");

  await selectFilter(page, "사업 유형", "bid");
  await waitForCardCount(page, countBy(businessItems, (item) => item.source_type === "bid"), "bid filter mismatch");
  await page.getByRole("button", { name: "필터 초기화" }).first().click();
  await waitForCardCount(page, businessItems.length, "business reset after type filter failed");

  await selectFilter(page, "기관", "G2B");
  await waitForCardCount(page, countBy(businessItems, (item) => agencyForItem(item) === "G2B"), "agency filter mismatch");
  await page.getByRole("button", { name: "필터 초기화" }).first().click();
  await waitForCardCount(page, businessItems.length, "business reset after agency filter failed");

  await selectFilter(page, "진행 상태", "active");
  await waitForCardCount(page, countBy(businessItems, (item) => statusOf(item) === "active"), "active status filter mismatch");
  await page.getByRole("button", { name: "필터 초기화" }).first().click();
  await waitForCardCount(page, businessItems.length, "business reset after status filter failed");

  await selectFilter(page, "정렬", "deadline");
  check(page.url().includes("sort=deadline"), "business sort is not synced to URL");
  await page.getByRole("button", { name: "필터 초기화" }).first().click();
  await waitForCardCount(page, businessItems.length, "business reset after sort failed");

  await page.getByRole("button", { name: /관심목록에 추가/ }).first().click();
  await page.reload({ waitUntil: "networkidle" });
  await selectFilter(page, "빠른 필터", "favorites");
  await waitForCardCount(page, 1, "business favorite filter should show one saved item");

  await page.getByRole("button", { name: "필터 초기화" }).first().click();
  await page.getByRole("link", { name: "상세보기" }).first().click();
  await page.locator("article.detail-page").waitFor();
  const viewedBusinessId = page.url().split("/").pop();
  await page.waitForFunction(
    (id) => JSON.parse(localStorage.getItem("modularhub.recentlyViewedBusinessIds") || "[]").includes(String(id)),
    viewedBusinessId,
  );
  await page.goto(`${baseUrl}/business`, { waitUntil: "networkidle" });
  check((await page.locator("main").innerText()).includes("최근 본 항목"), "recently viewed business marker missing");

  await page.goto(`${baseUrl}/business?priority=due7&sort=deadline`, { waitUntil: "networkidle" });
  check((await selectedFilterValue(page, "빠른 필터")) === "due7", "business priority URL param not restored");
  check((await selectedFilterValue(page, "정렬")) === "deadline", "business sort URL param not restored");

  await page.goto(`${baseUrl}/news`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "모듈러 뉴스정보" }).waitFor();
  await page.locator("article.result-card").first().waitFor();
  await waitForCardCount(page, newsItems.length, "news default card count mismatch");
  await checkNoBadDisplayText(page, "main", "news list");
  check(await page.locator("article.result-card").first().getByText(/관련도 \d+\/100/).count() >= 1, "news card relevance score should use N/100 label");

  const displayRegionCounts = newsRegionCounts(newsItems);
  const domesticCount = displayRegionCounts.domestic;
  const overseasCount = displayRegionCounts.overseas;
  const countryOptions = getOverseasCountryOptions(newsItems, getNewsDisplayRegion);
  const countryOptionTotal = countryOptions.reduce((sum, option) => sum + option.count, 0);
  check(displayRegionCounts.all === newsItems.length, "display region total should match news count");
  check(domesticCount + overseasCount === newsItems.length, "news display region counts should add up to total");
  check(countryOptionTotal === overseasCount, "country option counts should add up to overseas count");
  check(!countryOptions.some((option) => option.value === "KR"), "KR should not appear in overseas country options");
  check(await selectForLabel(page, "국가").count() === 0, "country dropdown should be hidden before overseas filter");
  check(await page.getByRole("button", { name: /지역 미확인/ }).count() === 0, "unknown region button should not be visible");
  check(await selectForLabel(page, "출처").count() === 0, "source dropdown should not be rendered");
  await page.getByRole("button", { name: /해외/ }).click();
  await waitForCardCount(page, overseasCount, "overseas news filter mismatch");
  check(await selectForLabel(page, "국가").count() === 1, "country dropdown should be shown for overseas filter");
  const firstCountry = countryOptions.find((option) => option.value !== "unknown");
  if (firstCountry) {
    await selectFilter(page, "국가", firstCountry.value);
    await waitForCardCount(
      page,
      newsItems.filter((item) => getNewsDisplayRegion(item) === "overseas" && newsCountryMatches(item, firstCountry.value)).length,
      "country filter card count mismatch",
    );
    check(new URL(page.url()).searchParams.get("country") === firstCountry.value, "country URL param missing");
    await selectFilter(page, "국가", "all");
    await waitForCardCount(page, overseasCount, "all countries should restore overseas count");
  }
  const unknownCountry = countryOptions.find((option) => option.value === "unknown");
  if (unknownCountry) {
    await selectFilter(page, "국가", "unknown");
    await waitForCardCount(page, unknownCountry.count, "unknown country filter card count mismatch");
    await selectFilter(page, "국가", "all");
    await waitForCardCount(page, overseasCount, "all countries should restore after unknown country");
  }
  check((await page.locator("main").innerText()).includes("해외"), "overseas badge missing");

  await page.getByRole("button", { name: /전체/ }).first().click();
  await waitForCardCount(page, newsItems.length, "news all filter should restore after unknown check");
  check(!page.url().includes("country="), "country param should be removed outside overseas filter");

  const searchInput = page.getByPlaceholder("뉴스 제목, 내용, 언론사 검색");
  await searchInput.dispatchEvent("compositionstart");
  await searchInput.fill("사상초등학교 모듈러 교실");
  check(!page.url().includes("q="), "Korean composition should not update URL before compositionend");
  await searchInput.dispatchEvent("compositionend");
  await page.waitForURL(/q=/);
  check(new URL(page.url()).searchParams.get("q") === "사상초등학교 모듈러 교실", "Korean composed query should be committed to URL");
  check(await searchInput.inputValue() === "사상초등학교 모듈러 교실", "Korean composed input should stay intact");
  await searchInput.fill('"modular housing" factory');
  await page.keyboard.press("Enter");
  await page.waitForURL(/modular%20housing|modular\+housing/);
  check(new URL(page.url()).searchParams.get("q") === '"modular housing" factory', "quoted English query should be preserved");
  await page.getByRole("button", { name: /필터 초기화/ }).first().click();
  await page.waitForFunction(() => document.querySelector('input[placeholder="뉴스 제목, 내용, 언론사 검색"]')?.value === "");
  check(await searchInput.inputValue() === "", "news search input should clear after reset");

  const originalLink = page.getByRole("link", { name: "원문 보기" }).first();
  check(await originalLink.count() >= 1, "original news link missing");
  check((await originalLink.getAttribute("target")) === "_blank", "original news link should open in new tab");
  check((await originalLink.getAttribute("rel"))?.includes("noopener"), "original news link missing noopener");

  await page.getByRole("button", { name: /관심 뉴스에 추가/ }).first().click();
  await selectFilter(page, "주제", "favorites");
  await waitForCardCount(page, 1, "news favorite filter should show one saved item");

  await page.goto(`${baseUrl}/news?region=overseas&sort=relevance`, { waitUntil: "networkidle" });
  check(page.url().includes("region=overseas"), "news region URL param missing");
  if (firstCountry) {
    await page.goto(`${baseUrl}/news?region=overseas&country=${firstCountry.value}&q=modular`, { waitUntil: "networkidle" });
    check(new URL(page.url()).searchParams.get("country") === firstCountry.value, "country URL param should restore");
    check(new URL(page.url()).searchParams.get("q") === "modular", "country URL should preserve q");
    await page.goto(`${baseUrl}/news?region=domestic&country=${firstCountry.value}`, { waitUntil: "networkidle" });
    check(!page.url().includes("country="), "domestic URL should remove country param");
    await page.goto(`${baseUrl}/news?country=${firstCountry.value}`, { waitUntil: "networkidle" });
    check(!page.url().includes("country="), "country without overseas region should be removed");
  }
  await page.goto(`${baseUrl}/news?region=overseas&country=XX`, { waitUntil: "networkidle" });
  check(!page.url().includes("country=XX"), "invalid country param should be removed");
  await page.goto(`${baseUrl}/news?region=overseas&sort=relevance`, { waitUntil: "networkidle" });
  check((await selectedFilterValue(page, "정렬")) === "relevance", "news sort URL param not restored");
  await page.goto(`${baseUrl}/news?region=unknown&q=모듈러&source=SBS&days=30`, { waitUntil: "networkidle" });
  check(!page.url().includes("region=unknown"), "legacy unknown region param should be removed");
  check(!page.url().includes("source="), "legacy source param should be removed");
  check(decodeURIComponent(page.url()).includes("q=모듈러"), "legacy URL cleanup should preserve q");
  check(page.url().includes("days=30"), "legacy URL cleanup should preserve days");
  await selectFilter(page, "관련도", "direct");
  check(page.url().includes("relevance=direct"), "news relevance URL param missing");
  check(await page.locator("article.result-card").count() >= 1, "direct relevance filter should show at least one item");
  check((await page.locator("main").innerText()).includes("직접 관련"), "direct relevance badge missing");
  await page.goto(`${baseUrl}/news?relevance=direct`, { waitUntil: "networkidle" });
  check((await selectedFilterValue(page, "관련도")) === "direct", "news relevance URL param not restored");

  await page.getByRole("link", { name: "상세보기" }).first().click();
  await page.locator("article.detail-page").waitFor();
  const viewedNewsId = page.url().split("/").pop();
  await page.waitForFunction(
    (id) => JSON.parse(localStorage.getItem("modularhub.recentlyViewedNewsIds") || "[]").includes(String(id)),
    viewedNewsId,
  );
  await page.goto(`${baseUrl}/news`, { waitUntil: "networkidle" });
  check((await page.locator("main").innerText()).includes("최근 본 항목"), "recently viewed news marker missing");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
  check(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), "home mobile has horizontal overflow");
  check(await page.locator(".intro h1 span").count() === 2, "mobile hero heading should remain two explicit lines");
  await page.goto(`${baseUrl}/business`, { waitUntil: "networkidle" });
  check(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), "business mobile has horizontal overflow");
  await page.getByRole("button", { name: /사업 검색조건/ }).click();
  await selectFilter(page, "빠른 필터", "due7");

  await page.goto(`${baseUrl}/news`, { waitUntil: "networkidle" });
  check(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), "news mobile has horizontal overflow");
  await page.getByRole("button", { name: /뉴스 검색조건/ }).click();
  check(await selectForLabel(page, "출처").count() === 0, "mobile source dropdown should not be rendered");
  await page.getByRole("button", { name: /해외/ }).click();

  const credentialTokens = [
    "service" + "Key",
    "DATA_GO_KR_" + "SERVICE_KEY",
    "NAVER_CLIENT_" + "SE" + "CRET",
    "NAVER_CLIENT_" + "ID",
  ];
  const credentialPattern = new RegExp(credentialTokens.join("|"), "i");
  check(!credentialPattern.test(JSON.stringify([businessData, newsData, metaData])), "public JSON exposes credential token names");

  console.log(`BROWSER QA PASSED: business=${businessItems.length}, news=${newsItems.length}, overseas=${overseasCount}`);
} finally {
  await browser.close();
}
