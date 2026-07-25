const { test, expect } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');

const siteRoot = path.resolve(__dirname, '..');
const baseURL = process.env.PORTAL_BASE_URL || 'http://127.0.0.1:8765/';
const hourlyMailRoot = path.resolve(
  siteRoot,
  '../../../../../data/semantic_pipeline_v2/investment/loop_engineering/hourly_value_mail',
);
const latestSentMail = fs.readdirSync(hourlyMailRoot, { withFileTypes: true })
  .filter((entry) => entry.isDirectory())
  .map((entry) => {
    const manifestPath = path.join(hourlyMailRoot, entry.name, 'manifest.json');
    if (!fs.existsSync(manifestPath)) return null;
    const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
    if (manifest.status !== 'sent' || !manifest.snapshot_path) return null;
    return {
      name: entry.name,
      snapshotPath: manifest.snapshot_path,
    };
  })
  .filter(Boolean)
  .sort((left, right) => right.name.localeCompare(left.name))[0];
if (!latestSentMail || !fs.existsSync(latestSentMail.snapshotPath)) {
  throw new Error('No sent hourly-value-mail snapshot is available for deep-link QA');
}
const mailSnapshot = JSON.parse(
  fs.readFileSync(latestSentMail.snapshotPath, 'utf8'),
);
const mailPrimary = mailSnapshot.digest.find(
  (item) => (item.portal_type || 'news') === 'news',
);
const mailLinks = [
  ...mailSnapshot.digest.map((item) => ({
    type: item.portal_type || 'news',
    id: item.article_id,
  })),
  ...mailSnapshot.research_objects.map((item) => ({
    type: 'object',
    id: item.research_object_id,
  })),
];

async function blockFullIndex(page) {
  await page.route('**/data/site-index.json', (route) => route.abort('failed'));
}

test('latest email deep link renders title and summary without the full site index', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await blockFullIndex(page);
  const startedAt = Date.now();
  await page.goto(
    `${baseURL}#news/${encodeURIComponent(mailPrimary.article_id)}`,
    { waitUntil: 'domcontentloaded' },
  );
  await expect(page.locator('.summary')).toBeVisible({ timeout: 5000 });
  await expect(page.locator('.detail-title h3')).toContainText(
    mailPrimary.title.slice(0, 12),
  );
  await expect(page.locator('#content')).not.toContainText('页面加载失败');
  const metrics = await page.evaluate(() => {
    const title = document.querySelector('.detail-title h3');
    const summary = document.querySelector('.summary');
    return {
      titleTop: Math.round(title.getBoundingClientRect().top),
      summaryTop: Math.round(summary.getBoundingClientRect().top),
      summaryTextLength: summary.textContent.trim().length,
      documentWidth: document.documentElement.scrollWidth,
      viewportWidth: innerWidth,
      directDetailMode: document.documentElement.classList.contains('direct-detail'),
    };
  });
  expect(Date.now() - startedAt).toBeLessThan(8000);
  expect(metrics.titleTop).toBeLessThan(260);
  expect(metrics.summaryTop).toBeLessThan(600);
  expect(metrics.summaryTextLength).toBeGreaterThan(100);
  expect(metrics.documentWidth).toBeLessThanOrEqual(metrics.viewportWidth);
  expect(metrics.directDetailMode).toBeTruthy();
  await page.screenshot({ path: path.join(siteRoot, 'output/playwright/email-fast-detail-mobile.png'), fullPage: false });
});

test('inline bootstrap renders the summary even when the main application is unavailable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route('**/app.js*', (route) => route.abort('failed'));
  await page.goto(
    `${baseURL}#news/${encodeURIComponent(mailPrimary.article_id)}`,
    { waitUntil: 'domcontentloaded' },
  );
  await expect(page.locator('.bootstrap-detail .summary')).toBeVisible({
    timeout: 8000,
  });
  await expect(page.locator('.bootstrap-detail .detail-title h3')).toContainText(
    mailPrimary.title.slice(0, 12),
  );
  await expect(page.locator('.loading-copy')).toHaveCount(0);
});

test('all links in the sent mobile email have non-empty fast detail shards', async ({ request }) => {
  expect(mailLinks.length).toBeGreaterThan(0);
  const checks = await Promise.all(mailLinks.map(async (item) => {
    const response = await request.get(
      `${baseURL}data/details/${item.type}/${encodeURIComponent(item.id)}.json`,
    );
    expect(response.ok()).toBeTruthy();
    const payload = await response.json();
    expect(payload.type).toBe(item.type);
    expect(payload.id).toBe(item.id);
    expect(payload.item.title.trim().length).toBeGreaterThan(0);
    expect(payload.item.summary.trim().length).toBeGreaterThan(10);
    return item.id;
  }));
  expect(checks).toHaveLength(mailLinks.length);
});

test('analysis-card list no longer overflows at phone widths', async ({ page }) => {
  for (const width of [320, 360, 390, 430]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto('about:blank');
    await page.goto(`${baseURL}#issues`, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('#content h3').first()).toContainText('分析卡片');
    const documentWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(documentWidth).toBeLessThanOrEqual(width);
  }
});
