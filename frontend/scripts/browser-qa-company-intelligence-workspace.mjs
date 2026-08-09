import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(scriptDir, "..");
const viteBin = resolve(frontendRoot, "node_modules", "vite", "bin", "vite.js");

function check(condition, message) {
  if (!condition) throw new Error(message);
}

function getFreePort() {
  return new Promise((resolvePort, reject) => {
    const server = createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      server.close(() => resolvePort(address.port));
    });
  });
}

async function waitForServer(url, timeoutMs = 30000) {
  const startedAt = Date.now();
  let lastError = null;
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
      lastError = new Error(`HTTP ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, 500));
  }
  throw new Error(`Vite preview did not become ready at ${url}: ${lastError?.message || "timeout"}`);
}

async function stopProcess(child) {
  if (!child || child.exitCode !== null) return;
  await new Promise((resolveStop) => {
    child.once("exit", resolveStop);
    child.kill("SIGTERM");
    setTimeout(() => {
      if (child.exitCode === null) child.kill("SIGKILL");
    }, 3000).unref();
  });
}

async function hasPageOverflow(page) {
  return page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
}

async function clickTab(page, label) {
  const tab = page.locator(".company-tabs button:visible").filter({ hasText: label }).first();
  await tab.waitFor({ state: "visible", timeout: 5000 });
  await tab.click();
  await page.waitForTimeout(150);
}

async function openAndCloseEvidenceDrawer(page, buttonLocator, expectedText) {
  await buttonLocator.waitFor({ state: "visible", timeout: 5000 });
  await buttonLocator.click();
  const drawer = page.locator(".evidence-drawer");
  await drawer.waitFor({ state: "visible", timeout: 5000 });
  const drawerText = await drawer.innerText();
  check(drawerText.includes(expectedText), `evidence drawer missing ${expectedText}`);
  check(drawerText.includes("계산 기준") || drawerText.includes("실제 출처 수"), "evidence drawer missing calculation/source details");
  await page.keyboard.press("Escape");
  await drawer.waitFor({ state: "hidden", timeout: 5000 });
}

async function assertWorkspaceCompany(page, baseUrl, companyId, viewportWidth) {
  const diagnostics = { consoleErrors: [], reactWarnings: [] };
  page.on("console", (message) => {
    const text = message.text();
    if (message.type() === "error") diagnostics.consoleErrors.push(text);
    if (message.type() === "warning" && /React|Warning/i.test(text)) diagnostics.reactWarnings.push(text);
  });

  await page.goto(`${baseUrl}/companies/${companyId}`, { waitUntil: "networkidle" });
  check(await page.locator("#company-tab-panel-overview").isVisible(), `${companyId}: overview tab missing`);
  const overviewText = await page.locator("#company-tab-panel-overview").innerText();
  check(overviewText.includes("\uD3EC\uC9C0\uC158") && overviewText.includes("\uD575\uC2EC \uC7AC\uBB34 \uC2A4\uB0C5\uC0F7"), `${companyId}: decision summary missing`);
  if (companyId !== "gs-ec") {
    await openAndCloseEvidenceDrawer(page, page.locator("#company-tab-panel-overview .evidence-inline-button").first(), "\uACC4\uC0B0 \uAE30\uC900");
  }
  check(!(await hasPageOverflow(page)), `${companyId} ${viewportWidth}: overview overflow`);

  await clickTab(page, "재무");
  await page.reload({ waitUntil: "networkidle" });
  const financialText = await page.locator("#company-tab-panel-financial").innerText();
  if (companyId === "gs-ec") {
    check(financialText.includes("최근 재무") || financialText.includes("최근 3개년 재무"), `${companyId}: fallback financial UI missing`);
  } else {
    check(financialText.includes("의사결정 요약"), `${companyId}: audit decision summary missing`);
    check(financialText.includes("동료 비교"), `${companyId}: peer comparison missing`);
    check(financialText.includes("중앙값"), `${companyId}: peer median missing`);
    check(!financialText.includes("rule_id"), `${companyId}: raw health rule metadata should be hidden by default`);
    check(financialText.includes("재무 추세"), `${companyId}: financial trends missing`);
    if (companyId === "kumkang-kind") check(financialText.includes("비교 조건 미충족") || financialText.includes("임의 순위 없음"), `${companyId}: non-comparable peer state missing`);
    await openAndCloseEvidenceDrawer(page, page.locator("#company-tab-panel-financial .evidence-inline-button").first(), "\uACC4\uC0B0 \uAE30\uC900");
  }
  check(!(await hasPageOverflow(page)), `${companyId} ${viewportWidth}: financial overflow`);

  await clickTab(page, "근거·출처");
  await page.reload({ waitUntil: "networkidle" });
  const evidenceText = await page.locator("#company-tab-panel-evidence").innerText();
  check(evidenceText.includes("Data Trust Center"), `${companyId}: data trust center missing`);
  check(evidenceText.includes("출처 유형"), `${companyId}: source type counts missing`);
  await page.locator("details.evidence-secondary-details summary").click();
  const expandedEvidenceText = await page.locator("#company-tab-panel-evidence").innerText();
  check(expandedEvidenceText.includes("\uC601\uC5ED\uBCC4 \uAC80\uC99D \uB9E4\uD2B8\uB9AD\uC2A4"), `${companyId}: evidence matrix missing`);
  await openAndCloseEvidenceDrawer(page, page.locator("#company-tab-panel-evidence .evidence-inline-button").first(), "\uC2E4\uC81C \uCD9C\uCC98 \uC218");
  check(!(await hasPageOverflow(page)), `${companyId} ${viewportWidth}: evidence overflow`);

  check(diagnostics.consoleErrors.length === 0, `${companyId} ${viewportWidth}: console errors: ${diagnostics.consoleErrors.join("\n")}`);
  check(diagnostics.reactWarnings.length === 0, `${companyId} ${viewportWidth}: React warnings: ${diagnostics.reactWarnings.join("\n")}`);
}

async function runWorkspaceQa(baseUrl, viewport) {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport });
  try {
    for (const companyId of ["yuchang-enc", "kumkang-kind", "daeseung-engineering", "planm", "nrb", "gs-ec"]) {
      await assertWorkspaceCompany(page, baseUrl, companyId, viewport.width);
    }
  } finally {
    await browser.close();
  }
}

let preview = null;

try {
  let baseUrl = process.env.QA_BASE_URL;
  if (!baseUrl) {
    const port = await getFreePort();
    baseUrl = `http://127.0.0.1:${port}`;
    preview = spawn(
      process.execPath,
      [viteBin, "preview", "--host", "127.0.0.1", "--port", String(port), "--strictPort"],
      { cwd: frontendRoot, stdio: ["ignore", "pipe", "pipe"], shell: false },
    );
    preview.stdout.on("data", (chunk) => process.stdout.write(chunk));
    preview.stderr.on("data", (chunk) => process.stderr.write(chunk));
    await waitForServer(baseUrl);
  }

  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 390, height: 844 },
    { width: 320, height: 800 },
  ]) {
    await runWorkspaceQa(baseUrl, viewport);
  }
  console.log("COMPANY INTELLIGENCE WORKSPACE QA PASSED: 1440, 390, 320");
} finally {
  await stopProcess(preview);
}
