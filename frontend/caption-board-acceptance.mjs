import { chromium } from "playwright";
import { writeFile } from "node:fs/promises";
const b = await chromium.launch({
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
const p = await b.newPage({ viewport: { width: 1800, height: 1200 } });
const errors = [];
p.on("pageerror", (e) => errors.push(e.message));
await p.goto("http://127.0.0.1:8000", { waitUntil: "domcontentloaded" });
await p
  .getByRole("button", {
    name: "Caltech robotics · named primary record",
    exact: true,
  })
  .click();
await p
  .locator(".evidence-card")
  .filter({ hasText: "Cole Allen · name in 2016 Caltech caption" })
  .click();
await p.locator(".inspector .citation").first().click();
await p.locator('.pdf-paper canvas[data-rendered="11"]').waitFor();
await p.waitForFunction(() =>
  document.querySelector(".inspector")?.textContent?.includes("11"),
);
await p.locator(".sidebar").evaluate((e) => {
  e.scrollTop = 0;
});
await p.screenshot({
  path: "../artifacts/caltech-primary-caption-board-v6.png",
  fullPage: true,
});
await writeFile(
  "../artifacts/caption-board-browser-v6.json",
  JSON.stringify(
    {
      errors,
      source: "actual 40-page Caltech original PDF",
      citationPage: 11,
      identityMerge: "none",
      inspector: "rendered real source page",
    },
    null,
    2,
  ),
);
await b.close();
if (errors.length) throw Error(errors.join("\n"));
