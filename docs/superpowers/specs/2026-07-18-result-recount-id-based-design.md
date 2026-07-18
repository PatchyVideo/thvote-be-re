# 记票 / 结果统计模块重写 —— 纯 id 投票对象体系(B-050)

> 创建日期：2026-07-18
> 最后更新：2026-07-18（§八 对齐两份 VoileLabs 官方需求文档:票位数/白名单口径/CP 相同组合/问卷ID/完整指标;CP key 修正为 multiset)
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
  - **定(用户 2026-07-18;§八 权威文档已印证)**:**CP key = 无序 multiset** `tuple(sorted([A,B,C 去 None]))`——(A,B)==(B,A),同一 couple 一条榜。**注意用 multiset(有序列表)不用 set**:2 人 CP 允许"两个相同角色"(自 CP 如 灵梦×灵梦),set 会把 (A,A) 去重成 (A) → 必须保留重复;3 人 CP 不许重复角色(权威规则,见 §八)。`active`(主动方)**不进 key,但完整保留为该 CP 的属性**并出**主动率**(用户强调"active 在谁身上有些情况有区别",故 v1 就带;raw_cp 本就存 active)。`first`/`reason` 作属性;二/三人组按元素数天然区分。
  - **旧数据迁移注意**:旧排行层是有序 (a,b,c),迁历史数据时需把 a/b 排序归一,否则老 CP 票会被拆——迁移时单独处理(吃一堑长一智,新系统一开始就无序)。
- **(3-merge) merged_into 黑掉**(用户 2026-07-18):id 已是唯一单元、变体走 altnames,**name 级 merged_into 在 id 方案里停用**——合并/拆分 UI + `/vote-objects` 的 `merged_into IS NULL` 过滤停用(代码保留/注释,不硬删,留将来"两 id 指同角色"的数据清理余地)。
- **(9) 问卷 paper 统计**:**v1 不做**(先放下),属"全复刻"后补项。
- **地基决策至此全部锁定。** 剩余为实现层细节(SQL vs 内存倾向 SQL;结果 Redis 缓存 + finalize 归档的具体形状;白名单导入脚本形态),留实现计划展开。

## 七、风险 / 兼容

- 老票已引用现有哈希 id → 播种必须原样保留,不能重生成。
- ETL 消失:新方案不需要旧那个 id→name ETL(直接 id 聚合),但要求 candidate 覆盖所有被投 id,否则未知 id 票的展示要有兜底(见 §六.3)。
- 前端切换前后并存期:vote-objects(v12)与旧静态 ts(v11)可能同时在跑,需与 B-040 前端侧协调。

## 八、权威需求对齐(2026-07-18,两份 VoileLabs 官方需求文档)

**需求来源(已入 `docs/`)**:
- **输入侧**:`VoileLabs-人气投票项目-需求文档 (2).docx`(投票系统需求文档)——定义投票范围/票位/本命/CP 相同组合/问卷 ID。
- **输出侧**:`VoileLabs-人气投票项目-需求文档-投票结果页面.md/.docx`(结果页面 v2.0)——定义榜单指标/名次规则/trend/上届对比/搜索。

### 8.1 输入侧权威规则(计票输入口径)
- **票位数**:角色 **8** / 音乐 **12** / CP **4** / 提名 **5**;每部门本命 ≤1,本命加权 **2**。
- **有效票**:各部门 ≥1 对象、无空票位;投票理由可选。
- **白名单 = 官方策展名单**:角色截至 2024/12/22 按作品分类(首登为准)+ 入围标准;音乐按专辑;→ candidate 名单的权威口径。计票白名单用它,未知 id **计票时丢**。
- **CP 相同组合(权威去重)**:原文"包含相同角色的组合,即使角色顺序不同、主动方不同,也视为同样的组合"。→ **key = `tuple(sorted([A,B,C 去 None]))` 有序 multiset**;顺序/active 均不入 key;**2 人 CP 允许相同角色(自 CP),3 人 CP 禁重复**(故 multiset ≠ set);active 作属性出主动率;组合票数=1 不计入。
- **问卷 ID**:7 位 `[问卷类型1][子分类1][问题组2][题序1][选项2]`;**性别题 = `q11011`**(男/女选项,系统文档未写死性别 ID,取后端配置)。

