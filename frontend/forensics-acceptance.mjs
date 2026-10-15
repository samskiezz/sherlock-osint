import { chromium } from "playwright";
import { writeFile } from "node:fs/promises";
const browser = await chromium.launch({
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
const page = await browser.newPage({ viewport: { width: 1600, height: 1100 } }),
  errors = [];
page.on("pageerror", (e) => errors.push(e.message));
await page.goto("http://127.0.0.1:8000", { waitUntil: "domcontentloaded" });
await page
  .getByRole("button", { name: "Cipher laboratory", exact: true })
  .click();
await page
  .getByRole("heading", { name: "Cipher & digital forensics laboratory" })
  .waitFor();
await page.getByRole("button", { name: "Run & preserve experiment" }).click();
await page.locator(".experiment-result").waitFor();
if (
  !(await page.locator(".experiment-result").innerText()).includes("Cole Allen")
)
  throw Error("Known hexadecimal decode failed");
await page.getByLabel("Transformation · 52 methods").selectOption("scrabble");
await page.getByLabel("Exact original input").fill("listen");
await page.getByLabel("Unrelated negative control").fill("zzzzzz");
await page.getByRole("checkbox").check();
await page.getByRole("button", { name: "Run & preserve experiment" }).click();
await page.waitForFunction(() =>
  document.querySelector(".experiment-result")?.textContent?.includes("silent"),
);
await page.locator(".page-scroll").evaluate(e => {e.scrollTop = 0;});
await page.screenshot({
  path: "../artifacts/cipher-word-puzzles-v6.png",
  fullPage: true,
});
await page
  .getByRole("button", { name: "Image diagnostics", exact: true })
  .click();
const photo = await page.getByLabel("Preserved image").locator("option").evaluateAll(options => options.find(o => o.textContent.includes("Caltech"))?.value);
if (photo) await page.getByLabel("Preserved image").selectOption(photo);
await page.getByLabel("Inspection view").selectOption("ela");
await page.waitForFunction(() => {
  const i = document.querySelector(".diagnostic-image img");
  return i?.complete && i?.naturalWidth > 0;
});
await page
  .getByText("Technical checks & benign recompression controls")
  .click();
await page.locator(".page-scroll").evaluate(e => {e.scrollTop = 0;});
await page.screenshot({
  path: "../artifacts/image-diagnostics-v6.png",
  fullPage: true,
});
await page
  .getByRole("button", { name: "Automatic screening", exact: true })
  .click();
await page.locator(".experiment-history").first().waitFor();
await page.locator(".experiment-history").first().click();
await page.locator(".page-scroll").evaluate(e => {e.scrollTop = 0;});
await page.screenshot({
  path: "../artifacts/automatic-forensics-v6.png",
  fullPage: true,
});
await writeFile(
  "../artifacts/forensics-browser-v6.json",
  JSON.stringify(
    {
      browserErrors: errors,
      hex: "passed",
      scrabble: "passed",
      realDiagnosticPixels: "passed",
      durableScreening: "visible",
    },
    null,
    2,
  ),
);
await browser.close();
if (errors.length) throw Error(errors.join("\n"));
