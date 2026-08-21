# 高级搜索/筛选 DSL 设计稿(B-050-后补5,兼 B-053 前置)

> 日期:2026-08-14
> 状态:设计定稿,待实施
> 需求来源:`docs/VoileLabs-人气投票项目-需求文档-投票结果页面.md` §846-923(搜索与筛选组件)、§938(约束贯穿演进/问卷统计)
> 前置勘察:[result-stats-audit-2026-08-14](../../migration/result-stats-audit-2026-08-14.md)(三方审计,P0 定级)、[result-recount-id-based-design](./2026-07-18-result-recount-id-based-design.md) §8.2(子集重算原语的关键发现)
> 对应 legacy:`thvote-be/result-query` 的 pest DSL(贯穿全部查询接口)

---

## 一、背景与目标

前端 `AdvancedSearch` 组件(图形 + 指令双模式)已在生成 DSL `query` 参数并传给角色/音乐/组合/问卷各结果页;Python 后端契约层(`src/api/graphql/resolvers/result_compat.py`)目前对非空 `query` 一律抛 `ADVANCED_SEARCH_NOT_IMPLEMENTED`。本设计落地服务端 DSL 解析 + 按投票子集重算,点亮高级搜索全功能。

**目标**:
1. 完整实现需求 §846-923 的指令语法(5 种原子条件 + AND/OR/括号);
2. 语义为"**换一个投票子集重算榜**"——先圈出满足约束的 `vote_id` 集合,再对子集重新聚合,而非对现成榜单做后置过滤(后者的百分比/名次基数是错的);
3. 约束贯穿契约层所有带 `query` 参数的 10 个查询(排名×3、单条×3、全局统计、完成率、问卷、问卷趋势),`RankingEntry` 内嵌的 trend/reasons 随重算自然变为子集口径(满足 §938);
4. 为 B-053(任意问卷题 × 投票结果交叉分析)沉淀可复用的子集圈选原语。

**非目标**(刻意不做,见 §十):covote 卡方/互信息、往届对比接通、问卷时间维度、`num_doujin`。

## 二、方案选型与性能定位(决策记录)

设计前专门评估过"是否真的需要 DSL / 解析器会不会成为性能风险"。结论:

- **解析器不是成本中心**。本语法仅 5 种原子 + 布尔组合,lark 文法约 40 行,解析一条查询是微秒级纯 CPU 操作,且原串长度受限(≤1KB)。
- **真正的成本是子集重算**,而它与"约束用什么形式表达"无关——换成 JSON 契约、砍指令模式只留图形模式,子集重算一分不省。
- 数据规模(本届预期几万票以内)+ 访问模式(过程开放、**定时更新非实时**)下,单次重算为几百毫秒量级,配合版本化缓存后风险很低。

据此比较过三个方案:

| 方案 | 表达层 | 结论 |
|---|---|---|
| **A(采纳)** | 服务端 lark 解析 DSL 字符串 | 前端零改动、legacy 契约逐字兼容、需求全覆盖;解析器成本趋近零 |
| B(否) | 砍指令模式,契约改结构化 JSON | 省 40 行文法,却砍需求硬核心(§846 明确规定指令模式)+ 前端重写 + 契约断裂;省小头花大头 |
| C(否) | 前端解析传 AST JSON | 校验任意嵌套 AST ≈ 解析本身,复杂度只是搬家;契约变动无收益 |

## 三、总体架构与数据流

新增子包 `src/apps/result/advanced_search/`,三个模块,职责单一:

```
dsl.py       lark 文法 + 解析:query 字符串 → AST(dataclass)→ 归一化 → 规范串/指纹
subset.py    AST 求值:从已载入的票构建 per-vote 事实索引 → 满足约束的 vote_id 集合
service.py   AdvancedSearchService:缓存查找 → miss 时载票、圈子集、过滤后复用
             compute 纯函数一次性算出整包结果 → 写缓存
```

**请求路径**(query 非空且非 `"NONE"` 时):

