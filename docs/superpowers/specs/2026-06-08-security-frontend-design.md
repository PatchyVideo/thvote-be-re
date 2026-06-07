# Block 1 安全 — 前端设计稿(thvote-fe)

> 创建日期：2026-06-08
> 最后更新：2026-06-08
> 配套后端设计稿：[`2026-06-08-security-backend-design.md`](./2026-06-08-security-backend-design.md)
> 仓库：`D:\personal\thvote-fe`(pnpm monorepo,packages/vote)

## 一、背景

Block 1 后端给二创提名加了"自动校验 + 人工审核队列",并对投票加了"问卷完成"门禁。这两处改变了前端能收到的响应,前端需配合:

1. **二创提名语义变化** —— 提交不再等于"已计入",而是"已提交,等待审核";且后端会逐条返回通过/拒绝/重复,前端要把结果如实告诉用户。
2. **投票门禁** —— 后端可能返回 `QUESTIONNAIRE_NOT_COMPLETED`,前端要友好处理(正常流程下路由守卫已挡住,这是防御)。
3. **(待确认)** 已通过提名列表的展示。

前端**不做**任何安全校验逻辑(校验在后端);前端只负责正确发请求、正确呈现后端结果。

## 二、改动点

### 1. 二创提名页(`packages/vote/src/vote-doujin/`)

**当前**:`submitDojin` mutation 成功即提示"提交成功"。

**改为**:
- mutation 响应改为读取后端返回的逐条结果 `{ accepted, rejected[], skipped[] }`(GraphQL 类型同步更新,见 codegen)。
- 提交后文案改为审核语义,例如:
  - 全部通过:"已提交 N 条提名,等待人工审核"
  - 部分被拒:"X 条已提交待审核;Y 条未通过:<逐条 reason>(如 域名不允许 / 发布时间不符)"
  - 重复:"Z 条为重复提名,已跳过"
- 处理新错误:
  - `422 NOMINATION_CLOSED` → "提名通道未开放 / 已关闭"
  - `503 NOMINATION_NOT_CONFIGURED` → "提名功能暂未开放"
- (可选)页面顶部显示提名开放窗口状态(若后端后续提供活动状态端点;本期可先沿用前端静态时间或仅靠提交时的报错)。

### 2. 投票提交页(`vote-character` / `vote-music` / `vote-couple`)

- 在各 submit mutation 的错误处理里,新增对 `QUESTIONNAIRE_NOT_COMPLETED` 的捕获 → 友好提示"请先完成问卷"并引导回问卷页。
- 这是防御性处理:正常流程 `main.ts` 路由守卫(`IsQuestionnaireAllDone`)已阻止,但后端门禁是真权威,前端需优雅兜底而非抛原始错误。

### 3. (待确认)已通过提名展示

- 后端提供 `GET /nominations/approved`(udid 去重聚合 + 提名计数)。
- **待确认**:这个列表给谁用?需求文档写"供组合部门投票页面",但二创≠组合,存疑。
  - 若确实要在某页面展示已通过的二创提名 → 前端加一个列表视图消费该端点。
  - 若暂不需要 → 前端本期不动,端点先备着。
- **本期默认:前端不实现该展示,待与产品确认消费方后再补。**

## 三、GraphQL 契约同步

- 后端 `submitDojin` 返回类型从无返回改为 `DojinSubmitResult { accepted, rejected[], skipped[] }`(具体字段名以后端 SDL 为准)。
- 前端 `packages/vote/src/graphql/` 下对应 mutation 定义 + codegen 类型需同步更新。
- 联调前以后端 SDL 为准对齐字段命名(camelCase)。

## 四、测试/验收(前端)

前端为 Vue,手工验收为主:
- 提名提交:构造全通过 / 含被拒域名 / 含重复 三种输入,确认文案正确反映后端逐条结果。
- 提名窗关闭:后端返回 422,确认提示"提名已关闭"。
- 投票门禁:绕过路由守卫直接触发投票(或 mock 后端 422),确认友好提示而非崩溃。
- 回归:正常提名/投票流程不受影响。

## 五、文件变更一览(前端)

| 文件 | 操作 |
|---|---|
| `packages/vote/src/vote-doujin/VoteDoujin.vue` | 改提交结果处理 + 审核语义文案 + 新错误码 |
| `packages/vote/src/vote-doujin/lib/*` | 如有提交封装,同步 |
| `packages/vote/src/graphql/`(submitDojin 定义 + codegen) | 同步返回类型 |
| `packages/vote/src/vote-character|music|couple/*.vue` | 加 `QUESTIONNAIRE_NOT_COMPLETED` 错误处理 |
| (可选)新增已通过提名列表视图 | 待确认后再定 |

## 六、与后端的联调依赖

- 前端改动**依赖后端先合并** Block 1 后端(新响应 shape + 错误码)。
- 建议顺序:后端 + 管理端先上 → 前端按最终 SDL 对齐 → 联调提名/投票链路。

## 七、关联

- 后端设计稿:[`2026-06-08-security-backend-design.md`](./2026-06-08-security-backend-design.md)
