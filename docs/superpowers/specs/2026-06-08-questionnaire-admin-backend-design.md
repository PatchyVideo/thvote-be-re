# 问卷管理增强（自由问卷列表 + 全层级 CRUD）— 后端(含管理端)设计稿

> 创建日期：2026-06-08
> 最后更新：2026-06-08
> 配套投票前端设计稿：[`2026-06-08-questionnaire-admin-frontend-design.md`](./2026-06-08-questionnaire-admin-frontend-design.md)
> 取代 B-039 原 admin「仅整树导入」方案;问卷结构去年份、主键自增、契约改问卷数组。

## 一、背景与目标

B-039 已把问卷结构迁到后端,但管理端只有「整树 JSON 导入」,过于敷衍。本次把问卷做成**可持续迭代的自由列表**,管理端支持:
- 问卷级:列表展示、新建、编辑元数据、删除
- 题目级:问题组 / 问题 / 选项 各自的新增、编辑、删除
- 保留整树导入(批量 / 灌历史题库)

并据此调整数据模型与公开契约。

## 二、关键决策(brainstorm 结论)

| 决策 | 选定 |
|---|---|
| 顶层模型 | **任意多份问卷**,问卷级 + 题目级全层级 CRUD |
| 问卷元数据 | 每份带 `key/title/category(main/extra)/required/order` |
| 年份 | 问卷结构**去 `vote_year`**(一份持续迭代的活定义);`paper_answer` 保留 `vote_year` 做轮次分区 |
| 主键 | 四层结构主键改**自增**(admin UI 新建由后端分配,不再手填编码 id) |
| 公开契约 | `GET /questionnaire/structure` 返回**问卷数组**(原固定 8 槽对象作废) |
| 编辑器 | 现有管理端内**自研嵌套编辑器**(无新依赖、契合 GPL、无许可成本) |

## 三、数据模型(migration 0010:drop & recreate 4 张结构表)

> 0008/0009 仅在 zfq_dev 测试、表为空 → 0010 直接 drop & recreate 为新 shape,无数据损失。`paper_answer` 不动。

```python
class QuestionnaireDef(Base):
    __tablename__ = "questionnaire_def"
    id            # Integer PK autoincrement
    key           # String(64) UNIQUE — 稳定标识(admin 填,如 "main_required")
    title         # String(255)
    introduction  # Text
    category      # String(8)  — main / extra
    required      # Boolean default False — 是否计入投票门禁
    order         # Integer default 0

class QuestionGroupDef(Base):
    __tablename__ = "question_group_def"
    id               # Integer PK autoincrement
    questionnaire_id # Integer FK index
    order            # Integer
    hidden_by_default# Boolean default False  — 取代原 initial_question_id 末位约定,语义化

class QuestionDef(Base):
    __tablename__ = "question_def"
    id            # Integer PK autoincrement
    group_id      # Integer FK index
    type          # String(8)  — Single / Multiple / Input
    content       # Text
    introduction  # Text
    order         # Integer
    max_input_len # Integer default 1000

class OptionDef(Base):
    __tablename__ = "option_def"
    id                  # Integer PK autoincrement
    question_id         # Integer FK index
    content             # Text
    related_question_ids# JSON list[int]  — 选中后展示的题 id
    mutex_option_ids    # JSON list[int]  — 互斥选项 id
    option_group        # Integer default 0
    order               # Integer
```

> `hidden_by_default`:原前端用 `initialQuestionId` 末位 0 表达"问题组默认隐藏",自增 id 下该约定失效,改用显式布尔。前端按此渲染。

`paper_answer` 不变:`id, vote_id, vote_year, questionnaire_id, group_id, active_question_id, selected_option_ids(JSON), input_text`。

## 四、公开契约变更

`GET /questionnaire/structure`(去掉 vote_year 参数):
```json
{
  "questionnaires": [
    {
      "id": 1, "key": "main_required", "title": "主问卷·必填",
      "introduction": "...", "category": "main", "required": true, "order": 1,
      "questionGroups": [
        {
          "id": 10, "order": 1, "hiddenByDefault": false,
          "questions": [
            {
              "id": 100, "type": "Single", "content": "...", "introduction": "...",
              "maxInputLen": 1000,
              "options": [
                {"id": 1000, "content": "...", "relatedQuestionIds": [101],
                 "mutexOptionIds": [1001], "optionGroup": 0}
              ]
            }
          ]
        }
      ]
    }
  ]
}
```
- 数组按 `order` 排序;前端按 `category` 分区、`required` 控门禁、`hiddenByDefault` 控初始隐藏。
- camelCase 输出。

