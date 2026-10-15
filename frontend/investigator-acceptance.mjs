import { chromium } from "playwright";
const browser = await chromium.launch({
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
const page = await browser.newPage({ viewport: { width: 1700, height: 1100 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
await page.goto("http://127.0.0.1:8000", { waitUntil: "domcontentloaded" });
await page.waitForSelector(".evidence-card");
await page.getByRole("button", { name: "Investigator", exact: true }).click();
await page.getByRole("heading", { name: "Investigation control" }).waitFor();
const responsePromise = page.waitForResponse(
  (r) =>
    r.url().endsWith("/api/investigations") && r.request().method() === "POST",
);
await page.getByRole("button", { name: "Start investigation" }).click();
const created = await (await responsePromise).json();
await page.waitForFunction(
  (id) =>
    document
      .querySelector(".investigation-heading h3")
      ?.textContent?.includes(id) &&
    document.querySelector(".investigation-heading .status")?.textContent ===
      "COMPLETE",
  created.id,
);
await page
  .locator(".audit-results .citation")
  .first()
  .waitFor({ timeout: 20000 });
await page.waitForFunction(
  () =>
    [...document.querySelectorAll(".agent-task .status")].filter(
      (el) => el.textContent === "COMPLETE",
    ).length === 7,
);
const tasks = await page.locator(".agent-task").count();
if (tasks !== 7) throw new Error("Expected seven persisted task stages");
await page.getByTitle("Toggle inspector").click();
await page.locator(".agent-tasks").scrollIntoViewIfNeeded();
await page.waitForTimeout(600);
await page.screenshot({
  path: "../artifacts/investigator-control.png",
  fullPage: true,
});
await page
  .locator(".agent-task")
  .filter({ hasText: "Evidence Auditor" })
  .locator("summary")
  .click();
if (
  !(await page.locator(".agent-task[open]").innerText()).includes(
    "Exact quote matching",
  )
)
  throw new Error("No citation audit output");
await page.locator(".agent-task[open] pre").scrollIntoViewIfNeeded();
await page.screenshot({
  path: "../artifacts/investigator-audit-detail.png",
  fullPage: true,
});
const runId = (
  await page.locator(".investigation-heading h3").innerText()
).split(" ")[0];
await page.reload();
await page.waitForSelector(".evidence-card");
await page.getByRole("button", { name: "Investigator", exact: true }).click();
await page.locator(".audit-results").waitFor();
if (!(await page.locator(".investigation-heading").innerText()).includes(runId))
  throw new Error("Investigator result lost after reload");
console.log(
  JSON.stringify(
    {
      persistentInvestigation: "passed",
      sevenCompletedStages: "passed",
      actualSourcePassages: "passed",
      citationAudit: "passed",
      reloadRecovery: "passed",
      browserErrors: errors,
      runId,
    },
    null,
    2,
  ),
);
await browser.close();
if (errors.length) process.exit(1);