```
GraphQL resolver(query 参数)
  → dsl.parse(query)                语法错 → ADVANCED_SEARCH_SYNTAX_ERROR
  → 归一化 → sha1 缓存指纹
  → Redis 查 result:{year}:adv:{快照版本}:{指纹}:{section}
      命中 → 直接返回(与现有预计算榜单同速)
      miss → ComputeDAO 载票(与 compute_all 同一入口)
           → 白名单解析名字 → subset.evaluate(ast) → vote_id 子集
           → 过滤四类票列表 → 复用现有 compute 纯函数整包重算
           → 按现有 key 布局写缓存(TTL 24h)→ 返回
  → 契约层 _ranking_entry_from_dict 等转换器原样复用(输出 shape 不变)
```

**query 为空/`"NONE"` 走现有路径,一行不改**——预计算榜单照旧,无回归风险。

**依赖的现状事实**(实现时依赖,变更需同步本稿):
- compute 管道是纯内存 Python:`ComputeDAO.load_*_votes()` 载入全部票 → `compute_ranking` 等纯函数计算(`src/apps/result/compute.py`),子集重算只需过滤输入列表,不改任何计算逻辑;
- 票的内存形态:角色/音乐/CP 为 `(vote_id, created_at, [{id, first, reason}])`,问卷为 `(vote_id, [{id: 题code, answer: [选项code], answer_str}])`;
- 契约层带 `query` 参数的 10 个查询字段经 8 处 `_reject_query_dsl(query)` 调用点收口(排名/单条的 char/music 各共用一个 helper)——接入点即替换该函数;
- 白名单 `load_whitelist_db()` 提供 id↔name/name_jp 映射(`src/apps/result/whitelist.py`)。

**筛选生效范围**:契约中带 `query` 参数的全部 10 个查询(`queryQuestionnaireTrend` 在筛选下仍返回恒空 `Trends`——无时间维度的既有退化行为,与筛选无关,见 §十)。`queryCharacterTrend`/`queryMusicTrend`(按 names 批量)契约本身无 `query` 参数,不改动——筛选下的演进曲线由详情页走单条/排名查询的内嵌 `trend` 字段获得。"同投率"= 筛选状态下 `vote_percentage` 列的自然语义(子集内占比),前端只需改列名,后端无需任何特殊处理。

## 四、DSL 文法与归一化

### 4.1 文法(lark,EBNF 示意)

```
?expr:     and_expr ("OR" and_expr)*           // OR 优先级最低
?and_expr: atom ("AND" atom)*                  // AND 结合更紧
?atom:     "(" expr ")"
         | "q" INT "=" INT                     // q11011 = 1101101 → 题code=选项code
         | "chars"  ":" "[" STR ("," STR)* "]" // 组内 OR
         | "chars_first"  "=" STR
         | "musics" ":" "[" STR ("," STR)* "]" // 组内 OR
         | "musics_first" "=" STR
STR: 双引号字符串;全文法空白不敏感
```

覆盖需求文档全部示例,含括号嵌套例
`(q11011 = 1101101 AND chars: ["东风谷早苗"]) OR musics_first="信仰是为了虚幻之人"`。

解析产物为 7 种 dataclass 节点:`QCond(qcode, ocode)` / `CharAny(names)` / `CharFirst(name)` / `MusicAny(names)` / `MusicFirst(name)` / `And(children)` / `Or(children)`。AST 与 lark 树解耦,类型标注齐全;B-053 直接消费 AST,不触碰解析细节。

### 4.2 归一化(决定缓存命中率)

- `chars:[...]`/`musics:[...]` 组内名字排序 + 去重;
- `And`/`Or` 按结合律拍平(`And(And(a,b),c)` → `And(a,b,c)`),操作数按规范串排序;
- 归一化后序列化为规范串 → sha1 → 缓存指纹。`A AND B` 与 `B AND A` 命中同一份缓存。

### 4.3 限制(护栏,解析后在 AST 上检查)