### 8.2 输出侧完整指标(结果页面 = "全复刻"全集)
- 核心排名:**名次**(票数→本命数→**系统 ID** tie-break;并列占虚位) / 票数 / 本命数 / 本命率 / **本命加权=票数+本命数** / 票数占比(筛选时=同投率) / 本命占比。
- 性别:男/女 数+比例、占总体男女比例(join q11011)。
- 概览:对象数 / 有效票数 / 本命票数 / **平均 / 中位得票数**。
- CP 额外:A/B/C 主动率 + 无主动率(和=100%)。
- **投票演进 trend**:逐小时时间序列(总票/新增/本命/新增本命)。
- **上届对比**:第 11/⑩/⑨ 届并排(需历史 `final_ranking`)。
- **高级搜索"从投票中筛选"**:交叉引用 + 指令语言(`chars:["名"]`/`chars_first=`/`q<id>=<opt>`/AND/OR/括号)。

### 8.3 对设计的两点影响
- **trend 需保留全提交历史**:改票会去掉某对象、trend 要画升降,故存储**双用——最新算终榜(各自取最新)+ 全历史算 trend**。
- **搜索/展示是 name-facing,计票是 id-based**:搜索语言按人名、榜单展示人名/头像,但计票按 id → 全程需 candidate 的 **id↔name 双向映射**(白名单兼任)。

### 8.4 v1 范围(据"先做核心闭环")
- **v1**:角色/音乐/CP 核心排名(票数/本命/本命率/本命加权/占比)+ 名次规则(含系统 ID tie-break)+ CP 无序 multiset + 主动率 + 白名单丢未知 id + 离线批量(管理台按钮)。
- **后补**:性别票(依赖问卷 join)、trend(需全历史)、上届对比、高级搜索、问卷结果页、作品提名。

## 九、v1 实现落地(2026-07-18)

**决策已全部编码,6 个任务(读 raw_*、id 归票、CP multiset、名次口径、schema、本文档)均已完成并合并到 `docs/b050-result-design` 分支。**

### 9.1 最终文件清单

- `src/apps/result/whitelist.py`(新):id 白名单 / 展示注册表。`Whitelist` 类按 id 索引,提供 `ids`/`__contains__`/`get`/`name_of`/`system_id_of`;`load_whitelist("character"|"music")` 用 `lru_cache` 读快照 JSON,运行时不依赖前端仓库。
- `src/apps/result/data/whitelist_character.json`(244 条)、`src/apps/result/data/whitelist_music.json`(612 条):从前端 `character.ts`/`music.ts` 提取的冻结快照,每条含 `id/name/name_jp/work/kind/date/album/system_id`(`system_id` = 前端列表数组下标,即"系统ID tie-break"的依据)。**放在 `src/apps/result/data/` 下(不是仓库根 `data/`)**,随包分发、无需额外挂载路径。
- `scripts/extract_whitelist.mjs`(新):Node 脚本,解析前端 TS 源里的 `characterList`/`musicList` 数组字面量(用赋值号定位、找 `=` 后第一个 `[` 而非按类型注解误匹配),写出上述两份 JSON。
- `src/apps/result/compute_dao.py`:新增 `load_char_votes`/`load_music_votes`/`load_cp_votes`/`load_questionnaire_votes`,改读 `RawCharacterSubmit`/`RawMusicSubmit`/`RawCPSubmit`(路径 A 真表,不再读死表 `character`/`music`/`cp`)。`_latest_per_vote` 按 `(created_at desc, attempt desc)` 在 Python 侧去重取每个 `vote_id` 最新一条,并排除 `invalidated=true` 的行(接 B-049 处置动作)。`_normalize_items` 兼容旧 `list[str]` payload → `list[dict]`。
- `src/apps/result/compute.py`:`compute_ranking`(角色/音乐通用)与 `compute_cp_ranking` 改为按 id 归票,产出含 `id`/`favorite_percentage_of_all` 的榜单字典;`compute_gender_map`/`compute_global_stats`/`compute_completion_rates` 等辅助函数保持 pure function 风格不变。
- `src/apps/result/compute_service.py`:接线——`compute_all` 依次 `load_*_votes` → `load_whitelist("character"|"music")` → `compute_ranking`/`compute_cp_ranking` → 写 Redis,替换掉原先读死表 + 走 `CandidateMeta` 元数据的旧管线。
- `src/apps/result/schemas.py`:`RankingEntity` 加 `id: Optional[str] = None`、`favorite_percentage_of_all: float = 0.0`,与上述 compute 输出对齐。

### 9.2 白名单快照重新提取步骤(前端列表变更时)

