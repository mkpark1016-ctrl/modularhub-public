import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const baseUrl = process.env.QA_BASE_URL || "http://127.0.0.1:5173";
const artifactDir = fileURLToPath(new URL("../qa-artifacts/", import.meta.url));

function check(condition, message) {
  if (!condition) throw new Error(message);
}

async function countCards(page) {
  return page.locator("article.result-card").count();
}

function itemsFrom(data) {
  return Array.isArray(data) ? data : data.items || [];
}

function sourceTypeCount(items, sourceType) {
  return items.filter((item) => item.source_type === sourceType).length;
}

function statusCount(items, status) {
  return items.filter((item) => (item.lifecycle_status || item.opportunity_status) === status).length;
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
  return "";
}

function agencyCount(items, agency) {
  return items.filter((item) => agencyForItem(item) === agency).length;
}

function typeAgencyCount(items, sourceType, agency) {
  return items.filter((item) => item.source_type === sourceType && agencyForItem(item) === agency).length;
}

async function checkNoBadDisplayText(page, scope, label) {
  const text = await page.locator(scope).innerText();
  for (const token of ["undefined", "null", "NaN", "Invalid Date"]) {
    check(!text.includes(token), `${label} 화면에 ${token} 표시`);
  }
}

const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

try {
  await mkdir(artifactDir, { recursive: true });

  const businessResponse = await page.request.get(`${baseUrl}/data/business.json`);
  const newsResponse = await page.request.get(`${baseUrl}/data/news.json`);
  const metaResponse = await page.request.get(`${baseUrl}/data/meta.json`);
  check(businessResponse.ok() && newsResponse.ok() && metaResponse.ok(), "정적 JSON 응답 실패");

  const businessData = await businessResponse.json();
  const newsData = await newsResponse.json();
  const metaData = await metaResponse.json();
  const businessItems = itemsFrom(businessData);
  const newsItems = itemsFrom(newsData);
  const businessIds = businessItems.map((item) => item.id);
  const lifecycleTotal = statusCount(businessItems, "active")
    + statusCount(businessItems, "closed")
    + statusCount(businessItems, "unknown");

  check(businessItems.length === metaData.business_count, "사업정보 meta 건수 불일치");
  check(newsItems.length === metaData.news_count, "뉴스 meta 건수 불일치");
  check(businessItems.length > 0, "사업정보 로드 실패");
  check(newsItems.length > 0, "뉴스정보 로드 실패");
  check(sourceTypeCount(businessItems, "bid") > 0, "입찰공고 데이터 없음");
  check(sourceTypeCount(businessItems, "procurement_plan") > 0, "발주계획 데이터 없음");
  check(sourceTypeCount(businessItems, "public_agency_contest") > 0, "공공기관 공모 데이터 없음");
  check(lifecycleTotal === businessItems.length, "사업정보 lifecycle 건수 불일치");
  check(businessIds.every(Boolean), "사업정보 id 누락");
  check(new Set(businessIds).size === businessItems.length, "사업정보 id 중복");

  await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: /사업기회와 시장 뉴스를/ }).waitFor();
  check(await page.getByRole("link", { name: "사업정보 보기" }).count() === 1, "홈 사업정보 CTA 누락");
  check(await page.getByRole("link", { name: "뉴스정보 보기" }).count() === 1, "홈 뉴스 CTA 누락");
  const homeText = await page.locator("main").innerText();
  check(homeText.includes(`${businessItems.length}건`), "홈 사업정보 건수 누락");
  check(homeText.includes(`${newsItems.length}건`), "홈 뉴스 건수 누락");
  await page.screenshot({ path: `${artifactDir}/home.png`, fullPage: false });

  await page.getByRole("link", { name: "사업정보 보기" }).click();
  await page.waitForURL(`${baseUrl}/business`);
  await page.getByRole("heading", { name: "모듈러 사업정보" }).waitFor();
  await page.locator("article.result-card").first().waitFor();
  check(await countCards(page) === businessItems.length, "사업정보 카드 수 불일치");
  await checkNoBadDisplayText(page, "main", "사업정보 기본");
  await page.screenshot({ path: `${artifactDir}/business-desktop-default.png`, fullPage: true });
  await page.setViewportSize({ width: 1920, height: 1080 });
  check(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), "1920px 데스크톱 가로 스크롤 발생");
  await page.screenshot({ path: `${artifactDir}/business-desktop-wide.png`, fullPage: true });
  await page.setViewportSize({ width: 1440, height: 900 });

  const businessMainText = await page.locator("main").innerText();
  for (const label of ["전체", "진행 중", "마감 임박", "발주계획", "공공기관 공모"]) {
    check(businessMainText.includes(label), `사업정보 요약 누락: ${label}`);
  }

  await page.getByLabel("사업 유형", { exact: true }).selectOption("bid");
  check(await countCards(page) === sourceTypeCount(businessItems, "bid"), "입찰공고 유형 필터 실패");
  await page.getByLabel("사업 유형", { exact: true }).selectOption("procurement_plan");
  check(await countCards(page) === sourceTypeCount(businessItems, "procurement_plan"), "발주계획 유형 필터 실패");
  await page.getByLabel("사업 유형", { exact: true }).selectOption("public_agency_contest");
  check(await countCards(page) === sourceTypeCount(businessItems, "public_agency_contest"), "공공기관 공모 유형 필터 실패");
  await checkNoBadDisplayText(page, "main", "공공기관 공모");
  await page.screenshot({ path: `${artifactDir}/business-desktop-public-agency.png`, fullPage: true });

  await page.getByLabel("기관", { exact: true }).selectOption("LH");
  check(await countCards(page) === typeAgencyCount(businessItems, "public_agency_contest", "LH"), "LH 기관 필터 실패");
  await page.getByLabel("기관", { exact: true }).selectOption("GH");
  check(await countCards(page) === typeAgencyCount(businessItems, "public_agency_contest", "GH"), "GH 기관 필터 실패");
  await page.getByLabel("기관", { exact: true }).selectOption("iH");
  check(await countCards(page) === typeAgencyCount(businessItems, "public_agency_contest", "iH"), "iH 기관 필터 실패");
  await page.getByLabel("기관", { exact: true }).selectOption("SH");
  const shPublicAgencyCount = typeAgencyCount(businessItems, "public_agency_contest", "SH");
  check(await countCards(page) === shPublicAgencyCount, "SH 기관 필터 실패");
  if (shPublicAgencyCount === 0) {
    check((await page.locator("section.results").innerText()).includes("현재 공개 가능한 SH 민간사업자 공모가 없습니다"), "SH 0건 안내 누락");
    check((await page.locator("section.results").innerText()).includes("SH 수집기는 정상 모니터링 중입니다"), "SH 모니터링 안내 누락");
  }
  await page.screenshot({ path: `${artifactDir}/business-desktop-sh-empty.png`, fullPage: true });

  await page.getByRole("button", { name: "필터 초기화" }).first().click();
  check(await countCards(page) === businessItems.length, "필터 초기화 실패");
  await page.getByLabel("사업 유형", { exact: true }).selectOption("bid");
  await page.getByLabel("기관", { exact: true }).selectOption("G2B");
  check(await countCards(page) === typeAgencyCount(businessItems, "bid", "G2B"), "입찰공고 + 나라장터 복합 필터 실패");
  await page.getByRole("button", { name: "필터 초기화" }).first().click();

  await page.getByLabel("진행 상태", { exact: true }).selectOption("active");
  check(await countCards(page) === statusCount(businessItems, "active"), "진행 중 상태 필터 실패");
  await page.getByLabel("진행 상태", { exact: true }).selectOption("closed");
  check(await countCards(page) === statusCount(businessItems, "closed"), "마감 상태 필터 실패");
  await page.getByLabel("진행 상태", { exact: true }).selectOption("unknown");
  check(await countCards(page) === statusCount(businessItems, "unknown"), "상태 미확인 필터 실패");

  await page.getByRole("button", { name: "필터 초기화" }).first().click();
  const contestItem = businessItems.find((item) => item.source_type === "public_agency_contest" && item.source_record_id);
  check(Boolean(contestItem), "공공기관 공모 샘플 누락");
  await page.getByPlaceholder("공고명, 기관, 공고번호, 지역").fill(contestItem.source_record_id);
  check(await countCards(page) >= 1, "사업정보 검색 실패");
  await page.screenshot({ path: `${artifactDir}/business.png`, fullPage: false });

  await page.goto(`${baseUrl}/business/${contestItem.id}`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: contestItem.title }).waitFor();
  const businessDetailText = await page.locator("article.detail-page").innerText();
  for (const label of ["기관", "게시일", "마감일", "공고/판단/계획번호", "진행 상태", "공식 원문"]) {
    check(businessDetailText.includes(label), `사업 상세 필드 누락: ${label}`);
  }
  const officialLink = page.getByRole("link", { name: /공식 원문|원문 열기/ }).first();
  check(await officialLink.count() >= 1, "공식 원문 링크 누락");
  check(Boolean(await officialLink.getAttribute("href")), "공식 원문 href 누락");
  check((await officialLink.getAttribute("target")) === "_blank", "공식 원문 새 창 설정 누락");
  await page.reload({ waitUntil: "networkidle" });
  check(page.url().endsWith(`/business/${contestItem.id}`), "사업 상세 새로고침 경로 유지 실패");
  await checkNoBadDisplayText(page, "article.detail-page", "사업 상세");
  await page.screenshot({ path: `${artifactDir}/business-detail.png`, fullPage: true });
  await page.screenshot({ path: `${artifactDir}/business-detail-desktop.png`, fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${baseUrl}/business`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "모듈러 사업정보" }).waitFor();
  const mobileFilterBox = await page.locator(".filters").boundingBox();
  check(Boolean(mobileFilterBox) && mobileFilterBox.width <= 390, "모바일 필터 폭 초과");
  check(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), "390px 모바일 가로 스크롤 발생");
  await checkNoBadDisplayText(page, "main", "모바일 사업정보");
  await page.screenshot({ path: `${artifactDir}/business-mobile-default.png`, fullPage: true });
  await page.getByLabel("사업 유형", { exact: true }).selectOption("public_agency_contest");
  await page.getByLabel("기관", { exact: true }).selectOption("LH");
  check(await countCards(page) === typeAgencyCount(businessItems, "public_agency_contest", "LH"), "모바일 공공기관 + LH 필터 실패");
  await page.screenshot({ path: `${artifactDir}/business-mobile-filters.png`, fullPage: true });
  await page.screenshot({ path: `${artifactDir}/business-mobile.png`, fullPage: true });
  await page.setViewportSize({ width: 430, height: 932 });
  await page.goto(`${baseUrl}/business`, { waitUntil: "networkidle" });
  check(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), "430px 모바일 가로 스크롤 발생");
  await page.screenshot({ path: `${artifactDir}/business-mobile-430.png`, fullPage: true });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${baseUrl}/news`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "모듈러 뉴스정보" }).waitFor();
  await page.locator("article.result-card").first().waitFor();
  check(await countCards(page) === newsItems.length, "뉴스 카드 수 불일치");
  await page.getByPlaceholder("뉴스 제목, 요약").fill(newsItems[0].title.slice(0, 12));
  check(await countCards(page) >= 1, "뉴스 검색 실패");
  await checkNoBadDisplayText(page, "main", "뉴스 목록");
  await page.screenshot({ path: `${artifactDir}/news.png`, fullPage: false });
  await page.screenshot({ path: `${artifactDir}/news-regression.png`, fullPage: true });

  const newsItem = newsItems[0];
  await page.goto(`${baseUrl}/news/${newsItem.id}`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: newsItem.title }).waitFor();
  const newsText = await page.locator("article.detail-page").innerText();
  for (const label of ["기관", "게시일", "내용", "원문 열기"]) {
    check(newsText.includes(label), `뉴스 상세 필드 누락: ${label}`);
  }
  await page.reload({ waitUntil: "networkidle" });
  check(page.url().endsWith(`/news/${newsItem.id}`), "뉴스 상세 새로고침 경로 유지 실패");
  await checkNoBadDisplayText(page, "article.detail-page", "뉴스 상세");
  await page.screenshot({ path: `${artifactDir}/news-detail.png`, fullPage: true });

  const credentialTokens = [
    "service" + "Key",
    "DATA_GO_KR_" + "SERVICE_KEY",
    "NAVER_CLIENT_" + "SE" + "CRET",
    "NAVER_CLIENT_" + "ID",
  ];
  const credentialPattern = new RegExp(credentialTokens.join("|"), "i");
  check(!credentialPattern.test(JSON.stringify([businessData, newsData, metaData])), "공개 JSON에 인증정보 토큰 노출");
  console.log(`BROWSER QA PASSED: business=${businessItems.length}, news=${newsItems.length}`);
} finally {
  await browser.close();
}
