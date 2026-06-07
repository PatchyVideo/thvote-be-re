# Block 3A 问卷结构化系统 — 后端(含管理端)设计稿

> 创建日期：2026-06-08
> 最后更新：2026-06-08
> 配套前端设计稿：[`2026-06-08-questionnaire-frontend-design.md`](./2026-06-08-questionnaire-frontend-design.md)

## 一、背景与目标

当前问卷结构全在前端(`@touhou-vote/shared/data/questionnaireV2`),后端只存不透明的 `papers_json` blob。需求要求后端可配置问卷(admin 增删改查问卷/问题组/问题/选项),并以问卷完成作为投票前置。

本块把问卷结构迁到后端,**结构形状对齐前端 `questionnaireV2`**,使结构查询端点能直接喂给前端 parser。迁移策略:**一次性切换**(后端结构上线 → 前端改从后端拉 + 提交结构化答案 → 弃 paperJson)。

## 二、对齐基准:前端 questionnaireV2 形状

后端结构与端点输出严格对齐 `packages/shared/data/questionnaireV2.ts`:
```
QuestionnaireDefinitionAllV2
  mainQuestionnaire:  { requiredQuestionnaire, optionalQuestionnaire1, optionalQuestionnaire2 }
  extraQuestionnaire: { exQuestionnaire1..5 }
QuestionnaireDefinitionV2 { id, name, introduction, questionGroups[] }
QuestionnaireGroupV2 { id, questionnaireId, order, initialQuestionId, questions[] }
  // initialQuestionId 末位为 0 表示该问题组默认隐藏
QuestionnaireQuestionV2 { id, type:'Single'|'Multiple'|'Input', content, introduction, options[] }
QuestionnaireOptionV2 { id, content, relatedQuestionIds[], mutexOptionIds[], optionGroup }
答案 QuestionnaireAnswerStateV2:每问卷 groups[]{ groupId, activeQuestionId, selectedOptionIds[], input }
```

## 三、关键决策(brainstorm 结论)

| 决策 | 选定 |
|---|---|
| 迁移程度 | **全迁**:后端存完整结构 + admin 可配 |
| 迁移策略 | **一次性切换**(弃 paperJson 兼容层) |
| 对齐基准 | 后端结构/端点 = 前端 questionnaireV2 形状 |

## 四、数据模型(migration 0009)

> 数值 id 沿用前端约定(结构化编码)。related/mutex 用 JSON 数组字段直接存,免过度规范化。

```python
class QuestionnaireDef(Base):
    __tablename__ = "questionnaire_def"
    id            # Integer PK (= questionnaireV2 的 questionnaire id,如 11/12/13/21..25)
    vote_year     # Integer index
    slot          # String(32)  — required/optional1/optional2/ex1..ex5(对应前端 8 个槽位)
    category      # String(8)    — main / extra
    name          # String(255)
    introduction  # Text
    order         # Integer
    __table_args__ = UniqueConstraint("vote_year", "id")

class QuestionGroupDef(Base):
    __tablename__ = "question_group_def"
    id                  # Integer PK (= group id)
    questionnaire_id    # Integer FK questionnaire_def.id index
    order               # Integer
    initial_question_id # Integer  — 末位 0 = 默认隐藏

class QuestionDef(Base):
    __tablename__ = "question_def"
    id            # Integer PK (= question id,如 11011)
    group_id      # Integer FK question_group_def.id index
    type          # String(8)  — Single/Multiple/Input
    content       # Text
    introduction  # Text
    order         # Integer
    max_input_len # Integer default 1000

class OptionDef(Base):
    __tablename__ = "option_def"
    id                  # Integer PK (= option id)
    question_id         # Integer FK question_def.id index
    content             # Text
    related_question_ids# JSON  — list[int]
    mutex_option_ids    # JSON  — list[int]
    option_group        # Integer default 0
    order               # Integer
```

### 结构化答题(替代 paperJson)
```python
class PaperAnswer(Base):
    __tablename__ = "paper_answer"
    id            # Integer PK autoincrement
    vote_id       # String(255) index
    vote_year     # Integer index
    questionnaire_id  # Integer
    group_id      # Integer
    active_question_id # Integer nullable
    selected_option_ids # JSON  — list[int]
    input_text    # Text nullable
    __table_args__ = UniqueConstraint("vote_id", "vote_year", "questionnaire_id", "group_id")
```

