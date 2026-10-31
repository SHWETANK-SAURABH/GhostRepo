// Drives the running app in a locally installed browser, through the whole product workflow.
// Start the backend and frontend first. Usage: npm run e2e
// Options: E2E_URL, E2E_BROWSER (msedge or chrome), E2E_WAIT_FOR_AI=1 to wait for the real model.
import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright-core";

const BASE = process.env.E2E_URL ?? "http://localhost:3000";
const OUTPUT = path.join(path.dirname(fileURLToPath(import.meta.url)), ".output");
const WAIT_FOR_AI = process.env.E2E_WAIT_FOR_AI === "1";
mkdirSync(OUTPUT, { recursive: true });

const browser = await chromium.launch({ channel: process.env.E2E_BROWSER ?? "msedge" });
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  acceptDownloads: true,
  permissions: ["clipboard-read", "clipboard-write"],
});
const page = await context.newPage();

const problems = [];
page.on("pageerror", (error) => problems.push(`page error: ${error.message}`));
page.on("console", (message) => {
  // 404 means no draft yet. 422 is the bad endpoint this walkthrough submits on purpose.
  const expected = /status of (404|422)/.test(message.text());
  if (message.type() === "error" && !expected) {
    problems.push(`console error: ${message.text()}`);
  }
});

const shot = (name, fullPage = true) =>
  page.screenshot({ path: path.join(OUTPUT, `${name}.png`), fullPage });

function step(name) {
  console.log(`- ${name}`);
}

async function expectText(text, timeout = 15_000) {
  await page.getByText(text, { exact: false }).first().waitFor({ timeout });
}

try {
  step("Dashboard loads with live data");
  await page.goto(BASE);
  await page.getByRole("link", { name: /Summon Ghost/ }).click();
  await page.waitForURL("**/investigations/new");
  await shot("01-new-investigation");

  step("Invalid paths are rejected");
  await page.getByLabel("Repository path").fill("../../..");
  await page.getByRole("button", { name: "Validate" }).click();
  await expectText("inside the configured workspace root");

  step("Demo repository is created and confirmed");
  await page.getByRole("button", { name: "Create demo repository" }).click();
  await page.getByRole("button", { name: "Create demo", exact: true }).click();
  const start = page.getByRole("button", { name: /Confirm and start investigation/ });
  await start.waitFor({ timeout: 30_000 });
  await shot("02-confirm-repository");
  await start.click();

  step("Progress appears while the investigation runs");
  await page.waitForURL(/investigations\/[0-9a-f]{32}$/);
  const investigationUrl = page.url();
  await expectText("Investigation progress");
  await shot("03-progress", false);

  step("Deterministic results appear");
  await expectText("Health indicator", 60_000);
  if (WAIT_FOR_AI) {
    step("Waiting for the local model");
    await page
      .getByText(/AI analysis did not complete|Health assessment/)
      .first()
      .waitFor({ timeout: 600_000 });
  }
  await expectText("Git history");
  await shot("04-autopsy");

  step("Findings are separated by origin");
  await page.getByRole("link", { name: "Findings", exact: true }).click();
  await expectText("Verified findings");
  await expectText("AI-generated findings and hypotheses");
  await expectText("Secret file is committed: .env");
  await shot("05-findings");
  await page.getByRole("button", { name: /^Critical/ }).click();
  const leaked = await page.getByText("demo-only-not-a-real-credential").count();
  if (leaked) throw new Error("A secret value is visible in findings");

  step("Plan lists tasks and updates status");
  await page.getByRole("link", { name: "Resurrection plan", exact: true }).click();
  await expectText("rough estimate, not a measurement");
  const firstStatus = page.getByLabel("Status").first();
  await firstStatus.selectOption("in_progress");
  await page.waitForTimeout(500);
  await shot("06-plan");

  step("README draft generates, edits and saves");
  await page.getByRole("link", { name: "README", exact: true }).click();
  await page.getByRole("button", { name: "Generate README draft" }).click();
  await expectText("Needs your confirmation");
  await expectText("pip install -r requirements.txt");
  await shot("07-readme");
  await page.getByRole("tab", { name: "Edit" }).click();
  const editor = page.getByLabel("README Markdown");
  await editor.fill(`${await editor.inputValue()}\nEdited in the browser test.\n`);
  await page.getByRole("button", { name: "Save draft" }).click();
  await expectText("Edited by you");
  await page.getByRole("button", { name: "Copy" }).click();
  await expectText("Copied to the clipboard");
  const readmeDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export" }).click();
  await (await readmeDownload).saveAs(path.join(OUTPUT, "README.draft.md"));

  step("Patch needs approval before download");
  await page.getByRole("link", { name: "Patches", exact: true }).click();
  await page.getByRole("button", { name: "Generate patch proposal" }).click();
  await expectText("Nothing has been changed in the repository");
  if (await page.getByRole("link", { name: "Download patch" }).count()) {
    throw new Error("Download was offered before approval");
  }
  await shot("08-patch");
  await page.getByRole("button", { name: "Approve patch" }).click();
  await page.getByRole("button", { name: /I reviewed it/ }).click();
  const patchDownload = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download patch" }).click();
  await (await patchDownload).saveAs(path.join(OUTPUT, "proposal.patch"));

  step("Reports export");
  for (const name of ["Markdown", "JSON"]) {
    const download = page.waitForEvent("download");
    await page.getByRole("link", { name, exact: true }).click();
    await (await download).saveAs(path.join(OUTPUT, `report-export.${name.toLowerCase()}`));
  }

  step("History and settings work");
  await page.getByRole("link", { name: "History" }).first().click();
  await expectText("stored locally");
  await page.getByRole("link", { name: "Settings" }).first().click();
  await expectText("Installed models");
  const endpoint = page.getByLabel("Ollama endpoint");
  const original = await endpoint.inputValue();
  await endpoint.fill("https://api.example.com");
  await page.getByRole("button", { name: "Save settings" }).click();
  await expectText("This host is not allowed");
  await endpoint.fill(original);
  await shot("09-settings");

  step("Dashboard reflects the investigation");
  await page.goto(BASE);
  await expectText("haunted-demo");
  await shot("10-dashboard");

  step("Layout holds at phone width");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(BASE);
  await expectText("haunted-demo");
  await shot("11-dashboard-mobile");
  for (const url of [BASE, investigationUrl, `${investigationUrl}/findings`, `${BASE}/settings`]) {
    await page.goto(url);
    await page.waitForTimeout(800);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    if (overflow > 1) problems.push(`horizontal overflow of ${overflow}px at ${url}`);
  }
  await shot("12-findings-mobile");

  if (problems.length) {
    throw new Error(`Browser problems:\n${problems.join("\n")}`);
  }
  console.log("Walkthrough passed.");
} catch (error) {
  await shot("failure").catch(() => {});
  console.error(`Walkthrough failed: ${error.message}`);
  process.exitCode = 1;
} finally {
  await browser.close();
}
