// ORION — full UI walkthrough.
//
// Screenshots are the deliverable, but a screenshot only proves something
// rendered, not that it rendered *correctly* — a section that 500s and falls
// back to its error panel photographs perfectly well. So every page is also
// checked for console errors, failed network requests, and the error/empty
// panels the design system uses, and those are reported alongside.
//
// Runs both themes: light is a supported theme per docs/UI_DESIGN.md §8 and
// is the one nobody looks at, which is where contrast bugs live.

import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const BASE = process.env.ORION_UI_BASE || 'http://localhost:5174';
const OUT = process.env.ORION_UI_OUT || './screenshots';
const EMAIL = 'demo@orion.test';
const PASSWORD = 'orion-demo-1234';

const findings = [];
let shotIndex = 0;

function record(page, label) {
  const problems = [];
  page.on('console', (m) => {
    if (m.type() === 'error') problems.push(`console: ${m.text().slice(0, 300)}`);
  });
  page.on('pageerror', (e) => problems.push(`pageerror: ${String(e).slice(0, 300)}`));
  page.on('requestfailed', (r) => {
    // Favicons and analytics noise are not findings.
    if (!/favicon|\.map$/.test(r.url())) {
      problems.push(`request failed: ${r.method()} ${r.url()} — ${r.failure()?.errorText}`);
    }
  });
  page.on('response', (r) => {
    if (r.status() >= 400 && !/favicon/.test(r.url())) {
      problems.push(`HTTP ${r.status()} ${r.url()}`);
    }
  });
  return problems;
}

async function shoot(page, name, problems, { full = true } = {}) {
  shotIndex += 1;
  const file = `${String(shotIndex).padStart(2, '0')}-${name}.png`;
  await page.screenshot({ path: join(OUT, file), fullPage: full });

  // The design system's error panel. If it is on screen, the page "rendered"
  // and still failed.
  const errorPanels = await page.locator('[role="alert"]').allTextContents();
  const visibleErrors = errorPanels.map((t) => t.trim()).filter(Boolean);

  findings.push({
    shot: file,
    url: page.url(),
    title: await page.title(),
    errorPanels: visibleErrors,
    problems: [...new Set(problems)],
  });
  problems.length = 0;
  console.log(`  ${file}  ${visibleErrors.length ? '[error panel]' : ''}${problems.length ? '[console]' : ''}`);
}

async function settle(page, ms = 900) {
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.waitForTimeout(ms);
}

