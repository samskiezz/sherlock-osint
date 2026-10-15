import { chromium } from "playwright";
import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
const repo = fileURLToPath(new URL("../", import.meta.url));
const browser = await chromium.launch({
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
try {
  const page = await browser.newPage({
    viewport: { width: 1800, height: 1200 },
  });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("http://127.0.0.1:8010", { waitUntil: "domcontentloaded" });
  await page
    .getByText("Authenticated evidence workspace", { exact: true })
    .waitFor();
  await page.screenshot({
    path: repo + "artifacts/authenticated-login-v8.png",
    fullPage: true,
  });
  const credentials = JSON.parse(
    await readFile(repo + "data/foundation-secrets/admin-login.json", "utf8"),
  );
  await page.getByLabel("Username", { exact: true }).fill(credentials.username);
  await page.getByLabel("Password", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page
    .getByRole("button", { name: "Evidence board", exact: true })
    .waitFor();
  await page.waitForFunction(
    () => document.querySelectorAll(".react-flow__node").length > 0,
  );
  await page.screenshot({
    path: repo + "artifacts/authenticated-evidence-board-v8.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Growing database", exact: true })
    .click();
  await page
    .getByRole("heading", { name: "Growing evidence database", exact: true })
    .waitFor();
  await page
    .getByRole("button", { name: "Verify audit chain", exact: true })
    .click();
  const audit = await (
    await page.request.get("http://127.0.0.1:8010/api/v1/audit/verify")
  ).json();
  if (!audit.valid) throw Error("Gateway audit chain invalid");
  await page.getByRole("button", { name: /Evidence library/ }).click();
  await page.waitForTimeout(300);
  const broken = await page
    .locator("img")
    .evaluateAll(
      (images) =>
        images.filter((i) => i.complete && i.naturalWidth === 0).length,
    );
  if (errors.length || broken) throw Error(JSON.stringify({ errors, broken }));
  await writeFile(
    repo + "artifacts/foundation-browser-v8.json",
    JSON.stringify(
      {
        authenticated_login: true,
        existing_board_through_authenticated_gateway: true,
        actual_original_library_loaded: true,
        gateway_audit_chain_valid: true,
        javascript_errors: errors,
        broken_loaded_images: broken,
        credentials_exported: false,
      },
      null,
      2,
    ),
  );
  console.log(
    "PASS: login, actual evidence board/media, database and chained audit behind authenticated gateway",
  );
} finally {
  await browser.close();
}
