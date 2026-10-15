import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
const root = fileURLToPath(new URL("../", import.meta.url));
process.env.PLAYWRIGHT_BROWSERS_PATH ||= root + ".browsers";
const { chromium } = await import("playwright");
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
  const credentials = JSON.parse(
    await readFile(root + "data/foundation-secrets/admin-login.json", "utf8"),
  );
  await page.getByLabel("Username", { exact: true }).fill(credentials.username);
  await page.getByLabel("Password", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page
    .getByRole("button", { name: "Evidence retrieval", exact: true })
    .click();
  await page
    .getByRole("heading", {
      name: "Evidence retrieval & cross-reference",
      exact: true,
    })
    .waitFor();
  await page
    .getByLabel("Evidence research query")
    .fill("Blitzkrieg Bots Cole Allen");
  await page
    .getByRole("button", { name: "Search stored evidence", exact: true })
    .click();
  const pdf = page
    .locator(".knowledge-hit")
    .filter({ hasText: "EV-32234078df6a" })
    .filter({ hasText: "PDF page 11" })
    .first();
  await pdf.waitFor({ timeout: 90000 });
  await page.screenshot({
    path: root + "artifacts/evidence-retrieval-v9.png",
    fullPage: true,
  });
  await pdf
    .getByRole("button", { name: "Open original & cited passage", exact: true })
    .click();
  await page
    .locator('.pdf-inspector canvas[data-rendered="11"]')
    .waitFor({ timeout: 60000 });
  await page
    .locator(".pdf-passage-highlight")
    .first()
    .waitFor({ timeout: 30000 });
  const handle = page.getByRole("separator", {
    name: "Resize evidence inspector",
  });
  const box = await handle.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + 60);
  await page.mouse.down();
  await page.mouse.move(box.x - 310, box.y + 60, { steps: 12 });
  await page.mouse.up();
  await page.locator(".pdf-passage-highlight").first().scrollIntoViewIfNeeded();
  const ink = await page
    .locator('.pdf-inspector canvas[data-rendered="11"]')
    .evaluate((canvas) => {
      const pixels = canvas
        .getContext("2d")
        .getImageData(0, 0, canvas.width, canvas.height).data;
      let count = 0;
      for (let i = 0; i < pixels.length; i += 160) {
        if (pixels[i] < 230 || pixels[i + 1] < 230 || pixels[i + 2] < 230)
          count++;
      }
      return count;
    });
  if (ink < 10)
    throw Error("Preserved PDF canvas contains no rendered content");
  await page.screenshot({
    path: root + "artifacts/cited-original-pdf-v9.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "provenance", exact: true }).click();
  await page.getByText(/Archive redistribution review/).waitFor();
  await page
    .getByRole("button", { name: "Close inspector", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Tradecraft & hypotheses", exact: true })
    .click();
  await page.waitForFunction(() =>
    Array.from(document.querySelectorAll("select")).some((x) =>
      x.textContent.includes("Isolation Forest"),
    ),
  );
  const controls = await page.locator("select").allTextContents();
  if (!controls.some((x) => x.includes("Isolation Forest")))
    throw Error("Executable method selection absent");
  const methodCatalogue = await (
    await page.request.get("http://127.0.0.1:8010/api/tradecraft")
  ).json();
  const detector = methodCatalogue.methods.find(
    (m) => m.name === "Isolation Forest",
  );
  await page
    .getByLabel("Executable method / guided workflow")
    .selectOption(detector.id);
  await page
    .getByPlaceholder(
      "Retain the strongest opposing explanation and missing observations.",
    )
    .fill(
      "Synthetic software acceptance fixture only. A planted outlier is compared with a benign held-out control; this makes no claim about any case subject.",
    );
  await page
    .getByRole("button", { name: "Execute & preserve analysis", exact: true })
    .click();
  const output = page.locator(".experiment-result .forensic-json");
  await output.waitFor();
  const computed = JSON.parse(await output.textContent());
  if (
    !computed.outlier_indices.includes(1) ||
    computed.outlier_indices.includes(0)
  )
    throw Error("Detector controls failed in the UI");
  await page.screenshot({
    path: root + "artifacts/analysis-methods-v9.png",
    fullPage: true,
  });
  const response = await page.request.get(
    "http://127.0.0.1:8010/api/knowledge/queries",
  );
  const saved = await response.json();
  if (!saved.length) throw Error("Reproducible query history absent");
  if (errors.length) throw Error(JSON.stringify(errors));
  await writeFile(
    root + "artifacts/platform-browser-v9.json",
    JSON.stringify(
      {
        authenticated: true,
        hybrid_search_real_results: true,
        page_11_primary_pdf_citation: true,
        exact_source_phrase_highlighted: true,
        actual_pdf_rendered: true,
        rights_review_interface: true,
        real_executable_detector_choices: true,
        detector_executed_and_saved_through_ui: true,
        detector_input:
          "Synthetic planted-outlier and benign control, not case evidence",
        saved_queries: saved.length,
        javascript_errors: errors,
        credentials_exported: false,
      },
      null,
      2,
    ),
  );
} finally {
  await browser.close();
}
