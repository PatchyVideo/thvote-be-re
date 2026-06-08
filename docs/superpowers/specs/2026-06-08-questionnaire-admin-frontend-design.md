# 问卷契约变更 — 投票前端设计稿(thvote-fe)

> 创建日期：2026-06-08
> 最后更新：2026-06-08
> 配套后端设计稿：[`2026-06-08-questionnaire-admin-backend-design.md`](./2026-06-08-questionnaire-admin-backend-design.md)
> 仓库：`D:\personal\thvote-fe`，包：`packages/vote`
> **取代** B-039 原前端设计稿(那份按固定 8 槽 + questionnaireV2 静态结构)。

## 一、背景

问卷结构后端化后改为**自由问卷列表**(任意多份,去年份,自增 id)。投票端(voter-facing)问卷模块需适配新契约:
- 结构来源:后端 `GET /questionnaire/structure`(无 vote_year 参数)
- 形状:从固定 8 槽对象 `QuestionnaireDefinitionAllV2` → **问卷数组**
- 分区/门禁:用每份问卷的 `category` / `required` 字段,而非写死的 slot 名
- 隐藏题组:用 `hiddenByDefault` 布尔,而非 `initialQuestionId` 末位约定
- 提交:结构化答案 `submitPaperV2`(不变)

questionnaireV2 的渲染/规则引擎(related 跳转、mutex 互斥)**保留复用** —— 只换"结构来源 + 顶层数据形状 + 分区/隐藏的判定字段"。

## 二、新契约(以后端 SDL/JSON 为准)

`GET /questionnaire/structure` →
```json
{ "questionnaires": [
  { "id", "key", "title", "introduction", "category": "main|extra",
    "required": bool, "order": int,
    "questionGroups": [
      { "id", "order", "hiddenByDefault": bool,
        "questions": [
          { "id", "type": "Single|Multiple|Input", "content", "introduction",
            "maxInputLen",
            "options": [
              { "id", "content", "relatedQuestionIds": [int],
                "mutexOptionIds": [int], "optionGroup": int }
            ] } ] } ] } ] }
```

## 三、改动点

### 1. 结构来源 + 形状
- `packages/vote/src/questionnaire/lib/` 的结构入口改调 `GET /questionnaire/structure`,得到 `questionnaires[]`。
- 弃用 `@touhou-vote/shared/data/questionnaireV2` 作为运行时数据源(类型定义可保留并改造)。
- 顶层从「8 个命名槽」改为「问卷数组」:页面遍历数组渲染,不再按 `requiredQuestionnaire`/`exQuestionnaire1` 等固定键取。

### 2. 分区与展示
- 用 `category`(main/extra)分区(原靠 mainQuestionnaire/extraQuestionnaire 两个 bucket)。
- 用 `order` 排序问卷与题组。
- 用 `hiddenByDefault` 决定题组初始是否隐藏(原靠 initialQuestionId 末位 0)。

### 3. related / mutex
- 引用改为**真实自增 id**(后端分配),不再是编码 id(11011 这类)。
- parser 的 related 跳转 / mutex 互斥逻辑不变,只是 id 来源变了 —— 仍按 id 比对,无需改算法。

### 4. 提交 / 回填 / 完成判定
- 提交仍 `submitPaperV2`(answerState 结构不变:按 questionnaireId/groupId 组织)。
- 回填 `getPaperV2`。
- "问卷是否全部完成"以后端门禁为权威;前端本地预判改为基于 `required=true` 的问卷是否各题组已答。

## 四、保留复用(不改)
- questionnaireV2 的 parser、related 跳转、mutex 互斥、题组隐藏渲染逻辑。
- 这些消费的字段名(relatedQuestionIds/mutexOptionIds/optionGroup/type)后端按此输出,算法层不动。

## 五、测试 / 验收(手工)
- 从后端拉到问卷数组并正确分区(main/extra)、排序渲染。
- related 跳转、mutex 互斥、题组默认隐藏 行为与切换前一致(id 改自增后仍正确)。
- 提交结构化答案 → 回填正确。
- required 问卷未答 → 投票被后端门禁拦截,前端友好提示(与 Block 1 兜底一致)。
- 回归:问卷修改页、各投票页不受影响。

## 六、文件变更一览(前端)

| 文件 | 操作 |
|---|---|
| `packages/vote/src/questionnaire/lib/questionnaire.ts`(V2 入口) | 结构来源改后端 + 顶层改数组遍历 |
| `packages/vote/src/questionnaire/lib/questionnaireV2Parser.ts` | 适配数组 + category/hiddenByDefault 字段(算法不变) |
| `packages/vote/src/questionnaire/Questionnaire.vue` | 按数组/分区渲染;提交/回填 submitPaperV2/getPaperV2 |
| `packages/vote/src/graphql/`(paper v2) | 对齐后端 SDL |
| `packages/shared/data/questionnaireV2.ts` | 运行时数据源停用;interface 改为数组形态(保留作类型) |
| `packages/vote/src/main/main.ts` 守卫 | 完成判定以后端为准 |

## 七、依赖与顺序
- **一次性切换**:后端结构端点(数组契约)+ submitPaperV2 先合并,并用管理端导入/录入题库后,前端同版切换。
- 字段命名严格对齐后端返回(camelCase)。

## 八、关联
- 后端设计稿:[`2026-06-08-questionnaire-admin-backend-design.md`](./2026-06-08-questionnaire-admin-backend-design.md)
