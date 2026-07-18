# 记票 / 结果统计模块重写 —— 纯 id 投票对象体系(B-050)

> 创建日期：2026-07-18
> 最后更新：2026-07-18（grill R1-R3 完成,§六 地基决策全部锁定;含 id 稳定性/CP 两处 explore 结论)
> 状态：**决策已锁定,可进入实现计划(writing-plans)**。§三是方向,§六是全部决策 + 依据。剩余为实现层细节。
> 关联：B-050(计票重写)、B-040(投票对象迁后端)、`src/apps/result/`、`src/db_model/candidate.py`、`src/db_model/raw_submit.py`;旧系统研究见本会话两轮 explore 结论。

## 一、背景:candidate 为什么长这样(两段身世)

1. **2026-05-13(合作者 zfqxuz,`0c85658`)**:把旧 Rust `result-query` 计票模块搬到 Python。candidate 就是旧 MongoDB `all_chars`/`all_musics`(**按人名的候选/元数据集合**)的 PG 搬运版,`FinalRanking` 是旧 `final_ranking_char/music`(历史名次)的搬运版。见 `docs/superpowers/specs/2026-05-13-result-query-design.md` 的旧→新对照表。**candidate 天生 name-keyed、无稳定 id,是"1:1 忠实移植旧 name-based 架构"的结果,不是设计缺陷。**
2. **2026-06-08(B-040)**:复用同一套 candidate 表,加 `merged_into`(去重规范化)+ `/vote-objects/*` 端点,让它兼任"前端投票对象后端真相源"。

## 二、旧系统数据流 & 其脆弱性(要摆脱的)

- 提交:前端交**哈希 id**(`{id:'4068b1c2',reason,first}`)。
- 原始存储:`submits_v1.raw_*` **按 id 存**(追加,取最新)。
- **ETL(旧仓库里看不到的一跳):把 id 翻成人名**,合并成 `submits_v1_final.votes`(`chars:[{name}]`)。
- 计票:`result-query` **100% 按人名 GROUP BY**,元数据/历史名次/查询语言全按 name。
- 输出:`RankingEntry` **无 id**,name+元数据后端带出;前端结果页用 name 展示 + 按 name 反查静态表取头像。
- **脆弱点**:`votes.name / candidate.name / final_ranking.name / 前端 character.ts.name` 四处人名必须逐字一致,差一字就把同一角色拆成两条票、或丢元数据/头像/历史名次。

## 三、方向定调(已定)

**id 一贯到底,name 只做展示。**

- 选票存 id(现状已是)→ 计票 **GROUP BY object_id** → 榜单按 id 排 → **只在出榜那一刻** 用 id JOIN candidate 取 name/元数据。
- candidate 成 **`id ↔ name ↔ 元数据`** 唯一真相源:
  - **一次性播种**:导入脚本把现有前端 `character.ts`/`music.ts`(连同哈希 id)灌进 candidate(保留现有 id,不重生成)。
  - **之后 candidate 为源**:前端弃静态 ts,改从 `/api/v1/vote-objects/*` 拉(可运行时 fetch 或构建期 codegen 快照)。管理台编辑成为权威。
- **candidate 加稳定 `object_id` 列**(= 前端哈希 id,唯一)。当前 candidate 只有自增 PK,缺与选票对得上的 id —— 这是核心缺口。
- 计票层排除 `user.removed` 账号 + `raw_*.invalidated` 作废票(接 B-049 处置动作)。
- 好处:人名随便改、id 不动就不散;封号/作废真正影响排名;去掉旧 ETL 和四处对齐脆弱性。

## 四、目标 / 非目标

- **目标**:①计票改读真实 `raw_*`(不再读死表)②GROUP BY id ③candidate=id/name/元数据源 ④排除 removed/invalidated ⑤前端切 `/vote-objects`(B-040 前端侧)。
- **非目标**:不重做结果页 UI(只换数据源/主键);不改投票提交格式(已是 id);本稿不含反刷票新规则(另见 B-044/047)。

## 五、涉及改动(粗粒度,细节待 §六 定后展开)

