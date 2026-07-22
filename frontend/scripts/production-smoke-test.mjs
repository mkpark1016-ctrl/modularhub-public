import { chromium } from "playwright";

const baseUrl = (process.env.PRODUCTION_BASE_URL || process.env.QA_BASE_URL || "https://modularhub-public.vercel.app").replace(/\/$/, "");
const maxAttempts = Number(process.env.PRODUCTION_SMOKE_ATTEMPTS || 10);
const intervalMs = Number(process.env.PRODUCTION_SMOKE_INTERVAL_MS || 30000);

function check(condition, message) {
  if (!condition) throw new Error(message);
}

async function poll(label, fn) {
  let lastError;
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      if (attempt < maxAttempts) await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
  }
  throw new Error(`${label} failed after ${maxAttempts} attempts: ${lastError?.message || "unknown error"}`);
}

const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const consoleErrors = [];
page.on("console", (msg) => {
  if (msg.type() === "error") consoleErrors.push(msg.text());
});
page.on("pageerror", (error) => consoleErrors.push(error.message));

try {
  const data = await poll("public JSON fetch", async () => {
    const [business, news, meta, companies] = await Promise.all([
      page.request.get(`${baseUrl}/data/business.json`),
      page.request.get(`${baseUrl}/data/news.json`),
      page.request.get(`${baseUrl}/data/meta.json`),
      page.request.get(`${baseUrl}/data/companies/companies.json`),
    ]);
    check(business.ok(), "business JSON failed");
    check(news.ok(), "news JSON failed");
    check(meta.ok(), "meta JSON failed");
    check(companies.ok(), "companies JSON failed");
    return {
      business: await business.json(),
      news: await news.json(),
      meta: await meta.json(),
      companies: await companies.json(),
    };
  });

  const newsItems = Array.isArray(data.news.items) ? data.news.items : [];
  const businessItems = Array.isArray(data.business.items) ? data.business.items : [];
  check(newsItems.length > 0, "news JSON has no items");
  check(businessItems.length > 0, "business JSON has no items");
  check(data.meta.news_count === newsItems.length, "meta news count mismatch");
  check(data.meta.business_count === businessItems.length, "meta business count mismatch");
  const latestNews = newsItems
    .map((item) => Date.parse(item.published_at || ""))
    .filter((value) => Number.isFinite(value))
    .sort((a, b) => b - a)[0];
  check(Number.isFinite(latestNews), "latest news date missing");

  await poll("home route", async () => {
    await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
    await page.getByRole("heading", { name: /오늘 확인할 사업과\s*모듈러 시장 뉴스/ }).waitFor({ timeout: 10000 });
  });
  await page.goto(`${baseUrl}/news`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "모듈러 뉴스정보" }).waitFor();
  await page.goto(`${baseUrl}/business`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "모듈러 사업정보" }).waitFor();
  await page.goto(`${baseUrl}/companies`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "스틸 모듈러 기업정보" }).waitFor();
  const companyText = await page.locator("main").innerText();
  check(companyText.includes("전체 11개사"), "company count 11 missing");
  check(companyText.includes("건설사"), "contractor role label missing");
  check(companyText.includes("모듈러 제작 전문 업체"), "modular specialist role label missing");
  check(await page.locator(".company-quick-filters").count() === 0, "duplicate role quick filter visible");
  await page.goto(`${baseUrl}/companies/daeseung-engineering`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: /대승엔지니어링/ }).waitFor();
  const hiddenRoute = await page.request.get(`${baseUrl}/company-intelligence`, { maxRedirects: 0 });
  check([200, 301, 302, 404].includes(hiddenRoute.status()), "hidden route returned unexpected status");
  await page.goto(`${baseUrl}/definitely-not-a-real-route`, { waitUntil: "networkidle" });
  check((await page.locator("main").innerText()).includes("페이지를 찾을 수 없습니다."), "not-found route did not show expected message");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${baseUrl}/companies`, { waitUntil: "networkidle" });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  check(!overflow, "mobile horizontal overflow detected");
  check(consoleErrors.length === 0, `console errors detected: ${consoleErrors.slice(0, 3).join(" | ")}`);
  console.log(`PRODUCTION SMOKE PASSED: business=${businessItems.length}, news=${newsItems.length}, latestNews=${new Date(latestNews).toISOString()}, base=${baseUrl}`);
} finally {
  await browser.close();
}
