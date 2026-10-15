import { chromium } from "playwright";
const browser = await chromium.launch({
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
const page = await browser.newPage({ viewport: { width: 1600, height: 1050 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
await page.goto("http://127.0.0.1:8000", { waitUntil: "domcontentloaded" });
await page.waitForSelector(".evidence-card");
// Drag an actual photograph, then confirm the persisted API layout.
const node = page
  .locator(".react-flow__node")
  .filter({ hasText: "Caltech · Blitzkrieg Bots team photograph" });
const before = await (
  await page.request.get("http://127.0.0.1:8000/api/boards/looking-glass")
).json();
const box = await node.boundingBox();
await page.mouse.move(box.x + 70, box.y + 18);
await page.mouse.down();
await page.mouse.move(box.x + 120, box.y + 55, { steps: 15 });
await page.mouse.up();
await page.waitForTimeout(1000);
const after = await (
  await page.request.get("http://127.0.0.1:8000/api/boards/looking-glass")
).json();
if (
  JSON.stringify(before.nodes.find((n) => n.id === "photo").position) ===
  JSON.stringify(after.nodes.find((n) => n.id === "photo").position)
)
  throw new Error("Drag did not persist");
// Reload and inspect actual bytes, provenance and a relationship.
await page.reload();
await page.waitForSelector(".evidence-card");
const reloaded = await (
  await page.request.get("http://127.0.0.1:8000/api/boards/looking-glass")
).json();
if (
  JSON.stringify(after.nodes.find((n) => n.id === "photo").position) !==
  JSON.stringify(reloaded.nodes.find((n) => n.id === "photo").position)
)
  throw new Error("Reload lost layout");
await page.getByRole("button", { name: "provenance", exact: true }).click();
if (!(await page.locator(".inspector-scroll").innerText()).includes("SHA-256"))
  throw new Error("No hash inspector");
await page.getByRole("button", { name: "original", exact: true }).click();
await page.screenshot({
  path: "../artifacts/evidence-board.png",
  fullPage: true,
});
await page
  .getByRole("button", { name: "Graph intelligence", exact: true })
  .click();
await page
  .locator(".analysis-canvas .react-flow__edge-interaction")
  .first()
  .click({ force: true });
if (
  !(await page.locator(".inspector").innerText()).includes(
    "Supporting originals",
  )
)
  throw new Error("Relationship inspector unavailable");
await page
  .getByRole("button", {
    name: "Patent provenance · inventors & original",
    exact: true,
  })
  .click();
await page.waitForTimeout(600);
await page
  .locator(".react-flow__node")
  .filter({ hasText: "Monica A. Jacinto · patent inventor" })
  .click();
await page.locator(".inspector .citation").click();
await page.locator('.pdf-paper canvas[data-rendered="1"]').waitFor();
await page.screenshot({
  path: "../artifacts/patent-inspector.png",
  fullPage: true,
});
await page
  .getByRole("button", { name: "Continuous watch", exact: true })
  .click();
await page.getByRole("heading", { name: "Continuous discovery" }).waitFor();
await page.screenshot({
  path: "../artifacts/continuous-watch.png",
  fullPage: true,
});
console.log(
  JSON.stringify(
    {
      dragPersistence: "passed",
      reloadPersistence: "passed",
      hashInspector: "passed",
      relationshipInspector: "passed",
      personToOriginalPaper: "passed",
      browserErrors: errors,
    },
    null,
    2,
  ),
);
await browser.close();
if (errors.length) process.exit(1);