- `db_model/candidate.py`:加 `object_id`(稳定 id)+ 迁移。
- 新播种脚本 `scripts/seed_candidates_from_frontend.py`(ts→candidate,保留 id)。
- `apps/result/compute_dao.py` / `compute_service.py` / `compute.py`:改读 `raw_*`、按 id 聚合、JOIN candidate、排除 removed/invalidated。
- `apps/vote_objects/*`:按 id 输出(前端按 id 拿名单/元数据)。
- `db_model/candidate.py` 死表清理(`character/music/cp/questionnaire` 四张,B-050 一并删)。
- 前端(另仓):切 `/vote-objects` + `/v12-be`(B-040 前端侧)。

## 六、待拍板决策(⚠️ grill 逐条落定,现未定)

1. **id 跨年稳定性**:前端 `character.ts` 的哈希 id 跨年稳定吗?同一角色 2024/25/26 同一 id?→ 决定 `object_id` 全局 vs per-year、历史名次按 id 还是回退 name。
2. **id 归属 / 分配权**:以后新增候选谁生成 id(后端?)?前端还自造 id 吗?播种后静态 ts 何时退役?
3. **未知/非法 id 的票**:id 不在 candidate 里的票算不算?candidate 变成**白名单**(只有名单内算票)还是沿用旧的"照样算、元数据未知"?防刷票视角要不要收紧?
4. **改票 / attempt 口径**:一人多次提交,记票取哪条(最新?)?和 `fill_duration_ms` 保首投的口径如何统一?
5. **统计维度**:旧系统统计 总票/本命票/男女票/reason 列表/按小时 trend。新记票全复刻?按 id 后 reason/性别票怎么挂?
6. **CP 记票**:CP 是 `(id_a,id_b,id_c)` **有序还是无序**?`active`(主动方)算什么?排名 key = 三元组?`(A,B)` 与 `(B,A)` 去重?CP 有没有候选表(还是纯动态 id 组)?
7. **计算触发 & 结果存储**:实时算 vs 离线批?结果存 Redis 缓存(旧 `cache_*`)还是 PG `final_ranking`?封号/作废后**重算时机**(手动触发?)。
8. **merged_into 计算含义**:变体 id 票并进主 id —— 读时 remap 还是预处理?admin 改 merged 后重算。
9. **问卷(paper)统计**:`paper_answer` 算不算 result 模块?按题/选项聚合口径?
10. **性能/实现**:几万人 × 多类别 —— 内存 HashMap 聚合(旧 Rust 式)还是 PG SQL `GROUP BY`?(raw_* 在 PG,倾向 SQL。)

### 已定(2026-07-18 grill R1)

- **(1) id 跨年稳定**:定为**祖传稳定 id**(跨年不变)。⚠️ 待 explore 确认前端是否有 id 生成逻辑;**若 id 是由人名哈希派生,则"改名即变 id",要重新评估**。
- **(3) 白名单制**:定 ✅(用户强调"最重要")。**只有 candidate 里的 id 才算票**;不在名单的 id 一律不计。→ 由此产生的新决策见下方 grill R2(执行点、覆盖保证、变体 id)。
- **(4) 改票口径**:定 = **按 `(vote_id, category)` 各自取最新**(各类别独立取该账号最新一条提交)。
- **(6) CP key**:待 explore(前端 + 旧 Rust 聚合逻辑)后定。
- **(5) 统计维度**:**全复刻为总体目标**,但 v1 先做核心闭环(票数 + 本命排名),男女票/reason/trend/历史名次等后补。
- **(7) 计算触发 & 存储**:定 = **离线批量算**,管理台一个"**开启一轮计算**"按钮触发(复用现有 `POST /admin/compute-results`;封号/作废后重新点即可)。结果存储沿用现有 Redis 缓存 + `finalize-ranking` 归档路径(待细化)。
- 仍开:**(9) 问卷统计口径**、**(10) SQL vs 内存聚合**(倾向 SQL,待定)。

### 已定(2026-07-18 grill R2 —— 白名单机制)

- **(7) 白名单执行点**:定 = **计票时丢弃**(不在提交时拒)。理由:票照样入库,漏了合法角色只需**改 candidate + 重跑一轮计算**票就回来,不永久丢。→ 需求:计票时应**记录/报告被丢弃的未知 id**,别静默。
- **(8) 覆盖保证**:定 = **a 方案**——开投前跑一道校验闸,确认"前端每个合法 id 都在白名单里",不全覆盖不许开投。
- **(9) id 模型澄清(重要,简化设计)**:**id = 角色的唯一最小单元,一个角色一个 id;名字可有变体,但变体归并到同一个 id(= 前端 `Character.altnames`)。** 即"归并"发生在 **name→id** 层、且**已在前端数据里做好**。
  - **推论:name 级的 `merged_into`(B-040)在 id 方案里不再需要**——不存在"两个 id 是同一角色要合并"(id 已保证角色唯一)。变体名只是同一 id 上的 altnames。→ 见下方"待确认后果"。
