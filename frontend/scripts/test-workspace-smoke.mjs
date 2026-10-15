// Authenticated navigation smoke test against the owned running workspace.
// It opens every current navigation view and never clicks analysis/write controls.
import { chromium } from "playwright";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import assert from "node:assert/strict";

const root = fileURLToPath(new URL("../../", import.meta.url));
const baseURL = process.env.SHERLOCK_BROWSER_URL || "http://127.0.0.1:8010";
const reportDir =
  process.env.SHERLOCK_BROWSER_REPORT_DIR ||
  path.join(root, "data/workspace-smoke");
await mkdir(reportDir, { recursive: true, mode: 0o700 });
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH || "/usr/bin/chromium",
  headless: true,
  args: [
    "--no-sandbox",
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
  ],
});
const errors = [],
  apiErrors = [],
  writes = [],
  resourceFailures = [],
  views = [];
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
  assert.equal(
    (
      await context.request.post("/api/v1/auth/login", { data: credentials })
    ).status(),
    200,
  );
  const page = await context.newPage();
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("response", (response) => {
    const url = new URL(response.url());
    if (url.pathname.startsWith("/api/") && response.status() >= 400)
      apiErrors.push({ path: url.pathname, status: response.status() });
  });
  page.on("request", (request) => {
    if (!["GET", "HEAD", "OPTIONS"].includes(request.method()))
      writes.push({
        method: request.method(),
        path: new URL(request.url()).pathname,
      });
  });
  page.on("requestfailed", (request) => {
    const url = new URL(request.url());
    resourceFailures.push({
      origin: url.origin,
      path: url.pathname,
      error: request.failure()?.errorText,
    });
  });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.locator(".workspace-header h1").waitFor();
  await page.locator(".advanced-nav-toggle").click();
  const labels = [
    ...new Set(
      await page
        .locator(".sidebar nav button")
        .evaluateAll((buttons) =>
          buttons
            .map((button) => button.querySelector("span")?.textContent?.trim())
            .filter(Boolean),
        ),
    ),
  ];
  assert.ok(
    labels.length >= 20,
    "Current specialist navigation was not enumerated",
  );
  for (const [index, label] of labels.entries()) {
    await page
      .locator(".sidebar nav button")
      .filter({ hasText: label })
      .first()
      .click();
    await page.waitForFunction(
      (expected) =>
        document.querySelector(".workspace-header h1")?.textContent ===
        expected,
      label,
    );
    await page.waitForTimeout(500);
    assert.equal(await page.locator(".workspace-header h1").innerText(), label);
    views.push({ label, header_rendered: true });
    await page.screenshot({
      path: path.join(
        reportDir,
        `view-${String(index + 1).padStart(2, "0")}.png`,
      ),
    });
  }
  await page.waitForTimeout(1000);
  const unexpectedWrites = writes.filter(
    (item) =>
      !(item.method === "PUT" && /^\/api\/boards\/[^/]+$/.test(item.path)),
  );
  const result = {
    views,
    view_count: views.length,
    page_errors: errors,
    api_error_routes: apiErrors,
    resource_failures: resourceFailures,
    write_requests: writes,
    unexpected_writes: unexpectedWrites,
    scope:
      "Navigation/rendering smoke only; unavailable providers, basemap assets and missing case originals remain explicit.",
  };
  await writeFile(
    path.join(reportDir, "workspace-smoke.json"),
    JSON.stringify(result, null, 2),
    { mode: 0o600 },
  );
  assert.deepEqual(errors, [], "Browser exceptions were observed");
  assert.deepEqual(
    unexpectedWrites,
    [],
    "Navigation initiated an unexpected write",
  );
  console.log(
    JSON.stringify({
      view_count: views.length,
      page_errors: errors,
      api_error_routes: apiErrors,
      resource_failures: resourceFailures.length,
      unexpected_writes: unexpectedWrites,
    }),
  );
} finally {
  await browser.close();
}
