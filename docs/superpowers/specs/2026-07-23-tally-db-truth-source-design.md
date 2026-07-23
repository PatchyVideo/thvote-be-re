# 计票真相源迁 DB（candidateId 双键）+ voteable 导入/管理通道 — 设计稿

> 日期：2026-07-23
> 状态：设计定稿，待实施（Phase 1 = 计票核心 + 导入通道；Phase 2 = admin-ui 管理页）
> 对应 BACKLOG：**B-050-后补6 ⚡**（主体）、**B-057 ①②**（顺带收口）
> 前置事实盘点见 `docs/CHANGELOG.md` 2026-07-23 条目

## 一、背景与问题

voteable/work 重构（zfq_dev，2026-07-23 合入 main）之后，可投票对象的真相源已经
迁入数据库（`voteable_character`/`voteable_music`/`work` + 年度关联表
`candidate_*`），投票契约方向定为**前端只传 `candidateId`(int)**。但计票系统
（B-050 v1）仍按**前端 8-hex id** 归票，数据源是前端列表的冻结快照
`src/apps/result/data/whitelist_{character,music}.json`。

三个具体矛盾：

1. **对撞（高危）**：前端 `zfq_dev_fe` 的投票页 roster 已改从后端 API 构造，
   `Character.id` 即 candidateId——一旦前端字段漂移修复（见下），提交的票就是
   candidateId 格式，现行计票会把它们全部当未知 id 丢弃，排名归零。
   （当前测试机前端因字段漂移 `item.id`≠`candidateId`，提交 id 全是
   `"undefined"`——前端修复与本设计的计票适配必须协调落地，顺序见 §八。）
2. **桥数据缺失**：`voteable_*.old_id` 列存在但全仓无写入方，244+612 行全 NULL。
   8-hex ↔ candidateId 的映射数据只存在于快照 JSON。
3. **真相源分裂**：快照 JSON 是运行时依赖，而未来角色/作品数据要「直接导入 /
   admin 手改 DB 行」（含 THBWiki 抽取工具产出）——JSON 快照模式与之相悖。

### 已核实的事实（2026-07-23 实测）

- 快照 JSON 每条含 `id`(8-hex)/`name`/`name_jp`/`work[]`/`kind[]`/`date`/`album`/
  **`system_id`（显式字段）**；角色 244 条、音乐 612 条，**两侧连裸 name 都零重名**
  → 按名匹配 DB 行是确定性操作。
- `candidate_*` 精简后仅 `(id, vote_year, voteable_id)`，无任何排序列。
- CI 对**空库**跑 `alembic upgrade head`（deploy-test.yml:132）→ 数据回填不能进
  迁移（空库上「回填不齐即中止」必炸）。
- `voteable.work_id` 是单值 FK；vote-objects API 的 `workIds` 数组只是
  `[work_id]` 包装。旧快照的多作品列表（如博丽灵梦 = 灵异传+红魔乡）在 DB 中
  已塌缩为单作品。
- THBWiki 抽取工具（2026-07-20 设计稿）第一轮纯抽取、不落库，落库契约未定——
  由本设计定义的导入通道承接。

## 二、目标与非目标

**目标**

1. 计票真相源迁 DB：白名单从 DB 加载，快照 JSON 退出运行时。
2. 双格式过渡：8-hex 旧票与 candidateId 新票**都能归到同一实体**，计票不断档。
3. 名次口径不变：三级 tie-break（票数→本命数→系统ID）中的系统ID继续等于
   官方列表序号（快照 `system_id`），落为 `candidate_*.sort_order`（年度属性）。
4. 数据进出走**统一导入通道**（admin 端点，dry-run 先行，upsert 语义）——快照
   回填、THBWiki 未来产出、CSV 手工维护共用同一入口；schema 迁移史零数据。
5. 管理员可视可改：admin-ui 提供 voteable 列表/编辑（含 `old_id`、`sort_order`、
   work 关联），作为一切数据问题的手工兜底。

**非目标**

- 不改投票提交链路（`src/apps/submit`）——payload 形状不变，id 语义由前端切换。
- 不做多作品关联表（`voteable.work_id` 保持单值；多作品展示差异见 §九）。
- 不做 THBWiki 抽取工具本体（另一设计稿）；本设计只提供其落库通道。
- 不动 CP 白名单语义（CP 成员仍必须全部命中角色白名单，规则不变）。

