# 拦脚本：让请求尽量来自真人浏览器（B-048）

> 状态：**Origin/Referer 校验已实现（默认关，待灰度）；端口收口待办**（2026-07-17）。
> 目标：把"脚本直连 API 刷票"的懒脚本挡在门外，尽量让变更请求来自真人在浏览器里的操作。

## 一、诚实的前提

网络层**无法 100%** 区分"真人手点"和"脚本"——铁了心的攻击者可驱动真·无头浏览器（Playwright/Puppeteer），跑我们的 JS、带真实 UA、甚至解验证码。所以目标是**抬高成本、拦掉便宜的懒脚本（curl / python-requests 直连）**，不是绝对拦截。漏网的"真人建的小号"交给取证层（B-044/045/046）事后聚类。

## 二、已实现：服务端 Origin/Referer 校验（`BrowserOriginGuardMiddleware`）

浏览器发 fetch/XHR 的 POST 会**自动带** `Origin`/`Referer`;裸脚本默认不带。对**变更类请求**要求带其一,不带→403(`FORBIDDEN_ORIGIN`)。

- **作用范围(只拦变更,读操作放行)**:
  - `POST /graphql` 且 body 含 `mutation` 操作(正则 `\bmutation\b`——刻意不匹配 introspection *query* 里的 `mutationType` 字段,所以前端 codegen 不受影响)。
  - REST 提交(character/music/cp/paper/dojin)、发码(send-sms/email-code)、登录(login-*)。
- **判定**:有 `Origin` 或 `Referer` 即放行;若 `CORS_ALLOWED_ORIGINS` 配了具体域名(非 `["*"]`),还需 host 匹配。
- **关键验证**:BaseHTTPMiddleware 读 body 后能正确回放给下游 GraphQL(经典坑),已由 `test_origin_guard.py::test_mutation_with_origin_passes_and_executes` 钉死(带 Origin 的 mutation 真的执行、返回结果)。
- **开关** `REQUIRE_BROWSER_ORIGIN`(Nacos,默认 **false**):安全灰度。测试机开→验证真人投票不受影响→再上生产;改后需重启容器(B-017)。

**局限/误伤**:少数隐私插件会剥离 Referer/Origin——开启后这类用户投票会被拦。故默认关、可随时关;`["*"]` 下只要求"带头"(presence),配了域名则要求匹配。伪造头能过(可接受,成本已抬高)。

## 三、待办：端口收口（`:18000` 直连）

测试机后端 `:18000` 直接对公网发布(compose `18000:8000`),脚本可**完全跳过前端/nginx**直打后端。理想是只让后端经 nginx 反代访问、`:18000` 对公网关闭。

**⚠️ 阻塞点**:前端 CI 的 codegen **直连 `:18000/graphql`** 拉 schema(`vote-image.yml` 等 `TEST_SERVER_HOST:18000`)。直接关端口会**打断前端构建**。收口前须先把 codegen 改走 nginx 代理(`:8082/v12-be/graphql`)或改用 schema 文件。

**处置**:列为 B-048 后续项;端口收口是 defense-in-depth(减少攻击面 + 单一入口),Origin 校验才是实际拦懒脚本的控制点,不依赖端口是否公开。生产上线前**务必核实生产后端未暴露裸端口**。

## 四、与其它防线的关系

- 投票已要求 `vote_token`(登录=captcha+手机)——注册 captcha 是既有的真人闸。
- 可选更狠:提交时也要一次 captcha("此刻有真人")——UX 摩擦 + 每票成本,留作后手。
- 本项(Origin 校验)+ 端口收口 = "拦懒脚本";取证层 = "抓真人小号"。两者互补。
