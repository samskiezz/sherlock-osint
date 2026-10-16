// Full owned workflow: real upload/extraction, unattended analysis, reading and tool execution.
import { chromium } from "playwright";
import assert from "node:assert/strict";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { createHash, randomBytes } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../", import.meta.url));
const output =
  process.env.SHERLOCK_BROWSER_REPORT_DIR ||
  path.join(root, "data/results-browser");
await mkdir(output, { recursive: true, mode: 0o700 });
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
const results = {
  scope: "Explicitly synthetic owned fixture; no historical case conclusion",
  errors: [],
  apiErrors: [],
};
try {
  const context = await browser.newContext({
    baseURL: process.env.SHERLOCK_BROWSER_URL || "http://127.0.0.1:8010",
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
  let page = await context.newPage();
  function observe(p) {
    p.on("pageerror", (e) => results.errors.push(e.message));
    p.on("response", (r) => {
      const u = new URL(r.url());
      if (u.pathname.startsWith("/api/") && r.status() >= 400)
        results.apiErrors.push({ path: u.pathname, status: r.status() });
    });
  }
  observe(page);
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page
    .getByRole("heading", { name: "Your case results", exact: true })
    .waitFor();
  assert.equal(
    await page.locator(".workspace-header h1").innerText(),
    "Case results",
  );
  const fixtureRun = randomBytes(5).toString("hex");
  const filename = `Owned synthetic results acceptance ${fixtureRun}.txt`;
  const text = `Owned synthetic research memo for workflow acceptance.\nFixture run: ${fixtureRun}.\nThe Example Project archive was recorded on 2026-10-16.\nContact workflow-fixture@example.org.\nReference US1234567B2.\nThis controlled fixture does not describe a real person or establish a case allegation.\nLiteral markup for display safety: <script>window.__resultsInjected = true</script>.\n`;
  const responsePromise = page.waitForResponse(
    (r) =>
      new URL(r.url()).pathname === "/api/upload" &&
      r.request().method() === "POST",
    { timeout: 240000 },
  );
  await page.locator(".results-intro input[type=file]").setInputFiles({
    name: filename,
    mimeType: "text/plain",
    buffer: Buffer.from(text),
  });
  const response = await responsePromise;
  assert.equal(response.status(), 200);
  const evidence = await response.json();
  assert.equal(evidence.metadata.processing_status, "COMPLETE");
  assert.equal(
    evidence.sha256,
    createHash("sha256").update(text).digest("hex"),
  );
  const immediate = await context.request.get(`/api/results/${evidence.id}`);
  assert.equal(immediate.status(), 200);
  const queued = await immediate.json();
  assert.ok(
    queued.run_id,
    "Extraction must immediately persist an automatic run",
  );
  results.immediate_analysis_dispatch = true;
  await page.close(); // Workers must finish while the UI is closed.
  let report;
  const started = Date.now();
  while (Date.now() - started < 300000) {
    report = await (
      await context.request.get(`/api/results/${evidence.id}`)
    ).json();
    if (["COMPLETE", "PARTIAL", "FAILED", "CANCELLED"].includes(report.state))
      break;
    await new Promise((r) => setTimeout(r, 2000));
  }
  assert.ok(
    ["COMPLETE", "PARTIAL"].includes(report.state),
    "Automatic analysis did not finish",
  );
  for (const tool of [
    "evidence.verify",
    "forensics.screen",
    "text.extractive_summary",
    "text.dates",
    "text.emails",
    "text.identifiers",
  ])
    assert.ok(
      report.checks.some((c) => c.tool === tool && c.status === "COMPLETE"),
      `${tool} needs a real saved output`,
    );
  assert.ok(
    report.information.some((v) =>
      JSON.stringify(v.value).includes("workflow-fixture@example.org"),
    ),
  );
  assert.ok(report.reading.length);
  assert.ok(
    report.reading.every((p) => text.slice(p.start, p.end) === p.quote),
  );
  results.unattended_analysis = {
    state: report.state,
    completed: report.progress.complete,
    failed: report.checks
      .filter((c) => c.status !== "COMPLETE")
      .map((c) => ({ tool: c.tool, status: c.status, reason: c.error })),
    seconds: (Date.now() - started) / 1000,
  };
  console.log(
    JSON.stringify({
      phase: "unattended-analysis",
      ...results.unattended_analysis,
    }),
  );
  page = await context.newPage();
  observe(page);
  await page.goto(`/?view=results&source=${evidence.id}`, {
    waitUntil: "domcontentloaded",
  });
  await page
    .getByRole("article", { name: "Source analysis report" })
    .getByRole("heading", { name: filename, exact: true })
    .waitFor();
  await page
    .getByRole("region", { name: "Source reading" })
    .waitFor()
    .catch(() => page.locator(".source-reading").waitFor());
  await page.locator(".source-reading").scrollIntoViewIfNeeded();
  assert.equal(await page.evaluate(() => window.__resultsInjected), undefined);
  const downloadPromise = page.waitForEvent("download");
  await page
    .getByRole("link", { name: "Download report", exact: true })
    .click();
  const download = await downloadPromise;
  const file = await download.path();
  const exported = await readFile(file, "utf8");
  assert.ok(
    exported.includes(evidence.sha256) &&
      exported.includes("workflow-fixture@example.org"),
  );
  results.report_download = true;
  await page.reload({ waitUntil: "domcontentloaded" });
  await page
    .locator(".source-notebook h2")
    .filter({ hasText: filename })
    .waitFor();
  results.bookmarked_source_survives_reload = true;
  await page.screenshot({ path: path.join(output, "results-source.png") });
  await page
    .getByRole("button", { name: "All tools for this source", exact: true })
    .click();
  await page
    .getByRole("heading", { name: "All tools and workspaces", exact: true })
    .waitFor();
  const directory = await (
    await context.request.get(`/api/results/tools?evidence_id=${evidence.id}`)
  ).json();
  await page.waitForFunction(
    (n) => document.querySelectorAll(".tool-directory > button").length === n,
    directory.tools.length,
  );
  assert.equal(
    await page.locator(".workspace-directory > button").count(),
    directory.workspaces.length,
  );
  results.exposed_tools = directory.tools.length;
  results.exposed_workspaces = directory.workspaces.length;
  await page
    .getByRole("textbox", { name: "Search all tools" })
    .fill("text.word_frequency");
  await page.locator(".tool-directory > button").first().click();
  const runResponse = page.waitForResponse(
    (r) =>
      new URL(r.url()).pathname === "/api/automation/run" &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Run selected tool", exact: true })
    .click();
  const requested = await runResponse;
  assert.equal(requested.status(), 200);
  const input = requested.request().postDataJSON();
  assert.equal(input.inputs.evidence_id, evidence.id);
  assert.equal(
    input.inputs.text,
    undefined,
    "Demo text must never silently replace the original",
  );
  await page
    .locator(".tool-live-result")
    .getByRole("heading", { name: "Analysis complete", exact: true })
    .waitFor({ timeout: 90000 });
  await page.locator(".tool-live-result .result-check summary").click();
  assert.ok(
    (await page.locator(".tool-live-result .result-check-body").innerText())
      .toLowerCase()
      .includes("workflow"),
  );
  results.callable_tool_with_real_source = true;
  assert.ok(new URL(page.url()).searchParams.get("run"));
  await page.reload({ waitUntil: "domcontentloaded" });
  await page
    .locator(".tool-live-result")
    .getByRole("heading", { name: "Analysis complete", exact: true })
    .waitFor({ timeout: 30000 });
  results.bookmarked_tool_output_survives_reload = true;
  await page.screenshot({ path: path.join(output, "tools-output.png") });
  const image = await page.evaluate(() => {
    const c = document.createElement("canvas");
    c.width = 128;
    c.height = 128;
    const g = c.getContext("2d");
    g.fillStyle = "#e6e3dc";
    g.fillRect(0, 0, 128, 128);
    g.fillStyle = "#304760";
    g.fillRect(16, 16, 42, 42);
    g.fillStyle = "#d69c63";
    g.beginPath();
    g.arc(88, 88, 24, 0, Math.PI * 2);
    g.fill();
    return c.toDataURL("image/png").split(",")[1];
  });
  const uploadedImage = await context.request.post("/api/upload", {
    timeout: 240000,
    multipart: {
      file: {
        name: "Owned synthetic geometry acceptance.png",
        mimeType: "image/png",
        buffer: Buffer.from(image, "base64"),
      },
    },
  });
  assert.equal(uploadedImage.status(), 200);
  const imageEvidence = await uploadedImage.json();
  let imageReport;
  for (let deadline = Date.now() + 300000; Date.now() < deadline; ) {
    imageReport = await (
      await context.request.get(`/api/results/${imageEvidence.id}`)
    ).json();
    if (["COMPLETE", "PARTIAL", "FAILED"].includes(imageReport.state)) break;
    await new Promise((r) => setTimeout(r, 2000));
  }
  for (const tool of [
    "evidence.verify",
    "forensics.screen",
    "visual.prepare",
    "visual.search",
  ]) {
    const check = imageReport.checks.find((c) => c.tool === tool);
    assert.equal(
      check?.status,
      "COMPLETE",
      `${tool} must have a readable source-bound image result`,
    );
    assert.ok(check.sources.length);
  }
  await page.goto(`/?view=results&source=${imageEvidence.id}`, {
    waitUntil: "domcontentloaded",
  });
  await page.locator(".result-source-preview").waitFor();
  await page.locator(".source-notebook").scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(output, "results-image.png") });
  results.source_bound_image_analysis = true;
  const mobile = await context.newPage();
  observe(mobile);
  await mobile.setViewportSize({ width: 390, height: 844 });
  await mobile.goto(`/?view=results&source=${evidence.id}`, {
    waitUntil: "domcontentloaded",
  });
  await mobile
    .locator(".source-notebook h2")
    .filter({ hasText: filename })
    .waitFor();
  await mobile.locator(".source-notebook").scrollIntoViewIfNeeded();
  const box = await mobile.locator(".source-notebook").boundingBox();
  assert.ok(
    box.x >= 0 && box.x + box.width <= 391,
    "Source reading must fit the mobile viewport",
  );
  await mobile.screenshot({ path: path.join(output, "results-mobile.png") });
  results.mobile_reading = true;
  const original = await context.request.get(
    `/api/evidence/${evidence.id}/file`,
  );
  assert.equal(
    createHash("sha256")
      .update(await original.body())
      .digest("hex"),
    evidence.sha256,
  );
  results.original_bytes_preserved = true;
  const all = await context.request.get("/api/results/report");
  assert.equal(all.status(), 200);
  assert.ok((await all.text()).includes(evidence.sha256));
  results.case_report_download = true;
  assert.deepEqual(results.errors, []);
  assert.deepEqual(results.apiErrors, []);
  results.status = "passed";
} catch (e) {
  results.status = "failed";
  results.failure = e.message;
  throw e;
} finally {
  await writeFile(
    path.join(output, "results-browser.json"),
    JSON.stringify(results, null, 2) + "\n",
    { mode: 0o600 },
  );
  await browser.close();
  console.log(JSON.stringify(results));
}
