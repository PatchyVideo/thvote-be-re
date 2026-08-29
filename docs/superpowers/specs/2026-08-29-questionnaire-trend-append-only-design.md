# 问卷趋势 + append-only 提交历史 设计稿(B-050-后补2)

> 日期:2026-08-29
> 状态:已批准(用户拍板:分两步交付,存储选型方案 1「原表就地 append-only」)
> 前置调研:三方并行审计(legacy Rust `thvote-be` / 前端 `Touhou-Vote/packages/result`@renko_dev / Python 现状),结论见 §一

## 一、调研结论(设计前提)

1. **legacy Rust 的 trend 也是近似值**。submit-handler 对 Mongo `raw_*` 是 append-only(`insert_one`),但 result-query 读的是外部 ETL 物化的 `votes` 集合(每人一条、已去重到最新提交),trend 把这唯一一条的 `created_at` 落小时桶——与 Python 现状(`compute_ranking` 按最新行分桶)**同一算法**。单次快照内不可能出现负增量;前端文案「减少的票数是因为改票去掉了该角色」描述的语义 legacy 从未真正实现。
2. **legacy 问卷趋势** = paper_result 缓存旁路产物:回答了题 qX 的提交按整卷提交时刻(`paper_meta.created_at`)分桶;`trend_first` 恒空(问卷无本命概念)。
3. **前端契约**(renko_dev 实测):`Trends { trend, trendFirst: [VotingTrendItem { hrs, cnt }] }`,`hrs` 为相对 `voteStart` 的小时偏移(前端用作数组下标,自己补零、自己累计),`cnt` 为**该桶净增量**(允许负数,前端直接画)。`queryQuestionnaireTrend` 前端只传 `['q11011']` 当总票数进度代理,**携带高级搜索 DSL `query` 参数**;`queryCharacterTrend`/`queryMusicTrend` 不带 query;三个 `query*Single` 的内嵌 trend 带 query。
4. **Python 现状**:写路径收口在 `SubmitDAO._upsert`(删旧插新,单行);读路径收口在 `ComputeDAO._latest_per_vote`(本就按 `(created_at, attempt)` 取最新、天然兼容多行);`raw_*` 五表 schema 本就支持多行(legacy 多行选民);问卷 V2 写路径为「按 (vote_id, vote_year) 整卷删除再整批插入」(`questionnaire/dao.py:75-81`);`paper_answer` 有 `created_at`,带 `uq_paper_answer_voter_group` UNIQUE 约束;`queryQuestionnaireTrend` 契约层为恒空桩(`result_compat.py` `_query_questionnaire_trend_entries`);高级搜索子集重算复用 compute 纯函数,trend 逻辑留在纯函数内即自动继承。alembic head=`0016`,下一迁移 `0017`。

## 二、总架构:两步交付

| | 动什么 | 不动什么 | 交付物 |
|---|---|---|---|
| **Step 1 近似问卷趋势** | compute 纯函数 + 数据加载 + 契约层桩 | 存储层 | 前端问卷演进空图点亮,与 legacy 口径一致 |
| **Step 2 append-only + 真实 trend** | 写路径(_upsert/问卷 dao)+ 0017 迁移 + trend 算法 | GraphQL 契约 | 全类别真实净增量曲线 + 完整提交历史(反刷票取证) |

两步各自独立可部署、可回滚。Step 2 上线前的改票历史已被旧覆盖式存储抹掉,真实曲线从上线时刻起积累;上线时每人只有一行,净增量算法退化为现近似值,**自然兼容、无需回填**。

## 三、Step 1:近似问卷趋势(legacy 平价)

- `ComputeDAO.load_questionnaire_votes` 返回值增补每行 `created_at`。
- `compute_paper_results` 纯函数:每题结果增加 `trend` 字段(稀疏 `[{hrs, cnt}]`),按该题所在 group 行的 `created_at` 相对 `vote_start` 小时分桶,越界钳制 `max(0, min(bucket, total_hours-1))`(与角色 trend 同款);计数 = 回答该题的选民数,与该题既有选项计数同一选民集。`trend_first` 恒空(legacy 同)。
- 与 legacy 的**刻意差异**(记录):legacy 用整卷提交时刻,我们用该题所在 group 行时刻。V2 写路径整卷重写、同批行时间几乎相同,实际无差。
- 契约层:`_query_questionnaire_trend_entries` 恒空桩改为从 paper 结果(`result:{year}:paper:{qid}`,或 DSL 命中时的 `result:{year}:adv:{ver}:{fp}:...` 对应节)提取 trend;question_ids→code 映射沿用 `get_questionnaire` 现行逻辑(前端传 `q11011` 形态)。
- **DSL 子集路径零成本继承**:`_compute_filtered` 本来就调 `compute_paper_results`,trend 自动进 adv 缓存。

## 四、Step 2:append-only 存储(方案 1「原表就地」)

