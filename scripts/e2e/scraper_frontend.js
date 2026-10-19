#!/usr/bin/env node
/**
 * Frontend-driven scraper E2E (Playwright).
 *
 * Logs in through the real login modal with the test-bypass phone/code,
 * opens the doujin nomination editor and clicks “自动获取信息” for each URL.
 *
 * Prereqs:
 *   npm i playwright && npx playwright install chromium
 *   Test env must have TEST_LOGIN_BYPASS_ACCOUNTS/CODE configured.
 *
 * Usage:
 *   FRONTEND_BASE=http://154.37.215.62:8082/v11 \
 *   PHONE=19900000001 CODE=888888 \
 *   node scripts/e2e/scraper_frontend.js
 */

const { chromium } = require('playwright');

const BASE = process.env.FRONTEND_BASE || 'http://154.37.215.62:8082/v11';
const PHONE = process.env.PHONE || '19900000001';
const CODE = process.env.CODE || '888888';
const OUT = process.env.E2E_OUT_DIR || '/tmp/thvote-scraper-e2e';

const CASES = [
  {
    name: 'THBWiki',
    url: 'https://thwiki.cc/东方红魔乡',
    expect: { ok: true, title: '东方红魔乡' },
  },
  {
    name: 'Steam',
    url: 'https://store.steampowered.com/app/851100/',
    expect: { ok: true, title: 'Touhou Luna Nights' },
  },
  {
    // 已知线上失败：B 站 API 对测试机返回非 JSON，前端应给出友好错误。
    name: 'Bilibili-current-failure',
    url: 'https://www.bilibili.com/video/BV1xx411c7mD',
    expect: { ok: false, toast: '不支持该网站或获取信息错误' },
  },
  {
    name: 'Unsupported-host',
    url: 'https://example.com/some-work',
    expect: { ok: false, toast: '不支持该网站或获取信息错误' },
  },
];

async function closeNotice(page) {
  const know = page.getByText('我知道了', { exact: true }).last();
  if (await know.isVisible().catch(() => false)) {
    await know.click();
    await page.waitForTimeout(500);
  }
}

(async () => {
  const fs = require('fs');
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e).slice(0, 160)));

  // login through the real modal
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(4000);
  await page.locator('a.float-arrow-box').click();
  await page.waitForTimeout(1000);
  await page.locator('input[placeholder="手机号(仅限国内)或邮箱"]').fill(PHONE);
  await page.locator('input[placeholder="验证码"]').fill(CODE);
  const loginResp = page
    .waitForResponse(r => r.url().includes('/graphql') && r.request().postData()?.includes('loginPhone'), { timeout: 30000 })
    .catch(() => null);
  await page.locator('button', { hasText: '开始投票' }).last().click();
  await loginResp;
  await page.waitForTimeout(5000);
  const session = await page.evaluate(() => !!localStorage.getItem('sessionToken'));
  if (!session) throw new Error('login failed: no sessionToken');

  const results = [];
  for (const c of CASES) {
    await page.goto(BASE + '/doujin', { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForTimeout(3500);
    await closeNotice(page);
    await page.getByText('添加提名', { exact: true }).first().click();
    await page.waitForTimeout(1000);
    await closeNotice(page); // rules modal
    const modal = page.locator('div.baseBoxRoundedShadow').filter({ hasText: '编辑提名' }).first();
    const inputs = modal.locator('input');
    await inputs.nth(0).fill(c.url);
    const respP = page
      .waitForResponse(r => r.url().includes('/doujin/api') && r.request().method() === 'POST', { timeout: 90000 })
      .catch(() => null);
    await modal.locator('button', { hasText: '自动获取信息' }).click();
    const resp = await respP;
    await page.waitForTimeout(1000);
    const title = await inputs.nth(1).inputValue();
    const author = await inputs.nth(2).inputValue();
    const body = await page.locator('body').innerText();
    const ok = c.expect.ok ? title.includes(c.expect.title) : body.includes(c.expect.toast);
    results.push({ name: c.name, http: resp ? resp.status() : null, title, author, ok });
    console.log(`${ok ? 'PASS' : 'FAIL'} ${c.name} http=${resp ? resp.status() : 'n/a'} title=${JSON.stringify(title)} author=${JSON.stringify(author)}`);
    await page.screenshot({ path: `${OUT}/${c.name.replace(/[^a-z0-9]+/gi, '-')}.png` });
  }

  console.log('ERRORS:', errors);
  console.log('SUMMARY', JSON.stringify({ pass: results.filter(r => r.ok).length, fail: results.filter(r => !r.ok).length }));
  await browser.close();
  process.exit(results.every(r => r.ok) ? 0 : 1);
})().catch(err => {
  console.error(err);
  process.exit(1);
});
