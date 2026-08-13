# 结果统计层三方审计:前端需求 × Python 后端 × legacy Rust

> 日期:2026-08-14
> 方法:三份并行代码审计(Python `src/apps/result` + GraphQL 契约层 / Touhou-Vote `packages/result` origin/zfq_dev_fe / legacy `thvote-be/result-query` Rust),交叉核实。
> 目的:定位"结果统计/展示层"(区别于计票 compute)从 Rust 迁到 Python 的完整性缺口,及与前端页面需求的匹配度。

## 一、结论

**接口覆盖面基本迁全,真正的缺口是几处内部深度实现 + 一个大功能(高级搜索 DSL)。**

- Python 12 个 GraphQL `query_*` + `covote`/`reasons`(在 `result.py`,不在契约层)覆盖了 legacy 18 个接口的**接口面**:排名/单条/理由/趋势/CP/全局/完成率/问卷/问卷趋势/covote 都在。
- legacy 独有的**高级查询 DSL**(交叉分析过滤)Python 未实现——而前端 `AdvancedSearch` 组件**正在生成**这个 DSL 参数,是当前最实质的功能缺口。
- 其余桩点(covote 的相关性/互信息、往届对比、问卷趋势、同人本统计)多与前端"维护中占位页"或"数据未录入"配对,不是单方遗漏。

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
| **问卷趋势** questionnaireTrend | QuestionnaireDetail(✅ 拿 q11011 一条线) | 🔴 恒返回空 `Trends`(无问卷时间维度) | ✅ |
| **同人本统计** numDoujin | QuestionnaireDetail 的 globalStats 取 numDoujin(✅ 读) | 🔴 恒 0 硬编码 | ✅ global_stats 含 |
| **covote 关联**(cs 卡方/mi 互信息/cv 共投率) | characterConnect/MusicConnect(🔴 占位"维护中",入口已注释) | 🔴 `cs`/`mi` 恒 0,`cv` 真算;有 GraphQL `covote`+REST | ✅ 完整 |
| **高级搜索 DSL**(交叉分析过滤) | AdvancedSearch 组件(✅ **生成 query 参数**传各 detail 页) | 🔴 非空 query → 抛 `ADVANCED_SEARCH_NOT_IMPLEMENTED` | ✅ pest DSL,贯穿所有接口 |
| **作品提名结果** | Doujin 页(🔴 **全硬编码**,总票数 1272 字面量,不调后端) | —(无端点) | —(scraper 侧) |

## 三、缺口分类

### A. 前端在用、后端是桩 —— 真实功能缺口(会影响展示)

1. **高级搜索 DSL**(最大):前端 `AdvancedSearch` 把用户选择(角色/音乐/问卷题答案 + AND 组合)编码成 `query` 参数,经 `decodeAdditionalConstraint.ts` 传给 characterDetail/MusicDetail/CoupleDetail/QuestionnaireDetail。后端收到非空 query **直接抛 `ADVANCED_SEARCH_NOT_IMPLEMENTED`**——即用户一旦用高级搜索,目标页报错。对应 BACKLOG **B-050-后补5 / B-053**,需"按投票子集重算榜"能力(非后置过滤)。
2. **往届对比**:characterCompare/MusicCompare 是专门的对比页,后端 `*Last1/2` 全是 `-1` 哨兵。前端用 `<0 ? '-'` 优雅降级(不报错,但对比列全空)。需 ① `compute_service` 传非空 `historical` ② 导入 `final_ranking` 历史(B-050-后补3 + B-057③)。
3. **问卷趋势**:QuestionnaireDetail 拿 questionnaireTrend 画一条线,后端恒空 → 图表空。需问卷 append-only 时间维度(B-050-后补2 同源)。
4. **numDoujin**:QuestionnaireDetail 的 globalStats 读 numDoujin,后端恒 0。同人本统计未做。

### B. 双方都停在占位 —— 要做才需两头补

- **covote / connect 页**:前端 characterConnect/MusicConnect 是"维护中"占位(入口已在 character.vue/Music.vue 注释掉),后端 `cs`/`mi` 恒 0。谁都没上,不阻塞;若要做,后端补相关性/互信息(B-050-后补8 已修 cv+人名,cs/mi 待补),前端补页面。

### C. 前端硬编码、不依赖后端

- **Doujin 页**:总票数 1272、提名前十、评论全是源码字面量,每届手改代码。后端无对应端点。若要数据化,前后端都要新建(优先级看运营是否接受手改)。

### D. 部署 / 联调前置 —— ✅ 已确认通路 OK

- 前端 result 走 GraphQL endpoint **`/res-be/graphql`**(不是 vote 的 `/v12-be`)。**2026-08-14 实测:测试机 `:8084/res-be/graphql` 返回 200**,nginx 反代到后端已就位,result 站可联调。
- 同日实测确认:`queryGlobalStats(voteYear:12)` 正常返回(`numDoujin` 确为 0=桩);`queryCharacterRanking(query:"chars:[...]")` 确实抛 `ADVANCED_SEARCH_NOT_IMPLEMENTED`(A-1 实锤:前端一用高级搜索即报错)。

### E. 可维护性债(前端,记录待收敛)

- `voteYear: 11` + `voteStart: Date.UTC(2023,11,29,10)` 在 20+ 处 `useQuery` 逐字重复,没走已存在的 `lib/voteYear.ts`。跨届要全仓搜替。
- characterEvolution.vue 模板写死"投票时间 2022-06-17…"过期文案,与实际查询窗口不符(MusicEvolution 无此问题)。
- `/test` 调试路由(Test.vue)注册在生产路由表。
- 均属 Touhou-Vote 仓、B-055 前端缺口清单,跨仓跟踪。

## 四、优先级建议

1. **先确认 `/res-be` nginx 通路**(D)——不通则 result 站根本联调不了,是所有验证的前置,成本最低。
2. **高级搜索 DSL**(A-1)——前端已具备完整入口,后端一实现就点亮 AdvancedSearch 全功能;是"投入产出比"最高的一块,但也是设计量最大的(子集重算 + 与分段共用索引,B-050-后补5/B-053 同组)。
3. **往届对比**(A-2)——依赖导入上届 `final_ranking`(B-057③)+ 接通 `historical`;数据到位后是纯展示增益。
4. **问卷真实数据**(B-054,运营侧)——问卷结果/性别/趋势多项受此阻塞,管道都通,等录题。
5. covote cs/mi、numDoujin、Doujin 数据化 —— 低优先,与前端占位页/运营手改现状匹配,按需再做。

## 五、与 BACKLOG 的映射

- A-1 高级搜索 = B-050-后补5 + B-053(交叉分析,同组共用 `vote_id→{题code:[选项code]}` 索引)
- A-2 往届对比 = B-050-后补3 + B-057③(导入 year=11 final_ranking)
- A-3 问卷趋势 = B-050-后补2(需 raw_* append-only)
- B covote cs/mi = B-050-后补8 尾巴
- B-054 问卷录题阻塞问卷结果/性别/趋势的真实数据
- D `/res-be` 通路、E 前端债 = 新增(见 BACKLOG 更新)