| 限制 | 阈值 | 超限行为 |
|---|---|---|
| query 原串长度 | ≤ 1024 字符 | 直接拒,不进入解析器 |
| 原子条件数 | ≤ 20 | `ADVANCED_SEARCH_TOO_COMPLEX`(指明超的是哪项) |
| 嵌套深度 | ≤ 5 | 同上 |

## 五、语义规范

1. **原子判定**(对单个 `vote_id`):
   - `chars:["a","b"]`:角色部门投过 a **或** b(组内 OR);`musics:` 同理;
   - `chars_first="a"`:角色部门本命位是 a;`musics_first=` 同理;
   - `q题=选项`:问卷该题选中了该选项(多选题按"包含"判定);
   - 该票没有对应部门的提交(如只投角色未投音乐)→ 该部门原子判 **False**。
2. **组合**:`AND` 取交、`OR` 取并、括号调整优先级;无括号时 AND 结合紧于 OR。需求钉死的语义:`chars:["早苗"] AND chars:["灵梦"]` = 两个都投了(两个原子各自独立判定后取交),区别于 `chars:["早苗","灵梦"]` = 投了任一。
3. **名字解析**(已拍板的两个决策):
   - 求值前把 AST 中所有名字经白名单批量解析为 id;**`name` 与 `name_jp` 均做精确匹配**,命中任一即解析成功;
   - **白名单中不存在的名字 → 抛 `ADVANCED_SEARCH_UNKNOWN_NAME`**,消息列出全部未匹配的名字(指令模式手打错字可立刻自查;图形模式从下拉框选择,不会触发)。注意区分:"在白名单里但没人投"不是未知,正常参与运算(匹配不到任何票);
   - 解析完成后,原子判定全部是 **id 集合运算**——与 B-050"纯 id 记票"路线一致,不引入按名归票回退。
4. **`q题=选项` 的 code 依赖**:题/选项按语义 code 匹配(与 `load_questionnaire_votes` 的输出一致)。线上问卷 code 未回填期间(B-054),问卷原子匹配不到任何票——属数据阻塞,非本设计缺陷,B-054 落地即自动生效。
5. **空子集是合法结果**:排名空列表、全局统计全 0,正常返回,不报错。

## 六、子集求值与过滤重算

### 6.1 事实索引(O(票数) 一遍扫描构建)

```
char_facts[vote_id]  = (投过的角色 id 集合, 本命 id | None)
music_facts[vote_id] = (投过的曲目 id 集合, 本命 id | None)
q_facts[vote_id]     = {题code: 选中的选项 code 集合}
全集 = 四类票列表 vote_id 的并集
```

数据源与 `compute_all` 完全同源(`ComputeDAO.load_*_votes()`,已含"每 vote_id 取最新、排除 invalidated"口径),不存在两套读取路径的漂移。

### 6.2 求值

对全集中每个 `vote_id` 递归求 AST 真值。复杂度 O(票数 × 原子数) ≤ 5 万 × 20 = 100 万次集合成员判断,纯内存,几十毫秒量级。

### 6.3 过滤重算

四类票列表按子集过滤后,**原样调用**现有纯函数:`compute_ranking` / `compute_cp_ranking` / `compute_global_stats` / `compute_completion_rates` / `compute_paper_results`。计算逻辑零改动。参数细节:

- `segment_map`(性别分段)传全量 map:计算只按子集内 vote_id 查询,天然正确;
- `historical` 照旧传 `{}`:筛选子集没有"上届对应子集",`*_last_*` 字段维持 -1 哨兵,语义诚实;B-050-后补3 落地后此处也**不**接历史(全量路径才接);
- `vote_start`/`total_hours` 与 `compute_all` 同源(settings),子集 trend 分桶口径与全量一致;
- **covote 不进重算集**(需求已确认无同投关联页,见 audit §六修正1);`num_doujin` 维持现状桩。

## 七、缓存与护栏

### 7.1 Key 布局(镜像现有布局,多一段前缀)

