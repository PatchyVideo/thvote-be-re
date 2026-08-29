# 结果统计层三方审计:前端需求 × Python 后端 × legacy Rust

> 日期:2026-08-14
> 方法:三份并行代码审计(Python `src/apps/result` + GraphQL 契约层 / Touhou-Vote `packages/result` origin/zfq_dev_fe / legacy `thvote-be/result-query` Rust),交叉核实。
> 目的:定位"结果统计/展示层"(区别于计票 compute)从 Rust 迁到 Python 的完整性缺口,及与前端页面需求的匹配度。

## 一、结论

**接口覆盖面基本迁全,真正的缺口是几处内部深度实现 + 一个大功能(高级搜索 DSL)。**

- Python 12 个 GraphQL `query_*` + `covote`/`reasons`(在 `result.py`,不在契约层)覆盖了 legacy 18 个接口的**接口面**:排名/单条/理由/趋势/CP/全局/完成率/问卷/问卷趋势/covote 都在。
- legacy 独有的**高级查询 DSL**(交叉分析过滤)Python 未实现——而前端 `AdvancedSearch` 组件**正在生成**这个 DSL 参数,是当前最实质的功能缺口。
- 其余桩点(covote 的相关性/互信息、往届对比、问卷趋势、同人本统计)多与前端"维护中占位页"或"数据未录入"配对,不是单方遗漏。

**勘正(2026-08-29,B-050-后补2 Step 1+2 完成后回看)**:本表当初把 legacy Rust 的 `trend` 标记为 ✅"真实现",实为对 legacy `result-query` 源码的误读——legacy 读的是外部 ETL 物化的 `votes` 单快照集合,`trend` 实质是"按最新提交时间分桶"的近似值,**没有**净增量能力(改票/减票在 legacy 里从未真正体现为负增量分桶);前端"改票会在趋势图上体现为减票"的直觉文案,legacy 从未实现过,不是本仓库迁移期间引入的退化。本仓库两步交付:Step 1(2026-08-29)先对齐 legacy 的近似口径接通 `queryQuestionnaireTrend`;Step 2(同日)把 `raw_*`/`paper_answer` 改造为 append-only 存储后,用真实净增量重写全部 `trend`/`trend_first`(角色/音乐/CP/问卷四类),**在这一点上已超越 legacy**。详见 CHANGELOG 2026-08-29 两条目、`src/apps/result/trend.py::net_delta_trends`。

## 二、三方对照表

能力 → 前端是否在用 / Python 后端状态 / legacy 有无。状态:✅真实现 · 🟡数据受阻(代码通缺数据) · 🔴桩(硬编码/恒空/未实现)。

