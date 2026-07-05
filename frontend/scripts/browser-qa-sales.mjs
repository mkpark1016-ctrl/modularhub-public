import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const baseUrl = process.env.QA_BASE_URL || "http://127.0.0.1:5173";
const artifactDir = fileURLToPath(new URL("../qa-artifacts/", import.meta.url));
const OVERSEAS_RSS_SOURCE = "해외 모듈러 RSS";

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
  check(businessItems.length === metaData.business_count, "business count does not match meta");
  check(newsItems.length === metaData.news_count, "news count does not match meta");
  check(businessItems.length > 0, "business data is empty");
  check(newsItems.length > 0, "news data is empty");

  await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
  await page.evaluate(() => localStorage.clear());
  await page.getByRole("heading", { name: /오늘 확인할 사업과 시장 뉴스/ }).waitFor();
  const homeText = await page.locator("main").innerText();
  for (const label of ["오늘의 영업 브리핑", "지금 확인할 사업", "최신 시장 뉴스", "수집원 상태"]) {
    check(homeText.includes(label), `home briefing missing ${label}`);
  }
  check(homeText.includes("D2B"), "source health is missing D2B");
  check(homeText.includes("해외 RSS"), "source health is missing overseas RSS");
  await page.screenshot({ path: `${artifactDir}/home.png`, fullPage: false });

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
  await page.screenshot({ path: `${artifactDir}/business.png`, fullPage: true });

  await page.goto(`${baseUrl}/business?priority=due7&sort=deadline`, { waitUntil: "networkidle" });
  check((await selectedFilterValue(page, "빠른 필터")) === "due7", "business priority URL param not restored");
  check((await selectedFilterValue(page, "정렬")) === "deadline", "business sort URL param not restored");

  await page.goto(`${baseUrl}/news`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "모듈러 뉴스정보" }).waitFor();
  await page.locator("article.result-card").first().waitFor();
  await waitForCardCount(page, newsItems.length, "news default card count mismatch");
  await checkNoBadDisplayText(page, "main", "news list");

  const overseasCount = countBy(newsItems, (item) => item.source === OVERSEAS_RSS_SOURCE);
  await page.getByRole("button", { name: /해외뉴스/ }).click();
  await waitForCardCount(page, overseasCount, "overseas news filter mismatch");
  check((await page.locator("main").innerText()).includes("해외뉴스"), "overseas badge missing");

  const originalLink = page.getByRole("link", { name: "원문 보기" }).first();
  check(await originalLink.count() >= 1, "original news link missing");
  check((await originalLink.getAttribute("target")) === "_blank", "original news link should open in new tab");
  check((await originalLink.getAttribute("rel"))?.includes("noopener"), "original news link missing noopener");

  await page.getByRole("button", { name: /관심 뉴스에 추가/ }).first().click();
  await selectFilter(page, "주제", "favorites");
  await waitForCardCount(page, 1, "news favorite filter should show one saved item");

  await page.goto(`${baseUrl}/news?region=overseas&sort=relevance`, { waitUntil: "networkidle" });
  check(page.url().includes("region=overseas"), "news region URL param missing");
  check((await selectedFilterValue(page, "정렬")) === "relevance", "news sort URL param not restored");
  await page.screenshot({ path: `${artifactDir}/news.png`, fullPage: true });

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
  await page.goto(`${baseUrl}/business`, { waitUntil: "networkidle" });
  check(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), "business mobile has horizontal overflow");
  await page.getByRole("button", { name: /사업 검색조건/ }).click();
  await selectFilter(page, "빠른 필터", "due7");
  await page.screenshot({ path: `${artifactDir}/business-mobile.png`, fullPage: true });

  await page.goto(`${baseUrl}/news`, { waitUntil: "networkidle" });
  check(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), "news mobile has horizontal overflow");
  await page.getByRole("button", { name: /뉴스 검색조건/ }).click();
  await page.getByRole("button", { name: /해외뉴스/ }).click();
  await page.screenshot({ path: `${artifactDir}/news-mobile.png`, fullPage: true });

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