```
现有:   result:{year}:chars:ranking
筛选后: result:{year}:adv:{快照版本}:{指纹}:chars:ranking     TTL 24h
       (chars|musics|cps 的 ranking/global、global_stats、
        completion_rates、paper:{qid} 全套 section 同前缀)
```

读取侧 `ResultDAO` 的现有方法增加一个可选 key 前缀参数即可复用,不写第二套读取代码。

### 7.2 快照版本

`ComputeService.compute_all` 收尾时写 `result:{year}:snapshot_version`(unix 时间戳)。高级搜索缓存 key 携带该版本:定时重算后版本翻转,旧指纹缓存自然失效,TTL 24h 兜底回收。key 不存在时(老部署未跑过新 compute)按 `"0"` 处理。

### 7.3 整包一次算

miss 时一次性算好全部 section 写入(票已在内存,多算几个 section 是顺手的纯 CPU),避免同一约束下用户切页时每个 section 各自 miss 重复载票。

### 7.4 防击穿(单飞)

per `(year, 指纹)` 的 Redis 锁(SET NX,TTL 30s,token 化 compare-and-delete):拿到锁者计算;拿不到者**跟随锁存活轮询**(200ms 间隔,上限 60s;锁消失即提前接手,B-060 修订——原固定 5s 预算在真机实测重算 ~8s 面前会让等锁者集体转入重复计算),超时兜底自己算(重复计算幂等无害)。

### 7.5 护栏总表

1. 表达层:原串 ≤1KB、原子 ≤20、深度 ≤5;
2. 缓存:版本翻转 + TTL 双重失效;归一化提升命中率;
3. 单飞锁防击穿;
4. 求值与重算全内存,DB 压力仅"载票"的几条现有全表 SELECT;
5. **全局 miss 重算限频**(终审修复波已实现,见 `service.py::_check_miss_budget`):GraphQL 入口本身无限流,且 `q<code>=<opt>` 原子的 code 不经白名单校验(B-054 前刻意保留)、指纹空间无界,按指纹隔离的单飞锁对轮换指纹攻击无效——在 `ensure_filtered_results` 进入 miss 计算分支之后、拿单飞锁之前,用 Redis `INCR`+`EXPIRE` 固定窗口对 `adv_miss_budget:{year}` 计数,超过预算抛 `ADVANCED_SEARCH_BUSY`。**B-060(2026-08-22)升级为双层**:per-IP `ADV_MISS_LIMIT_PER_IP_PER_MINUTE`(=10,client IP 经 `ClientIPMiddleware` 以 ContextVar 注入,复用 B-044 可信代理解析)+ 全局 `ADV_MISS_LIMIT_PER_MINUTE`(=30)兜底;且扣费点后置——**只有真正执行重算的调用者扣预算**,缓存命中与等锁后从缓存拿到结果的路径不扣。

## 八、错误处理

| 情形 | 错误 kind | 行为 |
|---|---|---|
| 语法错误 | `ADVANCED_SEARCH_SYNTAX_ERROR` | 人话消息带行列号(lark 原生提供) |
| 超限 | `ADVANCED_SEARCH_TOO_COMPLEX` | 指明超的是哪个限制 |
| 未知名字 | `ADVANCED_SEARCH_UNKNOWN_NAME` | 列出全部未匹配的名字 |
| 空子集 | 不是错误 | 空榜/全 0 正常返回 |
| 该年未跑 compute | `RESULT_NOT_COMPUTED`(现有) | **筛选路径不可达**:`ensure_filtered_results` 不依赖预计算快照存在,会现场从 DB 载票直接算出结果;此错误仅在无筛选(query 为空)路径可能出现。与 CHANGELOG 2026-08-14 条目"兼容性"一致 |
| 单条查询序号不在筛选后榜内 | `ENTITY_NOT_FOUND`(现有) | 与现行为一致 |
| miss 重算全局限频超限 | `ADVANCED_SEARCH_BUSY` | 缓存命中路径不触发;见 §7.5 第 5 条 |