## 三、数据模型变更（迁移 `0016`，纯 schema）

```
candidate_character  + sort_order INTEGER NULL
candidate_music      + sort_order INTEGER NULL
```

- **零数据操作**。幂等写法与 0011~0015 同款（Postgres-only
  `ADD COLUMN IF NOT EXISTS`；sqlite 测试库走 `create_all` 不受影响）。
- `down_revision = "0015"`（链：`0014 → 12a5f2e6dbed → 0015 → 0016`）。
- 语义：该 voteable 在**该届**官方候选列表中的序号（0 起）。年度属性所以放
  candidate 而非 voteable——下一届列表顺序变化时互不干扰。
- `voteable_*.old_id` 列已存在，无 schema 变更；其数据由导入通道写入（§五）。

模型侧同步：`CandidateCharacter`/`CandidateMusic` 加 `sort_order` 列声明。

## 四、白名单 DB 化（`src/apps/result/whitelist.py` 重写）

### 4.1 加载

`load_whitelist(category)`（同步读 JSON + `lru_cache`）替换为：

```python
async def load_whitelist_from_db(
    session: AsyncSession, category: Literal["character", "music"], vote_year: int
) -> Whitelist
```

查询：`voteable_* JOIN candidate_*(vote_year) LEFT JOIN work`。每行产出一个
`WhitelistEntry`。**不做进程级缓存**（compute 是管理员触发的离线批处理，每次
现读 DB，admin 改完数据重跑 compute 即生效；与 B-017 的 lru_cache 配置坑划清
界限）。

### 4.2 Entry 与双键索引

```python
@dataclass(frozen=True)
class WhitelistEntry:
    candidate_id: int          # canonical key（年度 candidate 行 id）
    voteable_id: int
    old_id: str | None         # 8-hex 旧 id（可能未回填）
    name: str
    name_jp: str
    origin: str                # work.name 或 ""（音乐同 album）
    type: str                  # voteable.type 经 _KIND_MAPPING 映射展示值
    first_appearance: str | None
    album: str | None          # 音乐 = work.name；角色 = None
    system_id: int             # candidate.sort_order；NULL → 兜底见 4.4
```

`Whitelist` 内部索引：

- `_by_token: dict[str, WhitelistEntry]` —— 同一 entry 挂两个 token：
  `str(candidate_id)`（如 `"22"`）和 `old_id`（如 `"4068b1c2"`，存在时）。
  构造时校验 token 无碰撞（8-hex 与十进制数字串天然不同形；碰撞即 raise）。
- 对外 API 保持并扩展：`__contains__(token)` / `get(token)` /
  `name_of(token)` / `system_id_of(token)` / `canonical(token) -> str | None`
  （返回 `str(candidate_id)`，未命中返回 None）。

### 4.3 canonical key 统一（compute 侧）

compute 各入口（角色票、音乐票、CP 成员、本命、covote）在**读票时**先
`wl.canonical(raw_token)`：

- 命中 → 用 `str(candidate_id)` 作为后续一切聚合的 key。
  **同一角色的 8-hex 旧票与 candidateId 新票聚合到同一个 key；CP 的无序
  multiset key 由 canonical 后的成员构成，不会因格式混用而分裂。**
- 未命中 → 该 item 丢弃（沿用 v1 白名单语义），**按 token 形态分类计数**
  （`legacy_8hex_unmatched` / `candidate_id_unknown` / `malformed`，含
  `"undefined"` 字面量单列），compute 结束输出一条汇总日志——不静默。

`compute.py`/`compute_service.py` 的改动预期极小：key 类型仍是 `str`，只在
入口加一次 canonical 翻译；元数据读取途径不变（经 entry）。

### 4.4 兜底规则（数据不全时行为明确）

