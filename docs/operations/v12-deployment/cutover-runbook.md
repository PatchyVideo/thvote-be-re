# v12 上线期切流、回退与灾备预案

更新于 2026-11-19（北京时间）。执行角色为发布负责人、前端/Vercel 负责人、域名/网关负责人和数据库值班人。发布记录中填写各角色、执行时间及回退授权人。

## 1. 这次上线需要什么

| 项目 | 本次安排 |
| --- | --- |
| v12 前端切到 Python 后端 | **必须做。** 先部署同一发布版本的后端和 HTTPS 网关，再在投票与结果项目分别配置代理，通过预览验收后开放导航。 |
| 数据库可恢复 | **必须做。** 核对备份、日志备份和实际可恢复时间范围，在隔离实例演练恢复，记录耗时及数据校验结果。生产放票前签字确认可接受的恢复时间与数据损失窗口。 |
| 数据库高可用 | **投票正式开放前优先落实。** 先在阿里云控制台核对版本、实例系列、可用区、主备状态和复制模式。能用托管跨可用区 HA 时，优先采用同一 RDS endpoint。现有实例若不能原地调整，就先验证迁移路线和停写窗口。若要在 HA 就绪前开放正式投票，由发布负责人按已实测的恢复能力决定是否延期。 |
| 第二机房 | **保留应用切换预案。** Vercel 可独立提供前端，不需要在备机房再跑一套前端。阿里云 ALB + ECS 伸缩组作为生产热备池，容量、隔离和到生产 RDS 的链路验收通过后接入。 |
| 跨地域数据库灾备 | 只有地域故障也必须迅速恢复写入时，才需要独立灾备实例和复制链路。上线当晚优先做好备份恢复和写入保护，再按业务恢复目标决定是否投入。 |

原稿将「Serverless / 无可见流复制」直接认定为「无托管备机」，并给出了分钟级 RTO 和秒级 RPO。数据库实例系列需要控制台确认，恢复指标需要演练计时。应用切机房、托管主备切换、独立实例接管以及 PITR 都有不同的前置条件。

## 2. 2026-11-18 核对的生产状态

| 项目 | 证据与状态 |
| --- | --- |
| 生产应用 | SSH 核对生产主机：16 vCPU，约 15.6 GiB 内存、170 GiB 可用盘。/opt/thvote/prod 下三个常驻容器，后端镜像 ID **0d5022cde4cf**，Alembic 当前 **0022**。容器监听 8000，主机公开 18000；核对时 80/443 未监听。 |
| 测试应用 | 测试后端 :18000 的 /health 实测返回 status=ok、db_status=ok、vote_year=12；测试机承担独立测试环境。 |
| 生产数据库 | 应用侧只读 SQL 确认 prod_db、PostgreSQL **18.3**、当前是可写主节点、pg_stat_replication 无可见记录。当前阿里云 CLI 查询不到该实例的控制面记录。控制台的实例系列、托管备节点与最新可恢复时间仍待核实；旧稿记载有 7 天备份及 PITR。 |
| 生产入口 | api.touhou.vote 公共 DNS 返回 NXDOMAIN；需新建 HTTPS 入口。vote.thwiki.cc/v11/ 有 HTML，GET /res-be/graphql 返回 200 HTML，POST 返回 405。touhou.vote 在本次探测网络返回 429，导航与历史路径需从常用访问网络复验。 |
| 候选版本 | 后端仓库的单一迁移头为 **0023**。前端两个应用的路由基准仍是 /v11/，投票 API 前缀已经是 /v12-be，结果 API 前缀是 /res-be。镜像从冻结提交构建并记录 GHCR **manifest digest**，生产容器的本地 image ID 用于现场辨认。 |

[生产后端常驻架构图](architecture/production-backend.svg) · [上线窗口自动切流图](architecture/cutover-window.svg) · [备站承载图](architecture/standby-serving.svg) · [建设与值班交接](README.md)

## 3. 生产新前端如何接上新后端

### 3.1 冻结版本和发布地址

