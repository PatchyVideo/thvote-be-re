# Block 3A 问卷结构化系统 — 前端设计稿(thvote-fe)

> 创建日期：2026-06-08
> 最后更新：2026-06-08
> 配套后端设计稿：[`2026-06-08-questionnaire-backend-design.md`](./2026-06-08-questionnaire-backend-design.md)
> 仓库：`D:\personal\thvote-fe`，包：`packages/vote`

## 一、背景

问卷结构当前由前端 `@touhou-vote/shared/data/questionnaireV2` 静态定义,提交时经兼容层 `questionnaireV2PaperJson.ts` 转成旧 `paperJson` blob 发后端。本块**一次性切换**为:结构从后端拉、提交结构化答案、弃 paperJson 兼容层。

前端 questionnaireV2 的解析/渲染/规则引擎(related 跳转、mutex 互斥)**保留复用** —— 只把"结构数据来源"和"提交格式"换掉。

## 二、改动点

### 1. 结构来源:静态 → 后端
- `packages/vote/src/questionnaire/lib/questionnaire.ts`(或 V2 入口)改为调 `GET /questionnaire/structure?vote_year=`,拿到 `QuestionnaireDefinitionAllV2` 形状的 JSON。
- 后端返回形状已对齐 `questionnaireV2.ts` 的 interface,**parser/渲染层不用改**,只换数据入口。
- 移除/停用 `shared/data/questionnaireV2.ts` 作为运行时数据源(可保留 interface 类型定义)。

### 2. 提交:paperJson → 结构化
- 提交改调 `submitPaperV2`(结构化 `QuestionnaireAnswerStateV2`),不再走 `serializeQuestionnaireAnswerStateV2ToPaperJson`。
- **弃用兼容层** `questionnaireV2PaperJson.ts`(一次性切换;如需回滚再说)。
- 回填改调 `getPaperV2`。

### 3. 完成判定:前端本地 → 后端
- 路由守卫 `IsQuestionnaireAllDone` 的"完成"以**后端判定**为准(投票门禁后端权威);前端仍可本地预判用于 UI,但最终以后端为准。

## 三、保留复用(不改)
- questionnaireV2 的 parser(`questionnaireV2Parser.ts`)、related 跳转、mutex 互斥、问题组隐藏(initialQuestionId 末位 0)等规则引擎。
- 这些消费的是 `QuestionnaireDefinitionAllV2` 形状 —— 后端按此形状返回即可无缝对接。

## 四、契约(以后端 SDL/JSON 为准)
- `GET /questionnaire/structure?vote_year=` → `QuestionnaireDefinitionAllV2`
- `submitPaperV2(QuestionnaireAnswerStateV2)` → ok
- `getPaperV2(voteToken) → QuestionnaireAnswerStateV2`
- 字段命名联调时对齐(后端尽量直接产出 camelCase 形状)。

## 五、测试/验收(手工)
- 进入问卷页:从后端拉到结构并正确渲染(题组/题型/选项)。
- related 跳转、mutex 互斥、问题组隐藏 行为与切换前一致。
- 提交结构化答案 → 回填正确。
- 未完成必答题 → 投票被后端门禁拦截(与 Block 1 前端兜底一致)。
- 回归:问卷修改、各投票页不受影响。

## 六、文件变更一览(前端)

| 文件 | 操作 |
|---|---|
| `packages/vote/src/questionnaire/lib/questionnaire.ts` / V2 入口 | 改结构来源为后端 |
| `packages/vote/src/questionnaire/lib/questionnaireV2PaperJson.ts` | 停用(一次性切换) |
| `packages/vote/src/questionnaire/Questionnaire.vue` | 提交改 submitPaperV2 + 回填 getPaperV2 |
| `packages/vote/src/graphql/`(paper v2 操作) | 新增 + codegen |
| `packages/shared/data/questionnaireV2.ts` | 运行时数据源停用,保留 interface |
| `main/main.ts` 守卫 | 完成判定以后端为准 |

## 七、依赖与顺序
- **一次性切换**:必须后端 structure + submitPaperV2 先上、且用 `/admin/questionnaire/import` 把现有题库灌进后端后,前端同一版切换。
- 建议:后端先合并 + 灌题库 → 前端切换 → 联调。

## 八、关联
- 后端设计稿:[`2026-06-08-questionnaire-backend-design.md`](./2026-06-08-questionnaire-backend-design.md)
