import { chromium } from "playwright";
const browser = await chromium.launch({
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
});
const page = await browser.newPage({
  viewport: { width: 1600, height: 1050 },
  deviceScaleFactor: 1,
});
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
await page.goto("http://127.0.0.1:8000", { waitUntil: "domcontentloaded" });
await page.waitForSelector(".evidence-card");
await page.screenshot({
  path: "../artifacts/evidence-board.png",
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
await page
  .getByRole("button", { name: "Cipher laboratory", exact: true })
  .click();
await page.getByRole("button", { name: "Run & preserve experiment" }).click();
await page.locator(".experiment-result").waitFor();
if (
  !(await page.locator(".experiment-result").innerText()).includes("Cole Allen")
)
  throw new Error("Cipher result missing");
await page.getByRole("button", { name: /^Evidence library/ }).click();
await page.getByRole("heading", { name: "Evidence vault" }).waitFor();
console.log(
  JSON.stringify({
    browserErrors: errors,
    cipher: "passed",
    board: "rendered",
    watch: "rendered",
    library: "rendered",
  }),
);
await browser.close();
if (errors.length) process.exit(1);