选型对比结论:`raw_*` schema 与 `_latest_per_vote` 当年就按多行设计,append-only 等于去掉人为删除动作;另立 history 表(方案 2)是为不存在的隔离需求付双写成本;事件溯源 diff(方案 3)与 payload 快照模型不合,均排除。

- **migration 0017**:
  - `paper_answer`:删 `uq_paper_answer_voter_group`;加 `attempt Integer NULL`;加 `(vote_id, vote_year)` 复合索引。
  - `raw_*` 五表:**零 DDL**。
- **写路径**:
  - `SubmitDAO._upsert`:去掉 `delete`,纯插入。`attempt` 递增、首提 `fill_duration_ms` 冻结的既有逻辑原样保留。
  - 问卷 dao `submit_answers`:去掉整卷 delete,整批插入,批内所有行带 `attempt = prev_max + 1`(首批=1)。
- **读路径**:
  - `_latest_per_vote` 一字不改。
  - 问卷读者(`compute_dao.load_questionnaire_votes`/`completion`/`get_answers`):取该 vote_id 的**最大 attempt 批次**的行;存量 `attempt IS NULL` 行按 `created_at` 最大批兜底(同一时刻整批写入,时间戳一致)。
- **`invalidated` 语义保持**:最新行被作废 → 选民整体出局(现行为);作废历史行对计票无效果(文档明示)。admin 监控列表将出现历史行——有分页/过滤,不阻塞;可后续补 attempt 列展示(不在本次范围)。
- **mock 生成器适配**:`generate_mock_votes.py` 插 `paper_answer` 时带 `attempt=1`;wipe 按 vote_id 前缀删,不受影响。

## 五、Step 2:真实净增量 trend 算法

新纯函数替换 `compute_ranking`/`compute_cp_ranking` 内的近似分桶(函数签名改为吃全历史行:`list[(vote_id, created_at, attempt, items)]` 形态):

- 对每个选民按 `(created_at, attempt)` 升序遍历快照序列,做集合 diff:
  - 首个快照:全体实体 +1,落该快照小时桶;
  - 后续快照:新增实体 +1、消失实体 -1,落该快照小时桶;
  - `trend_first` 对本命标记子集同理(本命转移 = 旧对象 -1、新对象 +1)。
- 选民集口径与榜单完全一致(最新行 invalidated → 该选民全历史跳过)。
- **核心不变量(写成测试)**:任一实体全桶净增量之和 == 终榜票数。
- CP 的实体 key 沿用无序 multiset 口径(B-050 v1);白名单过滤在 diff 前应用(与榜单同一过滤点),保证不变量成立。
- 输出仍为稀疏 `[{hrs, cnt}]`,`cnt` 可为负——前端已按净增量语义消费(§一.3)。
- 问卷真实 trend:同批次序列 diff「回答了题 qX」的状态变化(答→撤答 = -1);`trend_first` 仍恒空。
- 高级搜索子集重算因纯函数复用**自动继承**真实 trend;`_compute_filtered` 的调用点随签名变化同步调整。

## 六、错误处理与边界

- 时间越界:分桶统一钳制到 `[0, total_hours-1]`(现行为)。
- 乱序/同秒提交:排序键 `(created_at, attempt)`,attempt 单调递增兜底同秒。
- legacy 存量多行选民(`legacy_mongo_id` 行):本就多行,diff 序列算法直接适用。
- `attempt IS NULL` 存量行:排序时按 `coalesce(attempt, 0)`(现行为),问卷批次兜底见 §四。
- 空历史/单行选民:退化为现近似值,无特判分支。

## 七、测试策略

- Step 1:`compute_paper_results` trend 单测(分桶/稀疏/钳制/多题);`queryQuestionnaireTrend` 端到端(真数据 + DSL 子集);更新现有恒空断言(`test_result_compat_*`)。
- Step 2:改写 `test_submit_attempt_and_duration` 的单行断言为多行 append 断言(attempt 递增、fill_duration 冻结不回归);净增量单测(加票/去票/本命转移/invalidated 选民/legacy NULL-attempt);**不变量测试**(净增量和==终榜票数,随机化改票序列);问卷批次去重测试(含 NULL-attempt 兜底);mock 生成器 attempt 适配测试。
- 全量回归(当前基线 573 tests)+ 部署后测试机实测:灌 mock → 手工改票 → 观察负增量桶。

## 八、文档与迁移记录

- CHANGELOG:两步各一条(Added/Changed,含兼容性说明:Step 2 需跑 0017)。
- BACKLOG:B-050-后补2 状态推进;admin 监控 attempt 列展示记新待办。
- `docs/migration/result-stats-audit-2026-08-14.md`:§A-3/§三 更新(legacy 近似值真相 + 本次两步结论)。
- 与 legacy 的刻意差异清单:① Step 1 时间戳口径(group 行时刻 vs 整卷时刻);② Step 2 真实净增量为**超越** legacy 的新能力(legacy 从未实现,前端契约天然支持)。
