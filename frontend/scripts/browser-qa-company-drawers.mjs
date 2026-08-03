import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(scriptDir, "..");
const viteBin = resolve(frontendRoot, "node_modules", "vite", "bin", "vite.js");
const k = (...codes) => String.fromCharCode(...codes);
const labels = {
  production: k(0xC0DD, 0xC0B0, 0xC2DC, 0xC124),
  projects: k(0xD504, 0xB85C, 0xC81D, 0xD2B8),
  technology: k(0xAE30, 0xC220, 0x00B7, 0xD2B9, 0xD5C8),
  financial: k(0xC7AC, 0xBB34),
  detail: k(0xC0C1, 0xC138, 0xBCF4, 0xAE30),
  evidence: k(0xADFC, 0xAC70, 0xBCF4, 0xAE30),
  registrationNumber: k(0xB4F1, 0xB85D, 0x00B7, 0xCD9C, 0xC6D0, 0xBC88, 0xD638),
  status: k(0xC0C1, 0xD0DC),
  technologyField: k(0xAE30, 0xC220, 0x20, 0xBD84, 0xC57C),
  latestFinancial: k(0xCD5C, 0xADFC, 0x20, 0xC7AC, 0xBB34),
  threeYearFinancial: k(0xCD5C, 0xADFC, 0x20, 0x0033, 0xAC1C, 0xB144, 0x20, 0xC7AC, 0xBB34),
};

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

async function hasDrawerOverflow(page) {
  return page.evaluate(() => {
    const drawer = document.querySelector(".company-entity-drawer, .evidence-drawer");
    return Boolean(drawer && drawer.scrollWidth > drawer.clientWidth + 1);
  });
}

async function assertModalIsolation(page, label) {
  const state = await page.evaluate(() => ({
    rootInert: document.getElementById("root")?.inert === true,
    rootHidden: document.getElementById("root")?.getAttribute("aria-hidden"),
    bodyOverflow: document.body.style.overflow,
    activeInsideDrawer: Boolean(document.activeElement?.closest(".company-entity-drawer")),
    activeTag: document.activeElement?.tagName,
    activeId: document.activeElement?.id,
    drawerWordBreak: getComputedStyle(document.querySelector(".company-entity-drawer")).wordBreak,
    drawerHasDialog: Boolean(document.querySelector("[role='dialog'][aria-modal='true']")),
  }));
  check(state.drawerHasDialog, `${label}: dialog semantics missing`);
  check(state.rootInert, `${label}: app root should be inert`);
  check(state.rootHidden === "true", `${label}: app root should be aria-hidden`);
  check(state.bodyOverflow === "hidden", `${label}: body scroll should be locked`);
  check(state.activeInsideDrawer, `${label}: focus should start inside drawer`);
  check(state.activeTag === "H2", `${label}: initial focus should land on drawer title`);
  check(state.drawerWordBreak !== "break-all", `${label}: drawer should not force one-character wrapping`);
  check(!(await hasPageOverflow(page)), `${label}: page has horizontal overflow`);
  check(!(await hasDrawerOverflow(page)), `${label}: drawer has horizontal overflow`);
}

async function assertIsolationRestored(page, label) {
  const state = await page.evaluate(() => ({
    rootInert: document.getElementById("root")?.inert === true,
    rootHidden: document.getElementById("root")?.getAttribute("aria-hidden"),
    bodyOverflow: document.body.style.overflow,
    activeText: document.activeElement?.textContent?.trim() || "",
    entityDrawerCount: document.querySelectorAll(".company-entity-drawer").length,
  }));
  check(!state.rootInert, `${label}: app root inert should be restored`);
  check(state.rootHidden === null, `${label}: aria-hidden should be restored`);
  check(state.bodyOverflow !== "hidden", `${label}: body scroll lock should be restored`);
  check(state.entityDrawerCount === 0, `${label}: entity drawer should be unmounted`);
  check(state.activeText.includes(labels.detail), `${label}: focus should return to original detail button`);
}

async function clickTab(page, name) {
  const tab = page.locator(".company-tabs button:visible").filter({ hasText: name }).first();
  await tab.waitFor({ state: "visible", timeout: 5000 });
  await tab.click();
  await page.waitForTimeout(150);
}

async function openFirstEntityDrawer(page) {
  const button = page.locator("button:visible").filter({ hasText: labels.detail }).first();
  await button.waitFor({ state: "visible", timeout: 5000 });
  await button.click();
  const dialog = page.getByRole("dialog");
  await dialog.waitFor({ state: "visible", timeout: 5000 });
  return button;
}

async function assertFocusTrap(page, label) {
  await page.keyboard.press("Tab");
  check(await page.evaluate(() => Boolean(document.activeElement?.closest(".company-entity-drawer"))), `${label}: Tab escaped drawer`);
  await page.keyboard.press("Shift+Tab");
  check(await page.evaluate(() => Boolean(document.activeElement?.closest(".company-entity-drawer"))), `${label}: Shift+Tab escaped drawer`);
}

