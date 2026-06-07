# Block 2 作品投票 — 后端(含管理端)设计稿

> 创建日期：2026-06-08
> 最后更新：2026-06-08
> 配套前端设计稿：[`2026-06-08-works-voting-frontend-design.md`](./2026-06-08-works-voting-frontend-design.md)

## 一、背景与目标

官方作品(东方正作/CD/书籍等)投票在旧后端仅留壳子、前端无 vote-work 页 —— 全新功能。本块实现**后端完整作品投票链路**,每一层镜像角色(character),并把"前端从后端拉投票对象列表"的模式先在作品上跑通(Block 3 投票对象迁后端的试点)。

## 二、关键决策(brainstorm 结论)

| 决策 | 选定 |
|---|---|
| 提交形态 | **完全仿角色/音乐**:按 id 多选 + 一个本命(first)+ 每项 reason;数量上限默认 8(可配/可调) |
| 候选数据源 | **直接进后端 `candidate_work`,前端从后端拉**(目标形态,Block 3 试点) |
| 结果展示 | **后端 ComputeService 算 + 结果查询端点**,前端 result 页展示 |
| 门禁 | 作品投票同样套用 **Block 1 问卷门禁** |

## 三、数据模型(migration 0008)

### 新表 `candidate_work`(仿 `candidate_character` + 发布时间)
```python
class CandidateWork(Base):
    __tablename__ = "candidate_work"
    id            # Integer PK autoincrement
    vote_year     # Integer index
    name          # String(255) NOT NULL
    name_jp       # String(255) server_default ""
    category      # String(64) server_default ""   — 正作/CD/书籍/其他
    release_date  # String(16) nullable             — 发布时间,用于"按发布时间分类"
    __table_args__ = UniqueConstraint("vote_year", "name")
```
> 必填仅 `name`(对齐候选管理的 insertSelective 规则)。

### 新表 `work`(处理层,仿 `character` 表)
```python
class Work(Base):
    __tablename__ = "work"
    id              # String FK user.id PK
    submit_datetime # DateTime
    work_list       # JSON   — [{id, first, reason}]
```

### 已有 `raw_work`(Block A 同步时建,不动)

## 四、候选管理扩展(管理端,零新增端点)

候选管理已是 **schema 驱动**(`candidate_field_specs` / `validate_items` 从模型列推导)。只需:
1. `_model_for(category)` 与候选 service/DAO 的 category 映射加 `"work" -> CandidateWork`。
2. 把 import/edit/fields/list/delete 的 `category` 文案/校验从 `Literal["character","music"]` 扩为含 `"work"`。

→ 作品候选的 **CSV/JSON 导入、编辑、列表、删除、字段自省全部自动可用**,管理端 UI 的类别下拉加一个"作品"选项即可。

## 五、投票链路(逐层镜像角色)

| 层 | 角色现状 | 作品新增 |
|---|---|---|
| 提交校验 | `validate_character`(数量[1,8]、单本命、去重) | `validate_work` 同规则 |
| raw 存储 | `submit_character` → raw_character | `submit_work` → raw_work |
| 处理层 | vote_data `submit_character` → character 表 | vote_data `submit_work` → work 表 |
| 计算读取 | `ComputeDAO.load_char_votes` / `load_char_candidates` | `load_work_votes` / `load_work_candidates` |
| 排名计算 | ComputeService 角色计算 → Redis `result:{year}:chars:*` | 作品计算 → `result:{year}:works:*` |
| 结果查询 | REST/GraphQL character ranking | work ranking |
| GraphQL | submitCharacterVote / getSubmitCharacterVote | submitWorkVote / getSubmitWorkVote |
| 门禁 | (Block 1 加) | 同样套用问卷门禁 |

> 实现策略:逐层"读角色代码 → 仿写作品"。category key 约定 `"work"`,Redis key 段用 `works`。

## 六、投票对象列表端点(前端拉,Block 3 试点)

```
GET /vote-objects/works?vote_year=
→ { vote_year, groups: [ { group: "<发布时间分类>", items: [ {id, name, name_jp, release_date, category} ] } ] }
```
- 从 `candidate_work` 读,**按 `release_date`(或 category)分组**返回,供前端投票页直接渲染选择组件。
- 公开只读(投票页需要),可选加 vote_token 校验;本期公开。
- 这是 Block 3 "投票对象分类查询"的作品先行版;Block 3 会把 character/music 也纳入同一模式。

## 七、配置

- 复用 `vote_year`、投票时间窗。作品数量上限可硬编码 8(对齐角色),或加 `WORK_VOTE_MAX`(可选,默认 8)。

## 八、测试策略

| 层 | 覆盖 |
|---|---|
| unit | `validate_work`(数量/本命/去重);候选 fields 含 work |
| unit | ComputeService 作品计算(仿角色计算测试) |
| integration | submit_work 全链路(含问卷门禁拦截);work 候选导入;`/vote-objects/works` 分组 |
| integration | 结果查询 work ranking(Redis 命中/未命中) |
| contract | submitWorkVote / getSubmitWorkVote SDL；`/vote-objects/works` shape；候选 work 端点 |

## 九、文件变更一览(后端 + 管理端)

| 文件 | 操作 |
|---|---|
| `src/db_model/candidate.py` | 加 CandidateWork |
| `src/db_model/work.py` | 新建 Work 处理表 |
| `src/db_model/__init__.py` | 导出 |
| `alembic/versions/0008_work_voting.py` | 新建 migration |
| `src/apps/admin/candidate_service.py` + 候选 DAO/service | category 映射加 work |
| `src/apps/admin/schemas.py` / router | category Literal 扩 work |
| `src/apps/submit/{service,schemas,dao}.py` | submit_work + validate_work |
| `src/apps/vote_data/{service,dao,models}.py` | work 处理层 |
| `src/apps/result/{compute,compute_dao,compute_service,service,dao,router}.py` | 作品计算 + 查询 |
| `src/api/graphql/...` | submitWorkVote/getSubmitWorkVote/work ranking |
| `src/apps/<新>/vote_objects` 或 result router | `/vote-objects/works` |
| `src/admin_ui/index.html` | 候选类别下拉加"作品" |
| `tests/{unit,integration,contract}/...` | 新建 |

## 十、依赖

- **问卷门禁**:依赖 Block 1(`_require_questionnaire`)。若 Block 1 未先做,作品投票门禁同步实现一份相同逻辑。
- 前端 vote-work 依赖本块后端 + `/vote-objects/works` 先合并。

## 十一、关联

- 前端设计稿:[`2026-06-08-works-voting-frontend-design.md`](./2026-06-08-works-voting-frontend-design.md)
- BACKLOG:B-038
