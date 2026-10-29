#!/usr/bin/env node
/**
 * Frontend-driven scraper E2E (Playwright).
 *
 * Logs in through the real login modal, opens the doujin nomination editor and
 * clicks “自动获取信息” for each URL.
 *
 * Prereqs:
 *   npm i playwright && npx playwright install chromium
 *   2026-10-30 起改用邮箱+密码登录(loginEmailPassword):测试账号
 *   votetester1@touhou.ai 带真实密码哈希,不再依赖验证码/短信/旁路。
 *
 * Usage:
 *   FRONTEND_BASE=http://154.37.215.62:8082/v11 \
 *   EMAIL=votetester1@touhou.ai PASSWORD=<password> \
 *   node scripts/e2e/scraper_frontend.js
 */

const { chromium } = require('playwright');

const BASE = process.env.FRONTEND_BASE || 'http://154.37.215.62:8082/v11';
const EMAIL = process.env.EMAIL || 'votetester1@touhou.ai';
const PASSWORD = process.env.PASSWORD || 'wlrg6M43tpI6919i';
const OUT = process.env.E2E_OUT_DIR || '/tmp/thvote-scraper-e2e';
// 测试机 154.37.215.62 的出口 IP 被 B 站风控时只能验收“友好报错”；
// 在未被风控的网络(或配了 B 站代理)上设 BILI_EXPECT=ok 验收真实抓取。
const BILI_EXPECT = process.env.BILI_EXPECT || 'ok';

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
    // 已修复：B 站 API 对浏览器 UA 返回 412，改用 curl UA 后 200 JSON。
    name: 'Bilibili',
    url: 'https://www.bilibili.com/video/BV1xx411c7mD',
    expect:
      BILI_EXPECT === 'ok'
        ? { ok: true, title: '字幕君交流场所' }
        : { ok: false, toast: '不支持该网站或获取信息错误' },
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

  // login through the real modal (email + password, no SMS)
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(4000);
  await page.locator('a.float-arrow-box').click();
  await page.waitForTimeout(1000);
  await page.getByText('使用旧版账号密码登录', { exact: true }).click();
  await page.locator('input[placeholder="邮箱"]').fill(EMAIL);
  await page.locator('input[placeholder="密码"]').fill(PASSWORD);
  const loginResp = page
    .waitForResponse(r => r.url().includes('/graphql') && r.request().postData()?.includes('loginEmailPassword'), { timeout: 30000 })
    .catch(() => null);
  await page.locator('button', { hasText: '登录' }).last().click();
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