前端 `Touhou-Vote` 的 `character.ts`/`music.ts` 每次增删角色/曲目/改 `system_id` 顺序后,需要重新生成快照并提交:

```bash
node scripts/extract_whitelist.mjs /data/sunyunbo/www/Touhou-Vote /data/sunyunbo/www/Thvote-be/thvote-be-re
```

参数依次为前端仓库根、后端仓库根;脚本会覆盖写 `src/apps/result/data/whitelist_character.json` 与 `whitelist_music.json`。**生成后必须 `git add` 提交这两个 JSON**——它们是运行时唯一的白名单数据源(无数据库表兜底),忘记提交等于线上白名单没更新。

### 9.3 已落地口径(与设计稿 §六/§八决策一一对应)

- **系统 ID** = 前端列表(`characterList`/`musicList`)里的位置序号(数组下标),写入快照的 `system_id` 字段;名次并列时按它 tie-break(见下)。
- **CP key** = 无序 multiset `tuple(sorted([id_a, id_b, id_c 去 None]))`——用有序 tuple(不是 set)保留重复元素,允许 2 人自 CP(如 A×A);`active`(主动方)不进 key,作为属性统计出 `active_a/active_b/active_c/active_none` 四个占比(和为 100%)。
- **名次** = 票数(desc)→ 本命数(desc)→ 系统 ID(asc)三级排序;**同票数即同名次(虚位)**——`display_rank` 只在票数变化时才递推,票数相同则继承上一条的 `display_rank`(不看本命数/系统ID 差异,那两项只决定排列顺序、不决定"是否算并列")。
- **本命加权** = `favorite_vote_count_weighted = 票数 + 本命数`。
- **白名单丢未知 id**:角色/音乐票里 `item.id` 不在对应白名单 → 该票位直接跳过(不计入任何统计);CP 票任一成员(`id_a`/`id_b`/`id_c`)不在角色白名单 → **整条 CP 丢弃**(不是丢单个成员)。
- **CP 组合票数 == 1 不计入**排名与 `global_stats`(`all_keys = [k for k in vote_count if vote_count[k] >= 2]`)。
- **计票取每 vote_id 最新、排除 invalidated**:`ComputeDAO._latest_per_vote` 对同一账号的多次提交只留最新一条(`created_at` 为主、`attempt` 兜底),`invalidated=true`(B-049 管理端作废标记)的行在取最新之前就被过滤,不参与去重比较。

### 9.4 v1 明确后补(未做)

以下项目在设计稿 §8.4 已列为后补,v1 未实现,GraphQL/REST 对应字段暂不产出或喂空值:

- **性别男女票**:`compute_ranking` 里 `male_vote_count`/`female_vote_count` 依赖 `compute_gender_map`,该函数需要 `raw_paper`(问卷)按性别题 `q11011` join 每个 `vote_id`;v1 的 `load_questionnaire_votes` 读的是旧 `Questionnaire` 死模型的空表,故性别恒为 `unknown`,统计结果恒 0。**需切到 `raw_paper` 才能出真实性别票**。
- **trend 演进**:`raw_*` 各表当前是"改票即覆盖"式存储(`_upsert` 只留最新一条,详见 B-045 CHANGELOG),没有保留历史提交行;而 trend 需要画"随时间推移的新增/累计"曲线,要求**逐次提交都留痕(append-only)**。现有 `compute_ranking`/`compute_cp_ranking` 里的 `trend`/`trend_first` 字段基于的是"取最新那一条的 `created_at`"分桶,**不是**真实的历史演进(改票会让旧的 hour bucket 计数消失),这是已知的近似值而非目标口径——真正复刻需要先把 `raw_*` 改造成 append-only 存储,记入 B-050 后补项而非本次交付范围。
- **上届对比**:需要历史 `final_ranking` 表(`FinalRanking` 模型,`compute_dao.load_historical`)有上一/上上届数据;测试库目前该表为空,且 `load_historical` 的 key 是 name(而非 id),与本次 id-based 归票路径尚未对齐,v1 未接线(`compute_ranking` 签名保留了 `historical: dict[str, dict]` 参数,但 `compute_service.py` 传入的是空 `{}`)。
- **问卷结果页**:`compute_paper_results` 仍是占位实现,读的是死表 `Questionnaire`;真实问卷统计需要 B-039 结构化问卷表(`raw_paper`/`paper_answer`)接入,本次不动。
- **高级搜索、candidate 表迁移 `object_id`**:均按设计稿 §四"非目标"/§8.4"后补"处理,v1 未涉及。


