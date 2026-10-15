import { chromium } from "playwright";
import { writeFile } from "node:fs/promises";
const browser = await chromium.launch({
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
const page = await browser.newPage({ viewport: { width: 1800, height: 1200 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
await page.goto("http://127.0.0.1:8000", { waitUntil: "domcontentloaded" });
await page
  .getByRole("button", { name: "Growing database", exact: true })
  .click();
await page
  .getByRole("heading", { name: "Growing evidence database" })
  .waitFor();
if (!(await page.locator(".collection-paths").innerText()).includes("case.db"))
  throw Error("Database path missing");
await page.screenshot({
  path: "../artifacts/growing-database-v6.png",
  fullPage: true,
});
await page
  .getByRole("button", { name: "Patent intelligence", exact: true })
  .click();
await page
  .getByRole("heading", { name: "Mondaloy patent intelligence" })
  .waitFor();
await page
  .locator(".patent-list button")
  .filter({ hasText: "US:20100266442:A1" })
  .click();
if (
  !(await page.locator(".patent-detail").innerText()).includes(
    "Monica A. Jacinto",
  )
)
  throw Error("Inventor extraction missing");
await page.screenshot({
  path: "../artifacts/mondaloy-patents-v6.png",
  fullPage: true,
});
await page
  .getByRole("button", { name: "Public photo corpus", exact: true })
  .click();
await page.locator(".photo-grid img").first().waitFor();
await page.waitForFunction(() =>
  [...document.querySelectorAll(".photo-grid img")].every(
    (i) => i.complete && i.naturalWidth > 0,
  ),
);
await page.screenshot({
  path: "../artifacts/public-photo-corpus-v6.png",
  fullPage: true,
});
await page
  .getByRole("button", { name: "Tradecraft & hypotheses", exact: true })
  .click();
await page
  .getByRole("heading", {
    name: "Tradecraft, competing hypotheses & analytical dissent",
  })
  .waitFor();
await page
  .getByLabel("Executable method / guided workflow")
  .selectOption("mad");
await page.getByRole("button", { name: "Execute & preserve analysis" }).click();
await page.locator(".experiment-result").waitFor();
if (
  !(await page.locator(".experiment-result").innerText()).includes(
    "reference_population",
  )
)
  throw Error("Reference baseline missing");
await page.screenshot({
  path: "../artifacts/tradecraft-analysis-v6.png",
  fullPage: true,
});
await page.getByRole("button", { name: /Method catalogue/ }).click();
await page
  .getByPlaceholder("Search discipline, method or implementation state")
  .fill("Key Assumptions");
await page.locator(".method-catalogue summary").click();
if (
  !(await page.locator(".method-catalogue").innerText()).includes(
    "PRIMARY SOURCE ACQUIRED",
  )
)
  throw Error("Acquired primary reference missing");
await page.screenshot({
  path: "../artifacts/tradecraft-primary-source-v6.png",
  fullPage: true,
});
await page
  .getByRole("button", { name: "Cipher laboratory", exact: true })
  .click();
await page
  .getByRole("button", { name: "Modern encryption", exact: true })
  .click();
await page.getByRole("button", { name: "Generate ephemeral test key" }).click();
await page
  .getByRole("button", { name: "Run authenticated crypto experiment" })
  .click();
await page.waitForFunction(() =>
  document
    .querySelector(".experiment-result")
    ?.textContent.includes("AUTHENTICATED CIPHERTEXT CREATED"),
);
await page
  .getByRole("button", { name: "Use ciphertext for round-trip decryption" })
  .click();
await page
  .getByRole("button", { name: "Run authenticated crypto experiment" })
  .click();
await page.waitForFunction(() =>
  document
    .querySelector(".experiment-result")
    ?.textContent.includes("TAG VERIFIED"),
);
await page.screenshot({
  path: "../artifacts/authenticated-crypto-v6.png",
  fullPage: true,
});
await writeFile(
  "../artifacts/collection-browser-v6.json",
  JSON.stringify(
    {
      errors,
      vault: "real paths and records",
      patents: "real inventors and claims",
      photos: "actual acquired pixels",
      tradecraft: "baseline saved and acquired primary source linked",
      crypto: "AES-GCM browser round trip and authentication passed",
    },
    null,
    2,
  ),
);
await browser.close();
if (errors.length) throw Error(errors.join("\n"));
