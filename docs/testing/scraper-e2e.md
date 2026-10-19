# 前端发起的 Scraper E2E

> 目的：从真实前端“作品提名 → 自动获取信息”链路验证各站点爬虫，而不是只测
> 后端 `/api/v1/scraper/scrape`。登录使用测试旁路账号，不需要真实短信。
> 对应 B-063 的自动化缺口：单测见 `tests/unit/test_scraper_sites.py`、URL 路由见
> `tests/unit/test_scraper_parse_url.py`。

## 前置

1. 测试环境已配置 `TEST_LOGIN_BYPASS_ACCOUNTS` 包含 `19900000001`，
   `TEST_LOGIN_BYPASS_CODE=888888`（当前测试 Nacos 已配置）。
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
PHONE=19900000001 CODE=888888 \
node scripts/e2e/scraper_frontend.js
```

截图输出到 `/tmp/thvote-scraper-e2e/`。

## 当前用例与预期（2026-10-20 实测）

| 站点 | URL | 结果 |
|---|---|---|
| THBWiki | `https://thwiki.cc/东方红魔乡` | 标题/作者/封面正确填充 |
| Steam | `https://store.steampowered.com/app/851100/` | `Touhou Luna Nights` / `Team Ladybug` |
| Bilibili | `https://www.bilibili.com/video/BV1xx411c7mD` | 当前 API 返回非 JSON，前端提示“不支持该网站或获取信息错误”（已知问题，非前端崩溃） |
| 非法域名 | `https://example.com/some-work` | 同样提示不支持 |

## 已知线上不可用/受限

- YouTube：测试环境未配 `YOUTUBE_API_KEY` → `apierr: YOUTUBE_API_KEY not configured`；
- Pixiv：未配凭据 → `Pixiv authentication failed`（B-042②）；
- 抓取接口 per-IP 限流 10 次/分钟，连续跑多个用例时注意间隔。