| 统计能力 | 前端页面(在用?) | Python 后端 | legacy Rust |
|---|---|---|---|
| 角色/音乐/CP **排名** | character/Music/Couple + Detail(✅在用) | ✅ `compute_ranking`/`compute_cp_ranking` 真算 | ✅ |
| **单条详情** | *SingleDetail(✅) | ✅ 按序号取单条 | ✅ |
| **投票理由** reasons | *Reason 页(✅) | ✅ 内嵌 `RankingEntry.reasons` + REST `/reasons/` | ✅ 独立接口 |
| **趋势** trend(逐小时) | *Evolution / *SingleDetail(✅) | ✅ compute 逐小时分桶真算 | ✅ |
| **双向性别条件概率** | characterDetail/CoupleDetail(✅ male/femalePercentagePer{Char,Total}) | ✅ `build_segment_map`+`_segment_breakdown` 真算 | ✅ |
| **CP 主动方占比** aActive/bActive/cActive/noneActive | CoupleDetail(✅) | ✅ `compute_cp_ranking` 真算 | ✅ |
| **完成率**(逐题) | Questionnaire 组件(✅) | ✅ `compute_completion_rates` 真算 | ✅ 动态字段扫描 |
| **问卷结果**(选项计数+性别交叉) | Questionnaire 组件 / QuestionnaireInputDetail(✅) | 🟡 管道真算,数据受阻(线上问卷占位、code 未回填,B-054) | ✅ |
| **往届对比** *Last1/2 | characterCompare/MusicCompare(✅ 有专门对比页) | 🔴 `-1` 哨兵,`compute_service` 给 compute 的 `historical` 恒传 `{}`;且 `final_ranking` 历史未导入(B-057③) | ✅ 读 `final_ranking_char/music` |
| **问卷趋势** questionnaireTrend | QuestionnaireDetail(✅ 拿 q11011 一条线) | ✅ `net_delta_trends` 真实净增量(2026-08-29,B-050-后补2 Step 1+2) | 🟡 近似(见"一、结论"勘正) |
| **同人本统计** numDoujin | QuestionnaireDetail 的 globalStats 取 numDoujin(✅ 读) | 🔴 恒 0 硬编码 | ✅ global_stats 含 |
| **covote 关联**(cs 卡方/mi 互信息/cv 共投率) | characterConnect/MusicConnect(🔴 占位"维护中",入口已注释) | 🔴 `cs`/`mi` 恒 0,`cv` 真算;有 GraphQL `covote`+REST | ✅ 完整 |
| **高级搜索 DSL**(交叉分析过滤) | AdvancedSearch 组件(✅ **生成 query 参数**传各 detail 页) | ✅ lark DSL 解析 + 子集重算真算(2026-08-14 实现,待部署;10 个 query* 端点接通,取代 `ADVANCED_SEARCH_NOT_IMPLEMENTED`) | ✅ pest DSL,贯穿所有接口 |
| **作品提名结果** | Doujin 页(🔴 **全硬编码**,总票数 1272 字面量,不调后端) | —(无端点) | —(scraper 侧) |

## 三、缺口分类

### A. 前端在用、后端是桩 —— 真实功能缺口(会影响展示)

1. **高级搜索 DSL**(最大):前端 `AdvancedSearch` 把用户选择(角色/音乐/问卷题答案 + AND 组合)编码成 `query` 参数,经 `decodeAdditionalConstraint.ts` 传给 characterDetail/MusicDetail/CoupleDetail/QuestionnaireDetail。~~后端收到非空 query **直接抛 `ADVANCED_SEARCH_NOT_IMPLEMENTED`**——即用户一旦用高级搜索,目标页报错。~~ **✅ 已解决(2026-08-14,分支 `feat/advanced-search-dsl`,待部署)**:后端已实现"按投票子集重算榜"(lark DSL 解析 + `subset.py` 圈子集 + 复用 compute 纯函数整包重算,非后置过滤),对应 BACKLOG **B-050-后补5**(已归档)/ **B-053**(共用同一子集原语,尚未做)。
2. **往届对比**:characterCompare/MusicCompare 是专门的对比页,后端 `*Last1/2` 全是 `-1` 哨兵。前端用 `<0 ? '-'` 优雅降级(不报错,但对比列全空)。需 ① `compute_service` 传非空 `historical` ② 导入 `final_ranking` 历史(B-050-后补3 + B-057③)。
3. **问卷趋势**:QuestionnaireDetail 拿 questionnaireTrend 画一条线,后端恒空 → 图表空。需问卷 append-only 时间维度(B-050-后补2 同源)。**✅ 已解决(Step 1+2,2026-08-29)**:Step 1 先接通近似分桶,Step 2 落地 append-only 存储后改为真实净增量,详见"一、结论"勘正段与 CHANGELOG。
4. **numDoujin**:QuestionnaireDetail 的 globalStats 读 numDoujin,后端恒 0。同人本统计未做。

### B. 双方都停在占位 —— 要做才需两头补

- **covote / connect 页**:前端 characterConnect/MusicConnect 是"维护中"占位(入口已在 character.vue/Music.vue 注释掉),后端 `cs`/`mi` 恒 0。谁都没上,不阻塞;若要做,后端补相关性/互信息(B-050-后补8 已修 cv+人名,cs/mi 待补),前端补页面。

### C. 前端硬编码、不依赖后端

- **Doujin 页**:总票数 1272、提名前十、评论全是源码字面量,每届手改代码。后端无对应端点。若要数据化,前后端都要新建(优先级看运营是否接受手改)。