> `raw_paper`(旧 blob)保留作历史/留档,不再写新数据。

## 五、后端端点

### 公开
| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/questionnaire/structure?vote_year=` | 组装成 `QuestionnaireDefinitionAllV2` 形状返回,供前端直接 render |
| `POST`(GraphQL `submitPaperV2`) | — | 提交结构化答案(`QuestionnaireAnswerStateV2` 形状)→ 写 paper_answer |
| `GET`(GraphQL `getPaperV2`) | — | 回填该用户结构化答案 |

### 管理端(admin CRUD,随后端)
| 方法 | 路径 | 说明 |
|---|---|---|
| `GET/POST/PUT/DELETE` | `/admin/questionnaires` `/{id}` | 问卷增删改查 |
| `GET/POST/PUT/DELETE` | `/admin/question-groups` `/{id}` | 问题组 |
| `GET/POST/PUT/DELETE` | `/admin/questions` `/{id}` | 问题(type/related) |
| `GET/POST/PUT/DELETE` | `/admin/options` `/{id}` | 选项(mutex/related) |
| `POST` | `/admin/questionnaire/import` | 整树 JSON 一次性导入(可选,便于从前端 questionnaireV2 迁移现有题库) |

> admin UI:管理端新「问卷配置」Tab(树形:问卷→组→题→选项;增删改;related/mutex 编辑)。**整树导入端点**让首次迁移可直接把前端 questionnaireV2 的 JSON 灌进来。

## 六、完成校验升级(替换 Block 1 弱门禁)

Block 1 的 `_require_questionnaire(vote_id)` 从"存在任意 paper"升级为:
```
完成 = 所有 category=main 且 slot∈{required}(及业务规定的必填问卷)的问卷,
       其所有"必答问题"在 paper_answer 中均有合法答案
```
- 实现:`QuestionnaireCompletionService.is_complete(vote_id, vote_year)` 读结构(必填问卷的必答题)+ 读 paper_answer 比对。
- 投票门禁(角色/音乐/CP/作品)统一改调此服务。

## 七、复用 / 迁移

- **首次迁移**:用 `/admin/questionnaire/import` 把前端 `questionnaireV2.ts` 当前题库 JSON 一次性导入后端(避免手工录入)。
- **管理端**:配置 Tab 仿候选项 Tab 的白色主题 + 弹窗。

## 八、测试策略

| 层 | 覆盖 |
|---|---|
| unit | 结构组装(DB 行 → QuestionnaireDefinitionAllV2 形状);完成校验逻辑(必答题齐/缺) |
| unit | 整树导入解析 |
| integration | admin CRUD 各级;structure 查询 shape;submitPaperV2 写 paper_answer;getPaperV2 回填 |
| integration | 投票门禁升级:必答未答→拦截,已答→放行 |
| contract | 公开 structure / submitPaperV2 SDL;admin CRUD 403/shape |

## 九、文件变更一览

| 文件 | 操作 |
|---|---|
| `src/db_model/questionnaire_def.py` 等 | 新建 4 个结构模型 + PaperAnswer |
| `src/db_model/__init__.py` | 导出 |
| `alembic/versions/0009_questionnaire_structure.py` | 新建 |
| `src/apps/questionnaire/`(新 domain:router/service/dao/schemas) | 新建:结构查询 + 提交 + 完成校验 |
| `src/apps/admin/...` | 问卷配置 CRUD 端点 + 整树导入 |
| `src/api/graphql/...` | submitPaperV2 / getPaperV2 |
| `src/apps/submit/service.py` | 门禁改调 QuestionnaireCompletionService |
| `src/admin_ui/index.html` | 问卷配置 Tab |
| `tests/...` | 新建 |

## 十、依赖与顺序

- 升级门禁依赖 Block 1 的门禁挂载点已存在。
- 前端一次性切换依赖本块后端 + structure/submitPaperV2 合并。

## 十一、关联

- 前端设计稿:[`2026-06-08-questionnaire-frontend-design.md`](./2026-06-08-questionnaire-frontend-design.md)
- BACKLOG:B-039