| 情形 | 行为 |
|---|---|
| DB 白名单加载 0 行 | **中止 compute**，报 `WHITELIST_EMPTY`（禁止静默零榜） |
| `old_id` 未回填 | 8-hex 旧票按未命中丢弃 + 计数日志（跑一次快照导入即消除） |
| `sort_order` NULL | `system_id = SORT_ORDER_TAIL_BASE + candidate_id`（排在有值条目之后、彼此按 candidateId 稳定顺延） |
| 快照 JSON | 退役为导入 fixture 与测试样本，运行时零依赖 |

## 五、统一导入通道（admin 端点）

### 5.1 端点

`POST /api/v1/admin/voteables/import`（`require_admin` 闸门内，沿用 B-036
candidates/import 的请求形态与 dry-run 模式）：

```jsonc
{
  "category": "character" | "music",
  "vote_year": 12,               // 可空：只 upsert voteable、不建 candidate 行
  "format": "json" | "csv",
  "content": "...",              // 行字段见 5.2
  "dry_run": true                // 默认 true
}
```

响应（dry-run 与执行后同构）：

```jsonc
{
  "create": [...],               // 将新建的 voteable（含解析后字段）
  "update": [...],               // 将更新的（含 diff 字段列表）
  "work_created": [...],         // 将自动新建的 work（name+type）
  "candidate_upserts": n,        // 将建/更新的年度 candidate 行数
  "conflicts": [...],            // 无法安全处理的行 + 原因（见 5.3）
  "totals": {"rows": n, "matched_by_id": n, "matched_by_old_id": n,
              "matched_by_name": n, "created": n}
}
```

### 5.2 行字段与 upsert 语义

行字段（JSON 键 / CSV 列同名）：`voteable_id?`、`old_id?`、`name`（必填）、
`name_jp?`、`type?`、`first_appearance?`、`aliases?`（JSON 数组或 `;` 分隔）、
`work?`（work 名）、`work_type?`（自动建 work 时的 type，缺省 `others`）、
`sort_order?`（需 `vote_year` 同传才生效）。

匹配优先级（找到即锁定目标行，只更新**本次提供**的字段，未提供的不动）：

1. `voteable_id` 精确匹配（显式改某行）；
2. `old_id` 匹配；
3. `name` 精确匹配（当前两类数据零重名，见 §一）；
4. 都未命中 → 新建 voteable。

`work` 按 name 精确匹配 `work` 表；无匹配则自动建（`type = work_type`）——
**顺带落地 zfq 计划里记债的 Task 5**。`vote_year` 非空时 upsert
`candidate_*(vote_year, voteable_id)` 行并写 `sort_order`。

### 5.3 冲突与安全

进 `conflicts` 而不是猜：`name` 匹配到的行已有**不同**的非空 `old_id`；
`old_id` 与 `voteable_id` 同给但指向不同行；CSV 解析失败的行；同一批内
重复 key。conflicts 非空时执行请求（`dry_run=false`）**整批拒绝**——先修
数据再导。执行在单事务内，全成或全不成。

### 5.4 快照回填 = 第一份导入文件

`scripts/whitelist_to_import.py`：纯转换器（不碰 DB），把
`whitelist_{character,music}.json` 转成上述导入格式——`old_id`←`id`、
`sort_order`←`system_id`、`work`←`work[0]`（角色）/`album`（音乐）、其余字段
对应搬运。运维动作即：转换 → dry-run 看对账报告（`matched_by_name` 应为
244/612、`create` 应为 0）→ 执行。**报告本身就是对账凭证**，无需独立脚本。

未来 THBWiki 工具的 diff 阶段同样只需产出这个格式的文件。

## 六、admin 查看/编辑（B-057① 收口）

### 6.1 后端

- `GET /api/v1/admin/voteables?category=&q=&vote_year=&page=&page_size=`：
  返回 `{items, total}`；行含 `voteableId`/`name`/`nameJp`/`type`/
  `firstAppearance`/`aliases`/`workId`/`workName`/`oldId`/
  `years: [{voteYear, candidateId, sortOrder}]`。（补上设计 §4.6 里 404 的
  端点，形态按本设计为准。）
- `POST /api/v1/admin/voteables/{category}/{voteable_id}`：编辑
  `name`/`name_jp`/`type`/`first_appearance`/`aliases`/`work_id`/`old_id`。
  `old_id` 改动校验唯一性（与其它行冲突 → 409）。
