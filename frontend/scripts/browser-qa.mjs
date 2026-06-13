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

const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1365, height: 900 } });

try {
  await mkdir(artifactDir, { recursive: true });
  const businessResponse = await page.request.get(`${baseUrl}/data/business.json`);
  const newsResponse = await page.request.get(`${baseUrl}/data/news.json`);
  const metaResponse = await page.request.get(`${baseUrl}/data/meta.json`);
  check(businessResponse.ok() && newsResponse.ok() && metaResponse.ok(), "정적 JSON 응답 실패");
  const businessData = await businessResponse.json();
  const newsData = await newsResponse.json();
  const metaData = await metaResponse.json();
  check(businessData.items.length === metaData.business_count, "사업정보 meta 건수 불일치");
  check(newsData.items.length === metaData.news_count, "뉴스 meta 건수 불일치");
  check(businessData.items.length > 0, "사업정보가 비어 있음");
  check(newsData.items.length > 0, "뉴스정보가 비어 있음");

  await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: /사업기회와 시장 뉴스/ }).waitFor();
  check(await page.getByRole("link", { name: "사업정보 보기" }).count() === 1, "홈 사업정보 CTA 누락");
  check(await page.getByRole("link", { name: "뉴스정보 보기" }).count() === 1, "홈 뉴스 CTA 누락");
  const homeText = await page.locator("main").innerText();
  check(homeText.includes(`${businessData.items.length}건`), "홈 사업정보 건수 누락");
  check(homeText.includes(`${newsData.items.length}건`), "홈 뉴스 건수 누락");
  await page.screenshot({ path: `${artifactDir}/home.png`, fullPage: false });

  await page.getByRole("link", { name: "사업정보 보기" }).click();
  await page.waitForURL(`${baseUrl}/business`);
  await page.getByRole("heading", { name: "모듈러 사업정보" }).waitFor();
  await page.locator("article.result-card").first().waitFor();
  check(await countCards(page) === businessData.items.length, "사업정보 카드 수 불일치");
  const businessSearch = page.getByPlaceholder("공고명, 기관, 공고번호");
  const searchableBusiness = businessData.items.find((item) => item.bid_no || item.plan_no) || businessData.items[0];
  await businessSearch.fill(searchableBusiness.plan_no || searchableBusiness.bid_no || searchableBusiness.title.slice(0, 10));
  check(await countCards(page) >= 1, "사업정보 공고번호 검색 실패");
  await businessSearch.fill("");
  await page.getByLabel("유형").selectOption("입찰공고");
  const bidCount = businessData.items.filter((item) => item.source_type === "bid").length;
  check(await countCards(page) === bidCount, "입찰공고 source_type 필터 실패");
  await page.getByLabel("유형").selectOption("발주계획");
  const planCount = businessData.items.filter((item) => item.source_type === "procurement_plan").length;
  if (planCount > 0) {
    check(await countCards(page) === planCount, "발주계획 source_type 필터 실패");
  } else {
    const stateText = await page.locator("section.results").innerText();
    check(stateText.includes("발주계획"), "발주계획 0건 안내 누락");
    if (metaData.g2b_order_plan_status === "failed") {
      check(stateText.includes("나라장터 발주계획 API 호출에 실패"), "나라장터 발주계획 실패 안내 누락");
    }
    if (metaData.g2b_order_plan_status === "success_no_match") {
      check(stateText.includes("현재 조회기간 내 모듈러 발주계획 데이터가 없습니다"), "발주계획 정상 0건 안내 누락");
    }
    if (metaData.d2b_status === "disabled_stopped") {
      check(stateText.includes("방위사업청 기존 API는 중지 상태"), "D2B 중지 안내 누락");
    }
  }
  await page.screenshot({ path: `${artifactDir}/business.png`, fullPage: false });

  const businessItem = businessData.items[0];
  await page.goto(`${baseUrl}/business/${businessItem.id}`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: businessItem.title }).waitFor();
  const businessText = await page.locator("article.detail-page").innerText();
  for (const label of ["기관", "게시일", "마감일", "금액", "공고/판단/계획번호", "공식 확인 사이트", "검색 조합"]) {
    check(businessText.includes(label), `사업 상세 필드 누락: ${label}`);
  }
  await page.screenshot({ path: `${artifactDir}/business-detail.png`, fullPage: true });
  await page.reload({ waitUntil: "networkidle" });
  check(page.url().endsWith(`/business/${businessItem.id}`), "사업 상세 새로고침 경로 유지 실패");
  check(await page.getByRole("heading", { name: businessItem.title }).count() === 1, "사업 상세 새로고침 렌더 실패");

  await page.goto(`${baseUrl}/news`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "모듈러 뉴스정보" }).waitFor();
  await page.locator("article.result-card").first().waitFor();
  check(await countCards(page) === newsData.items.length, "뉴스 카드 수 불일치");
  const newsSearch = page.getByPlaceholder("뉴스 제목, 요약");
  await newsSearch.fill(newsData.items[0].title.slice(0, 12));
  check(await countCards(page) >= 1, "뉴스 검색 실패");
  check(await page.getByRole("link", { name: "원문 보기" }).count() >= 1, "뉴스 원문 보기 누락");
  await page.screenshot({ path: `${artifactDir}/news.png`, fullPage: false });

  const newsItem = newsData.items[0];
  await page.goto(`${baseUrl}/news/${newsItem.id}`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: newsItem.title }).waitFor();
  const newsText = await page.locator("article.detail-page").innerText();
  for (const label of ["기관", "게시일", "내용", "원문 열기"]) {
    check(newsText.includes(label), `뉴스 상세 필드 누락: ${label}`);
  }
  await page.screenshot({ path: `${artifactDir}/news-detail.png`, fullPage: true });
  await page.reload({ waitUntil: "networkidle" });
  check(page.url().endsWith(`/news/${newsItem.id}`), "뉴스 상세 새로고침 경로 유지 실패");
  check(await page.getByRole("heading", { name: newsItem.title }).count() === 1, "뉴스 상세 새로고침 렌더 실패");

  const secretPattern = /serviceKey|DATA_GO_KR_SERVICE_KEY|NAVER_CLIENT_SECRET|NAVER_CLIENT_ID/i;
  check(!secretPattern.test(JSON.stringify([businessData, newsData, metaData])), "공개 JSON에 인증정보 토큰 노출");
  console.log(`BROWSER QA PASSED: business=${businessData.items.length}, news=${newsData.items.length}`);
} finally {
  await browser.close();
}