### D. result 站部署拓扑与 `/res-be` 通道(2026-08-14 实测厘清)

前端 result 包(`packages/result`)Apollo client **硬编码相对路径 `/res-be/graphql`**(dev 与 zfq_dev_fe 一致);谁来接 `/res-be` 完全由部署环境的 nginx/proxy 决定,不同环境指向不同后端:

| 环境 | result 前端在哪 | `/res-be` → 后端 | 实测 |
|---|---|---|---|
| **本地 dev** | vite dev server | `vite.config.ts` proxy → `https://touhou.ai/vote-be`(**老 Rust**) | 源码 |
| **测试机(联调主场)** | `154.37.215.62:8084`(容器 `thvote-result`,`result-image.yml` 部署) | 容器 nginx → **我们的 Python 后端 `:18000`** | ✅ `:8084/res-be/graphql` 与 `:18000` 直连响应逐字一致,确认打到 Python |
| **生产** | **无独立 result 部署**:`vote.thwiki.cc/result/` 返回的是 vote 站 SPA fallback(title=第11回…),不是 result 站;result 无 Vercel 生产 CI(只有 `result-image.yml` 发测试机,对比 vote 有 `vote-ci.yml`) | `vote.thwiki.cc/res-be` POST=**405**(没接后端);生产真实结果后端是 `touhou.ai/vote-be/graphql`(**老 Rust**,POST=200) | ✅ |

**结论**:`/res-be` 是前端约定的相对 endpoint;**只有测试机把它反代到了我们的 Python 后端**——所以测试机 `:8084` 是一套完整的"我方 result 前端 → Python 后端"联调环境,可用。生产侧 result 尚无独立部署,结果数据仍走老 Rust `touhou.ai/vote-be`(待整体替换)。

同日实测另确认:`queryGlobalStats(voteYear:12)` 正常返回(`numDoujin`=0 桩);`queryCharacterRanking(query:"chars:[...]")` 抛 `ADVANCED_SEARCH_NOT_IMPLEMENTED`(A-1 实锤)。

### E. 可维护性债(前端,记录待收敛)

- `voteYear: 11` + `voteStart: Date.UTC(2023,11,29,10)` 在 20+ 处 `useQuery` 逐字重复,没走已存在的 `lib/voteYear.ts`。跨届要全仓搜替。
- characterEvolution.vue 模板写死"投票时间 2022-06-17…"过期文案,与实际查询窗口不符(MusicEvolution 无此问题)。
- `/test` 调试路由(Test.vue)注册在生产路由表。
- 均属 Touhou-Vote 仓、B-055 前端缺口清单,跨仓跟踪。

## 四、优先级建议

1. **先确认 `/res-be` nginx 通路**(D)——不通则 result 站根本联调不了,是所有验证的前置,成本最低。
2. **高级搜索 DSL**(A-1)——✅ **已完成(2026-08-14,分支 `feat/advanced-search-dsl`,B-050-后补5)**:前端已具备完整入口,后端已接通全部 10 个 `query*` 端点,子集重算复用 compute 纯函数(非后置过滤);与分段共用索引(`subset.py`)已就位,B-053 可直接复用。
3. **往届对比**(A-2)——依赖导入上届 `final_ranking`(B-057③)+ 接通 `historical`;数据到位后是纯展示增益。
4. **问卷真实数据**(B-054,运营侧)——问卷结果/性别/趋势多项受此阻塞,管道都通,等录题。
5. covote cs/mi、numDoujin、Doujin 数据化 —— 低优先,与前端占位页/运营手改现状匹配,按需再做。

## 五、与 BACKLOG 的映射

- A-1 高级搜索 = B-050-后补5 + B-053(交叉分析,同组共用 `vote_id→{题code:[选项code]}` 索引)
- A-2 往届对比 = B-050-后补3 + B-057③(导入 year=11 final_ranking)
- A-3 问卷趋势 = B-050-后补2(需 raw_* append-only)
- B covote cs/mi = B-050-后补8 尾巴 → **见 §六:需求文档无此页,降级/可弃**
- B-054 问卷录题阻塞问卷结果/性别/趋势的真实数据
- D `/res-be` 通路、E 前端债 = 新增(见 BACKLOG 更新)

