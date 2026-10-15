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
await page.locator(".run-selector select").selectOption("INV-62400e14639d");
await page.getByRole("button", { name: "Attach proposal to board" }).waitFor();
await page.getByTitle("Toggle inspector").click();
await page
  .getByRole("button", { name: "Attach proposal to board" })
  .scrollIntoViewIfNeeded();
await page.screenshot({
  path: "../artifacts/local-model-finding.png",
  fullPage: true,
});
await page.getByRole("button", { name: "Attach proposal to board" }).click();
await page.waitForSelector(".react-flow");
const proposal = page
  .locator(".react-flow__node")
  .filter({ hasText: "The two names listed under Inventor" });
await proposal.waitFor();
const state = await (
  await page.request.get("http://127.0.0.1:8000/api/boards/looking-glass")
).json();
const edge = state.edges.find((e) => e.id.includes("HYP-62400e14639d-0"));
if (edge?.data.state !== "HYPOTHESIS")
  throw new Error("Proposal became a factual edge");
await page.getByRole("button", { name: "Fit board", exact: true }).click();
await page.waitForTimeout(700);
await page.screenshot({
  path: "../artifacts/model-proposal-board.png",
  fullPage: true,
});
await page.reload();
await page.waitForSelector(".evidence-card");
if (
  !(await page.locator(".react-flow").innerText()).includes(
    "The two names listed under Inventor",
  )
)
  throw new Error("Proposal did not persist");
console.log(
  JSON.stringify(
    {
      realLocalModelRun: "INV-62400e14639d",
      proposalAttachment: "passed",
      hypothesisState: "passed",
      reloadPersistence: "passed",
      browserErrors: errors,
    },
    null,
    2,
  ),
);
await browser.close();
if (errors.length) process.exit(1);