- **(2)/(10-white) id 归属 & 白名单来源**:定 = **白名单 id 暂时用前端文件**(从 `character.ts`/`music.ts` 取 id 全集,连同 name/altnames/元数据一起,作为白名单 + id→name/元数据来源);**之后再迁到 candidate 表**为权威源。新增角色的 id 归属随迁移时定。

### 待确认后果(grill R2 引出)

- **merged_into 报废**:既然 id 已是唯一单元、变体走 altnames,那 name 级 `merged_into` + 管理台"合并/拆分"UI + `/vote-objects` 的 `merged_into IS NULL` 过滤,在 id 方案里**都可以退役**。**需你拍板:id 方案里彻底不要 merged_into?**(这会让合作者 B-040 的合并那部分成为历史。)
- **candidate 需加 `altnames`**(承接前端变体名),同时加 `object_id`(唯一 id)。
- **v1 白名单/元数据直接读"前端文件的导入副本"**(因 candidate 迁移在后):需一个"把前端 `character.ts` 的 {id,name,altnames,meta} 导进后端"的数据来源(脚本/数据文件/临时表),兼作白名单 + id→name。

### 已定/更新(2026-07-18 grill R3 —— investigation 结论 + 收尾)

- **(1) id 稳定性(explore 确认)**:id 是一个**已丢失的生成脚本**产出的 8-hex 哈希,**冻结自 2023-07-01,至今只增不改**(git:`5ec80a4` 整数→哈希;`ffeda29` 因碰撞改算法、整体重刷过一次;之后冻结)。**非人名派生**(md5/sha 各编码全不匹配),`altnames` 增删不动 id → **改名不动 id**,坐实 id-canonical 模型。
  - **铁律**:后端把这批 id 收成 `object_id` 后**永久冻结、绝不重跑生成器**;新角色由**后端分配**新稳定 id(前端不再自造)。这批 id = 不可再生的祖传常量。
- **(6) CP key(explore 确认:旧系统自相矛盾,无干净旧行为可抄)**:前端交 `{idA,idB,idC?,active(主动方id),first,reason}` 不排序;旧后端排行层 `CPItem` key = **有序 (a,b,c)**(→(A,B)≠(B,A)),提交层有个**无序相等但没接线**,写 `votes` 的 ETL 有没有排序**查不到**=潜伏 bug。
  - **定(用户 2026-07-18)**:**CP key = 无序** `sorted({A,B,C 去 None})`——(A,B)==(B,A),同一 couple 一条榜。`active`(主动方)**不进 key,但完整保留为该 CP 的属性**并出**主动率**(用户强调"active 在谁身上有些情况有区别",故 v1 就带;raw_cp 本就存 active)。`first`/`reason` 作属性;二/三人组按元素数天然区分。
  - **旧数据迁移注意**:旧排行层是有序 (a,b,c),迁历史数据时需把 a/b 排序归一,否则老 CP 票会被拆——迁移时单独处理(吃一堑长一智,新系统一开始就无序)。
- **(3-merge) merged_into 黑掉**(用户 2026-07-18):id 已是唯一单元、变体走 altnames,**name 级 merged_into 在 id 方案里停用**——合并/拆分 UI + `/vote-objects` 的 `merged_into IS NULL` 过滤停用(代码保留/注释,不硬删,留将来"两 id 指同角色"的数据清理余地)。
- **(9) 问卷 paper 统计**:**v1 不做**(先放下),属"全复刻"后补项。
- **地基决策至此全部锁定。** 剩余为实现层细节(SQL vs 内存倾向 SQL;结果 Redis 缓存 + finalize 归档的具体形状;白名单导入脚本形态),留实现计划展开。

## 七、风险 / 兼容

- 老票已引用现有哈希 id → 播种必须原样保留,不能重生成。
- ETL 消失:新方案不需要旧那个 id→name ETL(直接 id 聚合),但要求 candidate 覆盖所有被投 id,否则未知 id 票的展示要有兜底(见 §六.3)。
- 前端切换前后并存期:vote-objects(v12)与旧静态 ts(v11)可能同时在跑,需与 B-040 前端侧协调。
