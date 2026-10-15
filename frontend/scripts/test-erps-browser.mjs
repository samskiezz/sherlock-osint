// Requires the running authenticated gateway and a labeled synthetic ERPS fixture.
// Credentials are read privately; they are never included in the output report.
import { chromium } from "playwright";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import assert from "node:assert/strict";
const root = fileURLToPath(new URL("../../", import.meta.url));
const baseURL = process.env.SHERLOCK_BROWSER_URL || "http://127.0.0.1:8010";
const reportDir = path.join(root, "data/onboarding-validation");
await mkdir(reportDir, { recursive: true });
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH || "/usr/bin/chromium",
  headless: true,
  args: ["--no-sandbox"],
});
try {
  const context = await browser.newContext({
    baseURL,
    viewport: { width: 1440, height: 1000 },
  });
  const credentials = JSON.parse(
    await readFile(
      process.env.SHERLOCK_BROWSER_AUTH_FILE ||
        path.join(root, "data/foundation-secrets/admin-login.json"),
      "utf8",
    ),
  );
  const login = await context.request.post("/api/v1/auth/login", {
    data: credentials,
  });
  assert.equal(login.status(), 200, "gateway authentication");
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page
    .getByRole("button", { name: "Entity resolution", exact: true })
    .click();
  await page.getByText("Service connected", { exact: true }).waitFor();
  await page.getByLabel("Search entities", { exact: true }).fill("Avery Quinn");
  await page
    .locator(".erps-toolbar")
    .getByRole("button", { name: "Search", exact: true })
    .click();
  await page
    .locator(".erps-list button")
    .filter({ hasText: "Avery Quinn" })
    .first()
    .click();
  await page
    .getByRole("heading", { name: "Supporting evidence", exact: true })
    .waitFor();
  await page
    .getByRole("heading", { name: "Witness sets", exact: true })
    .waitFor();
  assert.ok(await page.locator(".erps-witness").count());
  assert.ok(await page.locator(".erps-mention").count());
  const evidence = page.getByLabel("Evidence source", { exact: true });
  const fixture = evidence
    .locator("option")
    .filter({ hasText: "ERPS synthetic acceptance.txt" })
    .first();
  await evidence.selectOption(await fixture.getAttribute("value"));
  await page.getByRole("button", { name: "Index source", exact: true }).click();
  await page
    .getByText("Source indexed. Entity list refreshed.", { exact: true })
    .waitFor({ timeout: 30000 });
  await page.evaluate(() => {
    for (const el of document.querySelectorAll("*")) {
      if (el.scrollTop) el.scrollTop = 0;
    }
  });
  await page.screenshot({
    path: path.join(reportDir, "erps-browser.png"),
    fullPage: true,
  });
  const response = await context.request.post("/api/erps/resolve", {
    data: { mentions: [{ nonsense: true }] },
  });
  assert.equal(
    response.status(),
    422,
    "invalid structured mentions retain their client error status through the proxy",
  );
  await page.goto("/?view=entities", { waitUntil: "domcontentloaded" });
  await page.getByText("Service connected", { exact: true }).waitFor();
  assert.deepEqual(errors, []);
  const report = {
    navigation: true,
    deep_link: true,
    service_connected: true,
    search: true,
    entity_inspection: true,
    lineage: true,
    source_index: true,
    invalid_request_status: response.status(),
    page_errors: errors,
  };
  await writeFile(
    path.join(reportDir, "erps-browser.json"),
    JSON.stringify(report, null, 2),
    { mode: 0o600 },
  );
  console.log(JSON.stringify(report));
} finally {
  await browser.close();
}