async function main() {
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();

  for (const theme of ['dark', 'light']) {
    console.log(`\n== ${theme} theme ==`);
    const context = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      deviceScaleFactor: 1,
    });
    // Set the theme before first paint, the way the no-FOUC script does.
    await context.addInitScript((t) => {
      try {
        window.localStorage.setItem('orion-theme', t);
      } catch {}
    }, theme);

    const page = await context.newPage();
    const problems = record(page, theme);

    // ── Public pages ────────────────────────────────────────────────
    await page.goto(BASE, { waitUntil: 'domcontentloaded' });
    await settle(page, 1600); // hero animation
    await shoot(page, `${theme}-landing`, problems);

    await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' });
    await settle(page);
    await shoot(page, `${theme}-login`, problems);

    // The inline forgot-password panel, which only exists after a click.
    const forgot = page.getByText(/forgot password/i).first();
    if (await forgot.count()) {
      await forgot.click().catch(() => {});
      await settle(page, 500);
      await shoot(page, `${theme}-login-forgot-password`, problems);
    }

    await page.goto(`${BASE}/signup`, { waitUntil: 'domcontentloaded' });
    await settle(page);
    await shoot(page, `${theme}-signup`, problems);

    await page.goto(`${BASE}/reset-password`, { waitUntil: 'domcontentloaded' });
    await settle(page);
    // No token in the URL: this must show the error state, not a form.
    await shoot(page, `${theme}-reset-password-no-token`, problems);

    await page.goto(`${BASE}/this-route-does-not-exist`, { waitUntil: 'domcontentloaded' });
    await settle(page, 500);
    await shoot(page, `${theme}-404`, problems);

    // ── Log in ──────────────────────────────────────────────────────
    await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' });
    await settle(page);
    await page.locator('input[type="email"], input[name="identifier"], input[type="text"]').first().fill(EMAIL);
    await page.locator('input[type="password"]').first().fill(PASSWORD);
    await page.locator('button[type="submit"]').first().click();
    await page.waitForURL(/dashboard/, { timeout: 20000 }).catch(() => {});
    await settle(page, 1500);
    await shoot(page, `${theme}-dashboard-overview`, problems);

    // ── Every dashboard section ─────────────────────────────────────
    // By id, not accessible name: each nav button reads "01 Scenarios" because
    // the numbering is part of the label, so an exact-name match finds nothing.
    const sections = ['scenarios', 'runs', 'models', 'batches', 'search', 'compare', 'settings'];
    for (const name of sections) {
      const nav = page.locator(`#sidebar-${name}`);
      if (!(await nav.count())) {
        findings.push({ shot: null, url: page.url(), problems: [`nav item missing: ${name}`] });
        continue;
      }
      await nav.click();
      await settle(page, 1200);
      await shoot(page, `${theme}-section-${name}`, problems);

      // Open the first row of the sections that have a detail view.
      if (['compare', 'search'].includes(name)) {
        // A completed row: clicking the newest one lands on a job still
        // running, whose detail panel is a one-line "still running" note.
        const completed = page.locator('tbody tr', { hasText: /completed/i }).first();
        const row = (await completed.count()) ? completed : page.locator('tbody tr').first();
        if (await row.count()) {
          await row.click();
          await settle(page, 1200);
          await shoot(page, `${theme}-section-${name}-detail`, problems);
        }
      }
    }

    // ── Replay ──────────────────────────────────────────────────────
    // A seeded run id; the page must show either frames or the documented
    // empty state offering replay-from-seed.
    await page.goto(`${BASE}/dashboard/runs/6`, { waitUntil: 'domcontentloaded' });
    await settle(page, 1500);
    await shoot(page, `${theme}-replay-run`, problems);

    // ── Billing ─────────────────────────────────────────────────────
    await page.goto(`${BASE}/billing`, { waitUntil: 'domcontentloaded' });
    await settle(page, 1200);
    await shoot(page, `${theme}-billing`, problems);

    await context.close();
  }

  // ── Responsive: the breakpoints §10 names ─────────────────────────
  console.log('\n== responsive ==');
  for (const [label, viewport] of [
    ['tablet-900', { width: 900, height: 1200 }],
    ['phone-390', { width: 390, height: 844 }],
  ]) {
    const context = await browser.newContext({ viewport });
    await context.addInitScript(() => {
      try { window.localStorage.setItem('orion-theme', 'dark'); } catch {}
    });
    const page = await context.newPage();
    const problems = record(page, label);

    await page.goto(BASE, { waitUntil: 'domcontentloaded' });
    await settle(page, 1400);
    await shoot(page, `${label}-landing`, problems);

    await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' });
    await settle(page);
    await page.locator('input[type="email"], input[name="identifier"], input[type="text"]').first().fill(EMAIL);
    await page.locator('input[type="password"]').first().fill(PASSWORD);
    await page.locator('button[type="submit"]').first().click();
    await page.waitForURL(/dashboard/, { timeout: 20000 }).catch(() => {});
    await settle(page, 1500);
    await shoot(page, `${label}-dashboard`, problems);

    // Horizontal overflow is the classic mobile break, and it is invisible in
    // a screenshot because the shot is taken at the document width.
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    if (overflow > 2) {
      findings.push({
        shot: null,
        url: page.url(),
        problems: [`horizontal overflow at ${viewport.width}px: ${overflow}px wider than the viewport`],
      });
    }

    await context.close();
  }

  await browser.close();

  writeFileSync(join(OUT, 'findings.json'), JSON.stringify(findings, null, 2));

  const bad = findings.filter((f) => f.problems?.length || f.errorPanels?.length);
  console.log(`\n${findings.length} captures, ${bad.length} with problems`);
  for (const f of bad) {
    console.log(`\n${f.shot || f.url}`);
    for (const e of f.errorPanels || []) console.log(`   error panel: ${e.slice(0, 200)}`);
    for (const p of f.problems || []) console.log(`   ${p}`);
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