## 五、管理端 CRUD 端点(全 `X-Admin-Secret`)

### 问卷级
| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/admin/questionnaires` | 列表(元数据 + group_count) |
| `GET` | `/admin/questionnaires/{id}` | 单份完整树 |
| `POST` | `/admin/questionnaires` | 新建(key/title/category/required/order)→ id |
| `PUT` | `/admin/questionnaires/{id}` | 改元数据 |
| `DELETE` | `/admin/questionnaires/{id}` | 级联删 |

### 问题组级 / 问题级 / 选项级
| `POST` `/admin/question-groups` `/admin/questions` `/admin/options` | 各自新建 → id |
| `PUT` `/admin/question-groups/{id}` `/admin/questions/{id}` `/admin/options/{id}` | 改 |
| `DELETE` 同上 | 级联删子节点 |

### 保留 / 改造
- `POST /admin/questionnaire/import` — 整树导入,接受**问卷数组**形态;id 缺省由后端分配,可选保留传入 id(用于带稳定 id 的题库迁移)。
- 公开 `GET /questionnaire/structure` — 见 §四。
- `submitPaperV2 / getPaperV2` — 不变。

### 错误码
| 场景 | 返回 |
|---|---|
| key 重复(新建/改) | `409 QUESTIONNAIRE_KEY_CONFLICT` |
| 节点 id 不存在 | `404 NOT_FOUND` |
| 父节点不存在(建子节点时) | `404 PARENT_NOT_FOUND` |

## 六、完成校验升级

`QuestionnaireCompletionService.is_complete(vote_id, vote_year)`:
- 读结构(无年份)中 `required=true` 的问卷;
- 完成 = 这些问卷的**每个题组**在 `paper_answer` 中都有作答(与现行 group 级覆盖一致)。
- 投票门禁(角色/音乐/CP)继续调此服务,行为不变,仅"必填问卷"判定从固定 slot 改为 `required` 字段。

## 七、分层

- `QuestionnaireAdminService` + `QuestionnaireAdminDAO`:四层 CRUD + 级联删除(共用 `_collect_descendants` helper)。
- 现有只读 `QuestionnaireService`(structure/answers/completion)保留,assembler 改为输出问卷数组。
- importer 改为解析问卷数组。

## 八、测试策略

| 层 | 覆盖 |
|---|---|
| unit | assembler(rows→问卷数组,排序);importer(数组→rows);completion(required 问卷判定) |
| unit | 级联删除 collect-descendants 逻辑 |
| integration | 四层 CRUD 各端点;级联删(删问卷→组/题/选项全清);key 冲突 409;父不存在 404 |
| integration | structure 公开端点数组形态;import 数组导入 |
| integration | 完成校验:required 问卷未答→门禁拦截;答全→放行 |
| contract | CRUD 端点 403 / shape;structure shape |

## 九、文件变更一览(后端 + 管理端)

| 文件 | 操作 |
|---|---|
| `src/db_model/questionnaire_def.py` | 重塑 4 模型(去 vote_year/slot,加 key/required/hidden_by_default,自增 PK) |
| `alembic/versions/0010_questionnaire_freeform.py` | 新建(drop & recreate 4 表) |
| `src/apps/questionnaire/assembler.py` | 输出改问卷数组 |
| `src/apps/questionnaire/importer.py` | 解析改问卷数组 |
| `src/apps/questionnaire/completion.py` | required 字段判定 |
| `src/apps/questionnaire/admin_dao.py` `admin_service.py` | 新建:四层 CRUD + 级联 |
| `src/apps/questionnaire/router.py` | structure 去年份;返回数组 |
| `src/apps/admin/router.py`(或 questionnaire 子路由) | 13 个 CRUD 端点 + 改造 import |
| `src/admin_ui/index.html` | 问卷配置 Tab:列表页 + 单问卷编辑页 |
| `tests/...` | 新建 |

## 十、与已合并 B-039 的关系

B-039 后端(zfq_dev)是 8 槽 + 年份 + 整树导入。本次**取代**其 admin/契约部分:
- 模型 migration 0010 覆盖 0008 的 shape;
- assembler/importer/structure 契约从 8 槽对象改问卷数组;
- 投票门禁、submitPaperV2/getPaperV2、paper_answer 复用不变。

## 十一、关联

- 投票前端设计稿:[`2026-06-08-questionnaire-admin-frontend-design.md`](./2026-06-08-questionnaire-admin-frontend-design.md)
- BACKLOG:B-041