## 六、需求文档对照与优先级修正(2026-08-14 补,依据 `docs/VoileLabs-人气投票项目-需求文档-投票结果页面.md`)

通读结果页需求文档(942 行,2022 定稿 / 2026 规范化)后,把"需求要什么 × 后端现状"对齐,得到两处**认知修正**:

### 修正 1:covote / "同投" 不是需求项 —— 从缺口清单划掉

需求文档**没有**任何"同投关联分析"页面。全文只两处提"同投率"(§131、§149):它是**高级搜索筛选到某投票子集后,"票数占比"这一列改的名字**(占比语义此时变为"同投率")。因此:

- 前端 `characterConnect`/`MusicConnect` 两个"维护中"占位页(入口已注释)—— 需求未要求,**可直接弃**,不是待补页面。
- 后端 `compute_covote` 的 `cs`(卡方)/`mi`(互信息)桩(§三-B / B-050-后补8 尾巴)—— **需求无消费方,不必实现**。之前审计把它列为"缺口"是误判,据需求订正为"不做"。
- 真正要做的"同投率"= 高级搜索筛选下 `票数占比` 列的改名,属 P0 高级搜索的一部分,不是独立统计。

### 修正 2:高级搜索/筛选 DSL 是需求硬核心(P0),非可选增强

需求 §846-923 用近 80 行详规该组件:图形模式 + **指令模式 DSL**(`q<题ID>=<选项ID>`、`chars:[...]` OR、`chars_first=`、`musics:[...]`、`musics_first=`、`AND`/`OR`/括号),且明确语义是"**从投票中筛选:交叉引用投票数据,仅显示满足约束的投票者所投出的结果**"——即**按投票者子集重算榜**,非后置过滤。适用范围:角色/音乐/组合的本届+上届对比页 + 问卷结果页。~~后端全桩(`ADVANCED_SEARCH_NOT_IMPLEMENTED`),是结果页第一短板。~~ **✅ 已实现(2026-08-14,分支 `feat/advanced-search-dsl`,待部署)**:曾是结果页第一短板,现已接通。

### 需求 × 后端 逐块对照

| 需求章节 | 后端 | 判定 |
|---|---|---|
| 搜索与筛选组件 §846(DSL/子集重算) | ✅ 已实现(2026-08-14,待部署) | **P0**,需求硬核心,已完成 |
| 上届对比 §172/§430 | 🔴 -1 哨兵+历届未导入 | P1,需导入 final_ranking |
| 投票演进比对 §222(多角色≤10) | ✅ trend 真算、query 支持多 name | 已满足 |
| 详情页问卷回答 §307(旭日/雷达/地图/男女相对比例) | 🟡 管道真算,受 B-054 占位阻塞 | 数据前置 |
| 组合主动率 §583 | ✅ 真算 | 已满足 |
| 投票理由 §334 | ✅ 内嵌 reasons+REST | 已满足 |
| 问卷结果页 §702(全局/完成率/演进线) | ✅ 全局·完成率真算;🔴 问卷演进线恒空 | P1(演进线) |
| 作品提名 §657 | 前端硬编码;需求 §700 自标 TODO"应改后端 API" | 低,组委会手动可接受 |

### 据需求订正后的优先级

1. **P0 高级搜索/筛选 DSL** —— 需求硬核心、覆盖最广、~~后端全桩~~ **✅ 已实现(2026-08-14,分支 `feat/advanced-search-dsl`,待部署)**;"同投率"列也在其内。设计量最大(子集重算 + 与问卷分段共用 `vote_id→{题:[选项]}` 索引),已出设计稿并落地。
2. **P1 上届对比** —— 导入历届 `final_ranking`(B-057③)+ 接通 `historical`(B-050-后补3)。
3. **P1 问卷演进线** —— 后端恒空(B-050-后补2,需 raw_* append-only)。
4. **数据前置 B-054** —— 问卷回答分布整块依赖真实问卷录入。
5. **划掉/最低**:covote `cs`/`mi`(需求无此页);作品提名后端化(需求自标 TODO)。