async function closeWithEscape(page, label) {
  await page.keyboard.press("Escape");
  await page.locator(".company-entity-drawer").waitFor({ state: "hidden", timeout: 5000 });
  await assertIsolationRestored(page, `${label} escape close`);
}

async function closeWithBackdrop(page, label, viewportWidth) {
  if (viewportWidth < 700) return;
  await page.mouse.click(12, 12);
  await page.locator(".company-entity-drawer").waitFor({ state: "hidden", timeout: 5000 });
  await assertIsolationRestored(page, `${label} backdrop close`);
}

async function openEvidenceFromEntityDrawer(page, label) {
  const evidenceButton = page.locator(".company-entity-drawer button:visible").filter({ hasText: labels.evidence }).first();
  await evidenceButton.waitFor({ state: "visible", timeout: 5000 });
  await evidenceButton.click();
  await page.locator(".company-entity-drawer").waitFor({ state: "hidden", timeout: 5000 });
  const evidenceDrawer = page.locator(".evidence-drawer");
  await evidenceDrawer.waitFor({ state: "visible", timeout: 5000 });
  check(await page.locator(".company-entity-drawer").count() === 0, `${label}: entity drawer should not remain under evidence drawer`);
  check(await page.evaluate(() => document.body.style.overflow === "hidden"), `${label}: evidence drawer should lock body scroll`);
  await page.keyboard.press("Escape");
  await evidenceDrawer.waitFor({ state: "hidden", timeout: 5000 });
  check(await page.evaluate(() => document.body.style.overflow !== "hidden"), `${label}: evidence drawer should restore body scroll`);
  check(await page.evaluate((detailText) => document.activeElement?.textContent?.trim().includes(detailText), labels.detail), `${label}: evidence close should restore original detail focus`);
}

async function runCompanyDrawerQa(baseUrl, viewport) {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport });
  const diagnostics = { consoleErrors: [], reactWarnings: [] };
  page.on("console", (message) => {
    const text = message.text();
    if (message.type() === "error") diagnostics.consoleErrors.push(text);
    if (message.type() === "warning" && /React|Warning/i.test(text)) diagnostics.reactWarnings.push(text);
  });
  try {
    await page.goto(`${baseUrl}/companies/kumkang-kind`, { waitUntil: "networkidle" });
    await clickTab(page, labels.production);
    check(await page.locator(".company-detail-table details, table details").count() === 0, `${viewport.width}: table row details should not exist`);
    await openFirstEntityDrawer(page);
    await assertModalIsolation(page, `${viewport.width} production`);
    await assertFocusTrap(page, `${viewport.width} production`);
    await closeWithEscape(page, `${viewport.width} production`);
    await openFirstEntityDrawer(page);
    await closeWithBackdrop(page, `${viewport.width} production`, viewport.width);
    if (viewport.width < 700) await closeWithEscape(page, `${viewport.width} production mobile second close`);

    await page.goto(`${baseUrl}/companies/yuchang-enc`, { waitUntil: "networkidle" });
    await clickTab(page, labels.projects);
    await openFirstEntityDrawer(page);
    await assertModalIsolation(page, `${viewport.width} project`);
    check((await page.getByRole("dialog").innerText()).includes(labels.projects), `${viewport.width}: project status/title text missing`);
    await openEvidenceFromEntityDrawer(page, `${viewport.width} project evidence`);

    await page.goto(`${baseUrl}/companies/nrb`, { waitUntil: "networkidle" });
    await clickTab(page, labels.technology);
    await openFirstEntityDrawer(page);
    await assertModalIsolation(page, `${viewport.width} technology`);
    const technologyText = await page.getByRole("dialog").innerText();
    check(technologyText.includes(labels.registrationNumber), `${viewport.width}: technology registration number missing`);
    check(technologyText.includes(labels.status), `${viewport.width}: technology status missing`);
    check(technologyText.includes(labels.technologyField), `${viewport.width}: technology field missing`);
    await openEvidenceFromEntityDrawer(page, `${viewport.width} technology evidence`);

    await page.goto(`${baseUrl}/companies/gs-ec`, { waitUntil: "networkidle" });
    await clickTab(page, labels.financial);
    const financialText = await page.locator("#company-tab-panel-financial").innerText();
    check(financialText.includes(labels.latestFinancial) || financialText.includes(labels.threeYearFinancial), `${viewport.width}: fallback financial UI missing`);
    check(!(await hasPageOverflow(page)), `${viewport.width}: fallback financial page overflow`);

    check(diagnostics.consoleErrors.length === 0, `${viewport.width}: console errors: ${diagnostics.consoleErrors.join("\n")}`);
    check(diagnostics.reactWarnings.length === 0, `${viewport.width}: React warnings: ${diagnostics.reactWarnings.join("\n")}`);
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
    await runCompanyDrawerQa(baseUrl, viewport);
  }
  console.log("COMPANY DRAWER BROWSER QA PASSED: 1440, 390, 320");
} finally {
  await stopProcess(preview);
}
