# 前端发起的 Scraper E2E

> 目的：从真实前端“作品提名 → 自动获取信息”链路验证各站点爬虫，而不是只测
> 后端 `/api/v1/scraper/scrape`。
> 对应 B-063 的自动化缺口：单测见 `tests/unit/test_scraper_sites.py`、URL 路由见
> `tests/unit/test_scraper_parse_url.py`。
>
> ⚠️ 2026-10-29 起测试登录旁路已删除（P-4），本脚本不再能自动过验证码：
> 需要真人先触发发码、把手机/邮箱收到的验证码通过 `CODE=` 传进来。

## 前置

1. 测试环境（或本地）能收到真实验证码；`CODE` 由真人现场提供
   （旧的白名单固定码 `888888` 已失效）。
2. `19900000001` 已完成问卷（测试库该账号已有 year=12 的答案，可直接进提名页）。
3. 本机有 Node 与 Playwright：

```bash
npm i playwright
npx playwright install chromium
```

## 运行

```bash
cd thvote-be-re
FRONTEND_BASE=http://154.37.215.62:8082/v11 \
PHONE=19900000001 CODE=<真人收到的6位验证码> \
node scripts/e2e/scraper_frontend.js
```

截图输出到 `/tmp/thvote-scraper-e2e/`。

## 当前用例与预期（2026-10-20 实测）

| 站点 | URL | 结果 |
|---|---|---|
| THBWiki | `https://thwiki.cc/东方红魔乡` | 标题/作者/封面正确填充 |
| Steam | `https://store.steampowered.com/app/851100/` | `Touhou Luna Nights` / `Team Ladybug` |
| Bilibili | `https://www.bilibili.com/video/BV1xx411c7mD` | 正常抓取。B 站 API 对浏览器 UA 返回 412，scraper 已改用 curl UA |
| 非法域名 | `https://example.com/some-work` | 同样提示不支持 |

## 已知线上不可用/受限

- YouTube：测试环境未配 `YOUTUBE_API_KEY` → `apierr: YOUTUBE_API_KEY not configured`；
- Pixiv：未配凭据 → `Pixiv authentication failed`（B-042②）；
- 抓取接口 per-IP 限流 10 次/分钟，连续跑多个用例时注意间隔。