全部经现有 `map_app_errors` 出口,错误 shape 与 `ADVANCED_SEARCH_NOT_IMPLEMENTED` 相同——前端现有错误通道原样保留,仅 kind 更细。`_reject_query_dsl` 及其 kind 在本设计落地时移除。

## 九、测试计划

1. **解析器单测**:5 种原子、AND/OR 优先级、括号嵌套;需求文档全部原例逐条断言;归一化等价(`A AND B` ≡ `B AND A` 同指纹;组内乱序同指纹);三类错误(语法/超限/长度)。
2. **求值单测**:手造小票集覆盖:`chars:["a"] AND chars:["b"]`(都投)vs `chars:["a","b"]`(投任一)、跨部门 AND、缺部门提交判 False、`*_first`、多选题包含判定、未知名字报错。
3. **过滤重算集成测**:小数据集断言**百分比/名次基数按子集口径**(子集重算 vs 后置过滤的分水岭,必须锁住);空子集返回形状。
4. **契约测**:GraphQL 带 query → 筛选结果;空 query/`"NONE"` → 与现路径结果一致;三类错误 shape;单条查询 + 筛选。
5. **缓存测**:miss→写入→hit;版本翻转后旧缓存不命中;单飞锁并发路径。
6. **性能冒烟**:5 万合成票,miss 全路径 < 2s(含载票、求值、整包重算)。

## 十、非目标与刻意保留

| 项 | 决定 | 依据 |
|---|---|---|
| covote 卡方(cs)/互信息(mi) | 不做 | 需求无同投关联页(audit §六修正1);"同投率"是筛选下占比列改名,已含于本设计 |
| 往届对比接通(`historical`) | 不做,另行(B-050-后补3 + B-057③) | 独立数据依赖(导入 final_ranking);筛选路径永远传 `{}` |
| 问卷时间维度(问卷 trend) | 不做,另行(B-050-后补2) | 需 raw_* append-only 存储改造 |
| `num_doujin` | 维持桩 | 同人本统计未做,与前端现状匹配 |
| 图形模式↔指令模式转换 | 前端职责 | 后端只认最终 query 字符串 |
| DSL 自动补全 | 不做 | 需求自标 TODO,前端功能 |

## 十一、与 BACKLOG 的映射及后续

- 本设计 = **B-050-后补5**(P0)的实现方案;落地后该项关闭;
- **B-053**(任意问卷题 × 投票结果交叉分析)复用本设计的 `subset.py` 原语("筛选"与"切分"是同一原语:用约束圈 `vote_id` 集合)+ AST 数据类;届时只需在 service 层增加"按题切分多子集各算一份"的编排;
- 实施完成后需同步:`docs/CHANGELOG.md`、BACKLOG 表 B-050-后补5 行、audit 文档 §四优先级状态;前端侧(Touhou-Vote 仓)跟进"同投率"列名切换(B-055 归口)。
- **已实施**(分支 `feat/advanced-search-dsl`,Task 1-6,2026-08-14):文法解析/归一化/护栏(Task 1-2)、子集圈选(Task 3)、整包重算服务+缓存失效(Task 4)、契约层接通(Task 5)、性能冒烟+回归+文档收尾(Task 6)全部完成。

## 十二、风险与回滚

- **风险 1:问卷原子在 B-054 前恒空匹配**——数据阻塞非代码缺陷;上线说明中写明,避免误判为 bug。
- **风险 2:名字歧义**(不同 voteable 的 name 与 name_jp 撞名)——精确匹配命中多个 id 时,按"全部命中的 id 取并集"处理(投任一即满足),与组内 OR 语义一致;不报错。
- **风险 3:缓存放大**(恶意枚举不同约束刷 miss)——护栏 §7.5;极端情况下可临时把 `_reject_query_dsl` 加回(单函数开关,回滚成本一行)。
- **回滚策略**:本设计全部代码位于新子包 + 契约层单函数替换;回滚 = 恢复 `_reject_query_dsl` 调用,预计算路径不受任何影响。