- `POST /api/v1/admin/candidates/{category}/{candidate_id}/sort-order`：
  单条改 `sort_order`（年度属性走 candidate 行）。
- 均在 `require_admin` 闸门内；写操作走既有 `_safe_log` 审计。

### 6.2 admin-ui（Phase 2）

`VoteablesView`（Vue3，模式对齐既有 WorksView/CandidatesView）：

- 列表：category 切换 + 关键字/年份筛选；列含 name/name_jp/type/work/
  old_id（缺失标黄）/参与年份与 sort_order。
- 编辑弹窗：6.1 的可编辑字段 + 各年度 sort_order；work 下拉选择（可搜索）。
- 导入入口：文件/文本粘贴 → dry-run 报告表格（create/update/conflicts 分组
  展示）→ 确认执行。

## 七、输出契约（加法式，遵守 CLAUDE.md §8）

- `RankingEntity` **新增** `candidate_id: Optional[int] = None`；
  既有 `id` 字段语义**不变**（仍 = 8-hex，取自 `entry.old_id`，未回填时 None）。
- GraphQL 契约层（`result_compat.py`）`RankingEntry` 同步新增 `candidateId`
  可空字段——加法式，现有前端查询不受影响；前端未来按 candidateId 关联
  vote-objects 详情。
- 排名条目的 `name`/`type`/`origin`/`album`/`name_jp` 改由 DB entry 提供。

## 八、落地时序（硬约束）

1. Phase 1 合入 + 部署（迁移 0016 自动跑）。
2. 运维：快照导入（dry-run 对账 → 执行）→ 重跑 compute，确认旧 8-hex 票归票
   正常（现测试机 3 票角色榜应不变）。
3. **此后**前端才可以修字段漂移 / 切 candidateId 提交（`zfq_dev_fe` 侧，
   与 zfq 协调）。切换后新旧格式票都可归票。
4. Phase 2（admin-ui）随后独立合入，不阻塞 1-3。

## 九、已知差异与未来相容性约定

- **多作品塌缩**：旧快照 `work[]` 列表在 DB 为单值 `work_id`，多作品角色的
  ranking `origin` 从「东方灵异传、东方红魔乡」变为单作品名。记录为已知展示
  差异；如需还原，将来加 voteable↔work 关联表（不在本轮）。
- **voteable.id 永不重建**：它是跨年身份锚点，raw 票经 candidate 归属于它。
  任何未来「从头建库」都必须走导入通道 upsert（匹配优先级 §5.2），**禁止
  drop-recreate**。
- **外部身份 = 加列模式**：`old_id`（v11/12 前端 8-hex）是第一个外部身份映射；
  THBWiki page id 等未来身份照此加列，不改既有语义。
- 快照 JSON 与 `scripts/extract_whitelist.mjs` 保留在仓库作为历史 fixture，
  文档标注「运行时零依赖，仅供导入对账/测试样本」。

## 十、测试计划

- **unit**：双键索引（8-hex/candidateId 都命中同一 entry；token 碰撞 raise）；
  canonical 翻译（混合格式聚合、CP multiset 不分裂）；sort_order NULL 兜底
  排序；`"undefined"` 等 malformed 分类计数。
- **integration**：导入 dry-run/执行/幂等（重跑 0 create 0 update）；匹配
  优先级与 conflicts 各分支；work 自动创建；admin 列表/编辑/sort-order 端点
  （鉴权 + 校验 + 审计）；compute 端到端（DB 白名单 + 混合格式 raw 票 →
  排名与 v1 快照口径一致；空白名单中止）。
- **contract**：GraphQL `candidateId` 字段存在且可空；旧查询响应不变。
- 转换器：用真实快照 JSON 跑转换 + 解析（不落库），断言 244/612 行、字段映射。

## 十一、文档与收尾

- CHANGELOG：Added（0016/导入端点/admin 端点/candidateId 字段）+ Changed
  （白名单数据源）+ 部署顺序（§八）。
- BACKLOG：B-050-后补6 置✅；B-057 ①② 置✅（③④⑤仍开放）；
  b050 记忆中「白名单要手动重提取」的维护坑随之作废（改记「数据经导入通道」）。
