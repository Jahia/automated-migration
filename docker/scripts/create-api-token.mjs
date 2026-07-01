#!/usr/bin/env node
/**
 * Creates a Personal API Token in Jahia via Playwright.
 *
 * Usage:
 *   node docker/scripts/create-api-token.mjs [--name <token-name>] [--env-file <path>]
 */

import { chromium } from "playwright";
import { writeFileSync, existsSync, readFileSync, readdirSync } from "fs";
import { resolve } from "path";

const JAHIA_URL = process.env.JAHIA_HOST || "http://localhost:8081";
const JAHIA_USER = process.env.JAHIA_USER || "root";
const JAHIA_PASS = process.env.JAHIA_PASS || "root1234";

const args = process.argv.slice(2);
function getArg(flag, fallback) {
  const idx = args.indexOf(flag);
  return idx !== -1 && args[idx + 1] ? args[idx + 1] : fallback;
}

const TOKEN_NAME = getArg("--name", "auto-migration");
const ENV_FILE = getArg("--env-file", null);

async function main() {
  console.log(`Creating API token "${TOKEN_NAME}" on ${JAHIA_URL}...`);

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  // Login
  console.log("  Logging in...");
  await page.goto(`${JAHIA_URL}/jahia/dashboard`);
  await page.waitForTimeout(2000);
  await page.fill('input[name="username"]', JAHIA_USER);
  await page.fill('input[name="password"]', JAHIA_PASS);
  await page.click('button[type="submit"]');
  await page.waitForTimeout(5000);

  if (!page.url().includes("dashboard")) {
    throw new Error("Login failed");
  }
  console.log("  Logged in.");

  // Navigate to API tokens
  console.log("  Navigating to API tokens...");
  await page.goto(`${JAHIA_URL}/jahia/dashboard/personal-api-tokens`);
  await page.waitForTimeout(3000);

  // Click "Create Token"
  console.log('  Clicking "Create Token"...');
  await page.click('button:has-text("Create Token")');
  await page.waitForTimeout(2000);

  // Fill token name
  console.log(`  Setting name "${TOKEN_NAME}"...`);
  await page.locator('input[type="text"]').first().fill(TOKEN_NAME);
  await page.waitForTimeout(500);

  // Select all scopes — click each unchecked checkbox with delay
  console.log("  Selecting all scopes...");
  const checkboxes = page.locator('input[type="checkbox"]');
  const total = await checkboxes.count();
  console.log(`    Found ${total} checkboxes`);

  for (let i = 0; i < total; i++) {
    try {
      const cb = checkboxes.nth(i);
      if (!(await cb.isChecked())) {
        await cb.click({ force: true, timeout: 3000 });
        await page.waitForTimeout(200);
      }
    } catch (e) {
      // checkbox may have been removed from DOM after a "select all" click
    }
  }
  await page.waitForTimeout(500);

  // Click the Create button in the dialog footer
  console.log("  Clicking Create...");
  // The dialog has multiple "Create" buttons — pick the one in the dialog actions
  const dialogBtns = page.locator('div[role="dialog"] button, .moonstone-dialog button');
  const btnCount = await dialogBtns.count();
  for (let i = 0; i < btnCount; i++) {
    const txt = await dialogBtns.nth(i).textContent();
    if (txt && txt.trim().toLowerCase().includes("create")) {
      await dialogBtns.nth(i).click();
      break;
    }
  }
  await page.waitForTimeout(4000);

  // Extract token
  console.log("  Extracting token...");
  let token = null;

  for (const sel of ['input[readonly]', 'code', 'pre', '.token-value']) {
    const el = page.locator(sel);
    const n = await el.count();
    for (let i = 0; i < n; i++) {
      const val = (await el.nth(i).inputValue().catch(() => "")) ||
                  (await el.nth(i).textContent().catch(() => ""));
      if (val && val.includes("=") && val.length > 20) {
        token = val.trim();
        break;
      }
    }
    if (token) break;
  }

  if (!token) {
    const body = await page.textContent("body");
    const match = body.match(/[A-Za-z0-9+/]{30,}={1,2}/);
    if (match) token = match[0];
  }

  await page.screenshot({ path: "/tmp/jahia-token-result.png", fullPage: true });
  await browser.close();

  if (!token) {
    console.error("ERROR: Could not extract token. Screenshot: /tmp/jahia-token-result.png");
    process.exit(1);
  }

  console.log(`\n  Token: ${token}`);

  const envPath = resolveEnvFile();
  writeTokenToEnv(envPath, token);
  console.log(`  Written to: ${envPath}`);
}

function resolveEnvFile() {
  if (ENV_FILE) return resolve(ENV_FILE);
  const projectsDir = resolve("projects");
  if (existsSync(projectsDir)) {
    for (const name of readdirSync(projectsDir)) {
      const candidate = resolve(projectsDir, name, ".env");
      if (existsSync(candidate)) return candidate;
    }
  }
  return resolve(".env");
}

function writeTokenToEnv(envPath, token) {
  const marker = "JAHIA_MCP_TOKEN=";
  let content = existsSync(envPath) ? readFileSync(envPath, "utf-8") : "";
  if (content.includes(marker)) {
    content = content.replace(new RegExp(`${marker}.*`), `${marker}${token}`);
  } else {
    content = content.trimEnd() + `\n${marker}${token}\n`;
  }
  writeFileSync(envPath, content);
}

main().catch((err) => {
  console.error("Fatal:", err.message);
  process.exit(1);
});