1. 发布负责人记录两个仓库的 commit、GitHub Actions run ID、拟发布和上一稳定后端 digest、Alembic 当前与目标版本、Vercel 两个项目的候选/现网部署 ID 和域名绑定。发布窗口内冻结并发部署。
2. 投票页建议用独立的生产 Vercel 项目及域名 **https://v12.touhou.vote/v12/**。当前投票的 Vue Router 基准在 thvote-fe/packages/vote/src/main/main.ts，Vite 资源目录在 packages/vote/vite.config.ts。发布分支将 /v11/ 基准和 v11/assets 更新到 v12，核对深链、刷新、二维码和外部跳转。结果项目沿用已出现的 **https://vote.thwiki.cc/v11/**，发布前实测页面显示第 12 回并向后端请求第 12 回数据。若该域名经项目管理员核对还在承担旧版业务，另绑 v12 结果域名后再开放。
3. touhou.vote 保留导航项目；在最终开放时才添加 v12 投票和结果两个链接。逐一记录旧版的主机、路径与源站。尤其要验证 touhou.vote 上既有 /v11/ 和 /res-be/* 的实际去向，v12 的 /res-be 规则只加到 v12 结果项目。

### 3.2 先发布后端并建 HTTPS 入口

- [后端流水线](../../../.github/workflows/deploy-test.yml)负责检查、构建、测试部署和手动生产发布。代码路径 push 只触发测试发布；文档变更不命中部署路径。生产工作目录默认是 /opt/thvote/prod，测试为 /opt/thvote/test。
- [Compose 模板](../../../docker/docker-compose.prod.yml)由流水线下发并覆盖部署机的 docker-compose.yml。生产 Redis/R-Nacos 由独立的 docker-compose.deps.yml 维护，容器共享 thvote-net。生产 Nacos 使用 thvote-prod 环境和 thvote_be 配置项（DEFAULT_GROUP），访问方法见 [Nacos 配置指南](../nacos-config-center.md)。
- 发布前核对 EXPOSE_API_DOCS、管理员 IP 白名单和可信代理配置、admin 密钥、CORS Origin、真实投票起止时间，以及登录/验证码配置。管理接口走受控入口；从两个网络验证代理识别和匿名访问受限。登录接入按[配置清单](../login-config-checklist.md)复验。

1. 数据库值班人确认最近可恢复时间点和恢复实例权限，记录发布前时间戳。检查生产 Nacos 的数据库指向 prod_db、投票窗口、验证码与短信/邮件出口、JWT 配置。核对 DEK 文件权限和挂载（0400、容器 UID 1000），以及提前留存的旧镜像与回滚方式。
2. 从已冻结的 main 在 GitHub Actions 运行 **Test & Deploy Backend**。先用默认的 deploy_prod=false 验证测试端。确认发布窗口后，选择同一冻结的 main 提交，开启 deploy_prod 且保留测试。正式 run 先部署测试，生产 job 复用**该 run 的同一 GHCR digest**，由 job 执行一次 Alembic 升级再重建生产应用。确认 run 的 head SHA；备节点只启动应用。推送 main 走测试环境。人工触发命令如下。

   ~~~bash
   gh workflow run deploy-test.yml --repo PatchyVideo/thvote-be-re \
     --ref main -f skip_tests=false -f deploy_prod=true
   ~~~

3. 在生产机通过受控 SSH 核对后端版本和依赖。当前目标迁移 0022 → 0023 给 paper_answer 加入 invalidated 标志，迁移完成后确认旧镜像与新 schema 的兼容性才可把旧 digest 记为可回退。迁移失败时停止发布、核对实际 DB revision 和容器状态；该 workflow 会先写 .env，后启动容器，故障后需将 .env 的 BACKEND_IMAGE 与实际可用版本对齐。

   ~~~bash
   cd /opt/thvote/prod
   docker compose ps backend
   docker compose -f docker-compose.deps.yml ps
   docker inspect thvote-backend --format '{{.Image}} {{.State.Health.Status}}'
   docker compose exec -T backend alembic current
   curl -fsS http://127.0.0.1:18000/health |
     jq -e '.status == "ok" and .db_status == "ok" and .vote_year == 12'
   ~~~

4. 在主站配置 api.touhou.vote 的受控 HTTPS 网关（如宿主 Nginx:443），转发到 127.0.0.1:18000。签发证书、校验 SNI/Host、用 nginx -t 验证后 reload。网关发布下表目标路径及启用的 OAuth callback，其余路径默认 404；健康检查路径只返回所需状态。将后端原始端口限制到可信接入链路。先盘点现有直连并迁移，避免打断部署和检查。Cloudflare 用代理模式时设 Full (strict) 并验证回源证书；仅用 DNS 时 A/AAAA 记录指向已有合格 443 监听的源站。
5. 网关保留方法、请求体、查询串、Authorization、Cookie、Origin 和必要的转发头。根据 Vercel / Cloudflare 的实际传递链配置真实客户端 IP，可信网关重写 X-Real-IP，后端只信任配置的代理来源。确认来自两条测试网络的访问可被正确限流，代理和前端缓存均跳过登录、发码、提交等接口。超时后遇到提交状态未知，先回读状态；避免网关重放写请求。
6. 如果生产启用了 QQ 或 THBWiki 绑定，核对 Nacos 的 SSO_CALLBACK_BASE_URL、供应商登记的回调 URL、回调后的浏览器跳转。后端原生回调路径为 /api/v1/user/sso/qq/callback 和 /api/v1/user/sso/thbwiki/callback。校验验证码站点域名与前端实际 Origin，检查现有会话切换行为和真实账号重登。

下面是主站宿主 Nginx 的最小 API vhost。证书路径按实际签发位置填写；真实 IP 配置应在确认受信代理来源与头部后补上，再开放真实登录。开启 SSO 前单独放行已登记的 callback，并用真实浏览器验收。

~~~nginx
server {
    listen 443 ssl;
    server_name api.touhou.vote;
    ssl_certificate     /etc/letsencrypt/live/api.touhou.vote/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.touhou.vote/privkey.pem;

    location ~ ^/(health|graphql|user-token-status|api/v1/(vote-objects/.+|questionnaire/structure|autocomplete/search|scraper/scrape))$ {
        proxy_pass http://127.0.0.1:18000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_connect_timeout 5s;
        proxy_read_timeout 30s;
        proxy_next_upstream off;
        proxy_hide_header Cache-Control;
        add_header Cache-Control "no-store" always;
    }

    location / { return 404; }
}
~~~

保存后执行 `sudo nginx -t`。已运行则用 `sudo systemctl reload nginx`，新装则用 `sudo systemctl enable --now nginx`。从受控资产表读取 PRIMARY_ORIGIN_IP 后，直连源站演练可用 `curl --resolve api.touhou.vote:443:"$PRIMARY_ORIGIN_IP" https://api.touhou.vote/health` 验证 SNI、证书与 JSON；若用 Cloudflare Origin CA 签发的回源证书，用受信 CA 验证源站并通过 Cloudflare 公网入口复验。

### 3.3 两个 Vercel 项目的 rewrite

投票配置文件为 thvote-fe/packages/vote/public/vercel.json；结果配置文件为 thvote-fe/packages/result/public/vercel.json。合并进各自 rewrites 数组，放在 SPA 的 /index.html 兜底规则前，保留现有静态资源及历史规则。发布前确认构建产物 dist/ 内实际带了对应配置。

| 项目 | 浏览器同源路径 | 目标（https://api.touhou.vote 后的路径） |
| --- | --- | --- |
| 投票 | /v12-be/vote-objects/:path* | /api/v1/vote-objects/:path* |
| 投票 | /v12-be/questionnaire/:path* | /api/v1/questionnaire/:path* |
| 投票 | /v12-be/doujin/api | /api/v1/scraper/scrape |
| 投票 | /v12-be/:path* | /:path*（包括 /graphql、/user-token-status 和 /api/v1/autocomplete/search） |
| 结果 | /res-be/:path* | /:path*（包括 /graphql、/api/v1/questionnaire/structure 和 /api/v1/vote-objects/*） |

投票项目的新增规则按顺序为：

~~~json
[
  { "source": "/v12-be/vote-objects/:path*", "destination": "https://api.touhou.vote/api/v1/vote-objects/:path*" },
  { "source": "/v12-be/questionnaire/:path*", "destination": "https://api.touhou.vote/api/v1/questionnaire/:path*" },
  { "source": "/v12-be/doujin/api", "destination": "https://api.touhou.vote/api/v1/scraper/scrape" },
  { "source": "/v12-be/:path*", "destination": "https://api.touhou.vote/:path*" }
]
~~~

结果项目新增：

~~~json
[
  { "source": "/res-be/:path*", "destination": "https://api.touhou.vote/:path*" }
]
~~~

当前仓库的 **Vote CI 实际部署 packages/result**，对 dev 上的结果目录或锁文件变更执行 Vercel --prod。Navigator CI 同样直发生产；vote-image.yml 自动部署测试机。切流变更先用发布分支构建。两个项目独立验收，先确认各自的 Vercel 项目 ID、域名归属和重写配置。

在冻结的前端源码目录，用 CI 对应的 Node 与 pnpm 版本构建。GRAPHQL_SCHEMA_URL 填同 digest 后端的受控 schema 地址。

~~~bash
pnpm install --frozen-lockfile
export GRAPHQL_SCHEMA_URL='http://<已验收的测试后端>:18000/graphql'
pnpm --filter @touhou-vote/vote run codegen
pnpm --filter @touhou-vote/vote run build
pnpm --filter @touhou-vote/result run codegen
pnpm --filter @touhou-vote/result run build
~~~

将两个 dist/ 分别复制到各自的发布目录（包含 vercel.json 和隐藏的静态文件），在两个目录各自确认 `vercel link` 指向正确项目。选 **Other / 静态站点**，沿用现行 CI 上传静态产物的方式。分别运行 `vercel deploy --prod --skip-domain`，保存两条部署专属 URL；这会创建已经使用生产环境设置的候选部署，正式域名继续指向原部署。先在这两条 URL 验收，受 Deployment Protection 保护时用授权浏览器或 `vercel curl`。 [Vercel 分阶段发布](https://vercel.com/docs/deployments/promoting-a-deployment)

### 3.4 验收后开放流量

1. 用同一个候选部署依次检查 HTTPS 网关、Vercel 预览地址、生产域名。以下脚本可重复使用，VOTE 和 RESULT 先填两个预览源，再填两个生产源。生产浏览器端 API 请求必须出现 JSON，状态码 200 的 SPA HTML 也算失败。

   ~~~bash
   set -euo pipefail
   API=https://api.touhou.vote
   VOTE=https://v12.touhou.vote
   RESULT=https://vote.thwiki.cc
   vote_year=12

   graphql_ping() {
     curl -fsS --max-time 15 -H 'Content-Type: application/json' \
       --data '{"query":"{ __typename }"}' "$1" |
       jq -e '.data.__typename == "Query" and (.errors | not)'
   }

   curl -fsS --max-time 10 "$API/health" |
     jq -e '.status == "ok" and .db_status == "ok" and .vote_year == 12'
   graphql_ping "$API/graphql"
   graphql_ping "$VOTE/v12-be/graphql"
   graphql_ping "$RESULT/res-be/graphql"

   curl -fsS --max-time 15 "$VOTE/v12-be/vote-objects/characters?vote_year=$vote_year" |
     jq -e 'type == "object" or type == "array"'
   curl -fsS --max-time 15 "$VOTE/v12-be/questionnaire/structure" |
     jq -e 'type == "object"'
   curl -fsS --max-time 15 "$RESULT/res-be/api/v1/questionnaire/structure" |
     jq -e 'type == "object"'
   ~~~

2. 浏览器验收投票页深链/刷新、验证码和既有账号登录、token 状态、候选加载/搜索、问卷完成判定、投票保存与回读、二创抓取及逐条反馈、导出卡片图片；结果页验收榜单、问卷、候选资源及届次。写入场景优先在同 digest 的测试环境完成。生产只使用明确授权且有处置方案的验证账号和记录，确保结果统计不会混入冒烟数据。
3. 前端负责人按项目运行 `vercel promote <已验收的生产候选部署 URL>`，记录实际绑定的部署 ID，在正式域名复跑上述探针及浏览器验收。导航负责人最后开放 v12 链接；确认老链接、老 API 以及结果站代表页面仍可请求。
4. 发布负责人值守首个流量窗口，按切流前基线比较 5xx、GraphQL errors、登录/写入成功率、P95、DB 连接与锁、Redis、Nacos、磁盘和容器重启。若 API 返回 HTML、登录/提交持续失败、出现错库或数据不一致，立即停止导流并按下节回退。

## 4. 回退顺序

| 故障 | 操作 |
| --- | --- |
| 新前端／rewrite 问题 | 先撤导航上的 v12 链接；分别将受影响的 Vercel 项目回退到已记录的上一稳定生产部署。复跑公开域名探针、直接链接及旧版回归。 |
| HTTPS 网关／源站错误 | 恢复已验收的网关配置或源站池并复验。v12 写流量暂时封口，页面显示维护状态；已打开页面也需受保护。保留并核对已接收的提交。 |
| 后端新镜像问题 | 先停 v12 写入并等待在途请求完成；检查迁移后的 schema 能否运行上一版本。兼容时将生产 BACKEND_IMAGE 指回已记录的上一 digest，运行 docker compose up -d --no-deps --force-recreate backend，检查 DB 状态、登录及投票回读。0023 的降级会移除 invalidated 标志；需要降级时先由数据库负责人核对已写数据和恢复路径。 |
| 发现错库、复制异常或写入状态不明 | 网关先封写，锁定唯一权威库，记录故障窗口、当前 endpoint 和请求状态；核对投票回读后再开放。禁止以旧版 API 处理 v12 写入。 |

已生成接管库上的新事务时，回切必须先解决这些事务如何保留。只改 DNS 或把旧库重新打开会让数据分叉。

## 5. 有故障时的接管步骤

### 5.1 只切应用机房

1. 建设前置、探测阈值和通知按[交接文档](README.md#4-自动切流实施清单)验收。生产主、备后端运行同一 digest 并访问同一 RDS 写入入口。备池的 Redis、Nacos、DEK 与时序配置验收通过后登记到 Cloudflare。两个站点的就绪状态由独立监控判断。
2. 主池持续失败、多个观测点一致且备池就绪并有足够容量时，控制器更新当前服务池，读回路由，通过两个正式前端复验 JSON/业务响应，并将状态和结果通知值班。共享数据库故障或两池不可用时，系统封写并进入独立维护端点。
3. 接管后备池保持为当前服务池。值班人继续查看独立监控，核对请求失败率、扩容和数据库连接。维护测试服务器的现有测试职责；它可以持续提供公开入口的辅助探针。
4. 主站恢复后在隔离接入点验收版本和依赖，完成稳定窗口、容量及回读检查后，由值班人确认回切。切回后经两个正式前端复验，待备池排空请求后恢复热备。
5. 控制器不可用或执行失败时，值班人先接管自动化的路由写入权限，核对健康池和唯一写库，再通过 Cloudflare LB 界面切到合格源站或维护端点，复验并发送告警。事件结束后对齐实际路由与控制器记录，再恢复自动化。

### 5.2 托管 RDS HA

1. 上线前由数据库负责人在控制台确认**实际**系列、主/备可用区和复制模式，核对能否按当前地域及 PostgreSQL 18 版本购买、转换或迁移。阿里云文档同时列有基础版和高可用版 Serverless，当前创建 Serverless 指南还注明不支持 PostgreSQL 18；以现有实例页面、目标规格和开通结果为准。
2. 生产连接使用 RDS 的稳定 endpoint。预生产先做一次控制台 **主备切换**，记录控制台事件、旧连接断开、应用重新连通及首笔成功写入的时间。应用端测试 SQLAlchemy 池能否自行恢复；只在池迟迟无法恢复时按站点重建后端或连接池。
3. 事故时设置写入维护状态，查看 RDS 故障和切换记录。在托管切换完成后验证 endpoint 能连接、事务只写在当前主节点、Alembic revision 正确、业务可回读，再开放写入。跨地域故障另按独立实例或备份恢复处理。托管主备使用原 RDS endpoint。

### 5.3 独立灾备库接管（仅在已建成并演练后使用）

1. 数据库负责人先记录源/目标实例 ID、源端最后确认提交点、目标已应用位置、复制延迟与预计丢失范围。DTS 逻辑同步单独验收 DDL、sequence、权限、约束及漏表；如果是物理流复制，才用 WAL/LSN 与恢复状态作为接管凭证。
2. 所有 v12 入口封写，停止相关后台/运维写入，断开或隔离旧主写连接并验证隔离。若旧主状态未知且无法证明已隔离，持续停写并升级决策。源可用时等目标追平；源不可用时由负责人按已知最后恢复点批准损失窗口。
3. 按已选产品执行主库接管。托管的独立 RDS/DTS 按实际同步任务的切换流程；物理备机按该产品支持的提升操作。保证**只有一个可写主库**，暂停会覆盖目标的同步任务，检查 sequence 和 schema。
4. 在两个站点对应的生产 Nacos 中改用新的 RDS endpoint，核对 DATABASE_URL 与会优先覆盖的 DB_HOST 等独立字段。确认 TLS 主机名、白名单和账户权限，重建后端/连接池。做只读校验和有授权的单次写入回读，再恢复服务。两站均故障时，先恢复数据库权威入口，再放备机房流量。
5. 旧主恢复后保持隔离，依据新的权威数据重建。原库回切需有一次新计划和验收。

### 5.4 误删、逻辑损坏或没有可接管备库

1. 立即封写，留存故障时间、审计日志和当前快照。确认事故前最后正确时间点。
2. 在 RDS 控制台把备份或 PITR 恢复到**独立实例**，校验 prod_db、Alembic、主键和序列、关键业务记录与 DEK 解密；核对事故窗口内要补回的有效提交。
3. 数据负责人根据损坏范围决定修复少量记录或整体接管。整体接管沿用上节唯一写主、Nacos 与连接池检查流程。记录实际可恢复点和开放写入时间。

## 6. 发布窗口记录

- [ ] 基线、两仓 commit、manifest digest、新旧 Vercel 部署 ID、域名负责人和回退授权人已记录
- [ ] 现网旧版入口从常用网络复验；v12 上线 URL 和导航链接审核
- [ ] RDS 控制台系列与备份窗口确认，隔离恢复通过；业务方签字确认 RTO/RPO 和开票门槛
- [ ] 生产镜像、Alembic、Nacos、Redis 和 DEK 核对通过
- [ ] API HTTPS、投票与结果 rewrite、GraphQL 业务响应和浏览器链路验收通过
- [ ] 回退演练通过；阿里云备池容量、状态类依赖、自动切流、独立监控和通知按交接清单验收
- [ ] 域名提升、导航开启、发布观察和异常处置均有记录

[阿里云 RDS Serverless 规格](https://www.alibabacloud.com/help/en/rds/apsaradb-rds-for-postgresql/create-a-serverless-apsaradb-rds-for-postgresql-instance) · [阿里云 RDS 主备切换](https://www.alibabacloud.com/help/en/rds/apsaradb-rds-for-postgresql/switch-workloads-over-between-primary-and-secondary-apsaradb-rds-for-postgresql-instances) · [Vercel 外部 rewrite](https://vercel.com/docs/routing/rewrites) · [Vercel 回退](https://vercel.com/docs/instant-rollback) · [Cloudflare 代理模式](https://developers.cloudflare.com/load-balancing/understand-basics/proxy-modes/) · [Cloudflare 支持的代理端口](https://developers.cloudflare.com/fundamentals/reference/network-ports/)
