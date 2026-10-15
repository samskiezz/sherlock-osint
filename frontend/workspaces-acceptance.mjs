import { chromium } from "playwright";
import fs from "node:fs/promises";
const browser = await chromium.launch({
  headless: true,
  args: [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
  ],
});
const page = await browser.newPage({ viewport: { width: 1720, height: 1100 } }),
  errors = [];
page.on("pageerror", (e) => errors.push(e.message));
await page.goto("http://127.0.0.1:8000", { waitUntil: "domcontentloaded" });
await page.waitForSelector(".evidence-card");
await page.getByRole("button", { name: "Chronology", exact: true }).click();
await page
  .getByRole("button", {
    name: "Caltech publishes Tridroid Cup report",
    exact: true,
  })
  .first()
  .click();
await page.locator(".temporal-detail").waitFor();
const before = await page.locator(".lab-toolbar .eyebrow").innerText();
await page.getByRole("button", { name: "Zoom in", exact: true }).click();
if (before === (await page.locator(".lab-toolbar .eyebrow").innerText()))
  throw Error("Timeline zoom failed");
await page.screenshot({
  path: "../artifacts/source-chronology-v3.png",
  fullPage: true,
});
await page
  .getByRole("button", { name: "Geospatial intelligence", exact: true })
  .click();
await page.locator(".sourced-map-marker").waitFor();
await page.locator(".sourced-map-marker").click();
await page.locator(".temporal-detail").waitFor();
await page.waitForTimeout(1600);
if (await page.locator(".map-workspace .notice").count())
  throw Error(await page.locator(".map-workspace .notice").innerText());
await page.screenshot({
  path: "../artifacts/sourced-map-v3.png",
  fullPage: true,
});
await page
  .getByRole("button", { name: "Graph intelligence", exact: true })
  .click();
await page.locator(".analysis-node").first().waitFor();
const graph = await (
    await page.request.get(
      "http://127.0.0.1:8000/api/graph/looking-glass?documented_only=true",
    )
  ).json(),
  edge = graph.edges[0],
  selects = page.locator(".graph-workspace .lab-toolbar select");
await selects.nth(0).selectOption(edge.source);
await selects.nth(1).selectOption(edge.target);
await page.getByRole("button", { name: "Shortest path", exact: true }).click();
await page
  .locator(".analysis-message")
  .filter({ hasText: "1 relationship steps" })
  .waitFor();
await page.screenshot({
  path: "../artifacts/network-analysis-v3.png",
  fullPage: true,
});
await page
  .getByRole("button", {
    name: "Patent provenance · inventors & original",
    exact: true,
  })
  .click();
await page.waitForTimeout(500);
await page
  .locator(".react-flow__node")
  .filter({ hasText: "Monica A. Jacinto · patent inventor" })
  .click();
await page.locator(".inspector .citation").click();
await page.locator(".pdf-paper canvas").waitFor();
await page
  .getByRole("textbox", { name: "Search preserved PDF" })
  .fill("Monica A. Jacinto");
await page
  .locator(".pdf-search-results")
  .getByRole("button", { name: "Page 1", exact: true })
  .click();
await page.locator(".pdf-passage-highlight").first().waitFor();
await page.getByRole("button", { name: "Next PDF page", exact: true }).click();
if (
  (await page
    .getByRole("spinbutton", { name: "PDF page number" })
    .inputValue()) !== "2"
)
  throw Error("PDF navigation failed");
await page
  .getByRole("button", { name: "Previous PDF page", exact: true })
  .click();
const resize = page.getByRole("separator", {
  name: "Resize evidence inspector",
});
await resize.focus();
await resize.press("ArrowLeft");
await page.locator('.pdf-paper canvas[data-rendered="1"]').waitFor();
const ink = await page.locator(".pdf-paper canvas").evaluate((c) => {
  const pixels = c.getContext("2d").getImageData(0, 0, c.width, c.height).data;
  let dark = 0;
  for (let i = 0; i < pixels.length; i += 4)
    if (pixels[i] < 120 && pixels[i + 1] < 120 && pixels[i + 2] < 120) dark++;
  return dark;
});
if (ink < 1000) throw Error("PDF canvas lacks actual document content");
await page.screenshot({
  path: "../artifacts/pdf-passage-inspector-v3.png",
  fullPage: true,
});
await page.locator(".case-box").click();
await page.getByRole("button", { name: "Claim review", exact: true }).click();
await page
  .getByRole("button", { name: "Propose relationship", exact: true })
  .click();
const form = page.locator(".lab-form");
await form.locator("select").nth(0).selectOption("report");
await form.locator("select").nth(1).selectOption("photo");
await form.locator("input").fill("Labels photograph");
await form
  .locator("textarea")
  .nth(0)
  .fill(
    "The Caltech institutional report labels the team photograph as members of Blitzkrieg Bots; it does not name individual people.",
  );
await form.locator("select").nth(2).selectOption("EV-613c677375a0");
await form.locator("textarea").nth(1).fill("Members of team Blitzkrieg Bots.");
await form.getByRole("button", { name: "Submit for review" }).click();
await page
  .locator(".review-card")
  .filter({ hasText: "The Caltech institutional report labels" })
  .first()
  .waitFor();
await page.screenshot({
  path: "../artifacts/claim-review-v3.png",
  fullPage: true,
});
const savedWidth = await page
  .locator(".inspector")
  .evaluate((e) => e.getBoundingClientRect().width);
await page.reload();
await page.waitForSelector(".evidence-card");
if (
  savedWidth !==
  (await page
    .locator(".inspector")
    .evaluate((e) => e.getBoundingClientRect().width))
)
  throw Error("Inspector width lost");
const results = {
  timeline: "zoom and cited event passed",
  map: "offline MapLibre and sourced institutional pin passed",
  graph: "verified shortest path passed",
  pdf: "actual pages, text search and coordinates passed",
  claim: "proposal saved; remains REVIEW REQUIRED",
  inspector: "resize persists",
  browserErrors: errors,
};
await fs.writeFile(
  "../artifacts/workspaces-browser-results-v3.json",
  JSON.stringify(results, null, 2),
);
console.log(JSON.stringify(results));
await browser.close();
if (errors.length) process.exit(1);
