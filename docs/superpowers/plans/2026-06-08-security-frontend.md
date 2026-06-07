# Block 1 安全 — 前端(thvote-fe)Implementation Plan

> **For agentic workers:** 前端为 Vue 3 monorepo,以手工验收为主。本计划描述改动点与验收清单,代码以仓库现有 `.vue` 模式为准。
> 仓库：`D:\personal\thvote-fe`，包：`packages/vote`
> 配套：后端 plan `2026-06-08-security-backend.md` 必须**先合并**(前端依赖新 SDL + 错误码)。

**Goal:** 让前端配合后端 Block 1:二创提名改为"提交待审核"语义并展示逐条结果;投票页防御性处理问卷门禁错误。

**前置依赖:** 后端 Block 1 合并 + GraphQL SDL 更新(`submitDojin` 返回 `DojinSubmitResult`)。

---

## File Map

| 文件 | 操作 |
|---|---|
| `packages/vote/src/graphql/`(submitDojin 定义 + codegen) | Modify — 同步返回类型 |
| `packages/vote/src/vote-doujin/VoteDoujin.vue` | Modify — 结果处理 + 审核语义 + 新错误码 |
| `packages/vote/src/vote-doujin/lib/*` | Modify(如有提交封装) |
| `packages/vote/src/vote-character/VoteCharacter.vue` | Modify — 加门禁错误处理 |
| `packages/vote/src/vote-music/VoteMusic.vue` | Modify — 同上 |
| `packages/vote/src/vote-couple/VoteCouple.vue` | Modify — 同上 |

---

## Task 1: 同步 GraphQL 契约

- [ ] **Step 1:** 拿到后端最终 SDL,确认 `submitDojin` 返回类型与字段命名(camelCase),例如 `DojinSubmitResult { accepted: Int, rejected: [{ index, reason }], skipped: [{ index, reason }] }`。
- [ ] **Step 2:** 更新 `packages/vote/src/graphql/` 下 `submitDojin` 的 mutation 文档(selection set 加上返回字段)。
- [ ] **Step 3:** 跑 codegen(若该包用 graphql-codegen)更新类型。`pnpm --filter vote ...`(按仓库脚本)。
- [ ] **Step 4:** 提交 `feat(vote): sync submitDojin result type with backend`

---

## Task 2: 二创提名页改审核语义

**File:** `packages/vote/src/vote-doujin/VoteDoujin.vue`

- [ ] **Step 1:** 读现有 `submitDojin` 调用与成功/失败处理(约 line 167)。
- [ ] **Step 2:** 提交成功后,读取 `data.submitDojin`(accepted / rejected / skipped),按 §设计稿文案展示:
  - 全部 accepted:`已提交 ${accepted} 条提名，等待人工审核`
  - 有 rejected:逐条 `第 ${index+1} 条未通过：${reason}`(域名不允许 / 作品发布时间不符)
  - 有 skipped:`${skipped.length} 条为重复提名，已跳过`
- [ ] **Step 3:** 错误处理新增分支:
  - GraphQL 错误码 `NOMINATION_CLOSED` → toast「提名通道已关闭」
  - `NOMINATION_NOT_CONFIGURED` → toast「提名功能暂未开放」
- [ ] **Step 4:** 把原"提交成功 = 已投票"的措辞全部改为"已提交待审核"。
- [ ] **Step 5:** 本地 `pnpm --filter vote dev`,手工验收(见末尾清单)。提交 `feat(vote): doujin nomination review semantics + per-item results`

---

## Task 3: 投票页门禁错误兜底

**Files:** `vote-character/VoteCharacter.vue`, `vote-music/VoteMusic.vue`, `vote-couple/VoteCouple.vue`

- [ ] **Step 1:** 各页 submit mutation 的 catch 分支新增:GraphQL 错误码 `QUESTIONNAIRE_NOT_COMPLETED` → toast「请先完成问卷」+ 路由跳问卷页(`router.push` 到问卷路由)。
- [ ] **Step 2:** 确认正常流程(已完成问卷)不受影响。
- [ ] **Step 3:** 提交 `feat(vote): handle QUESTIONNAIRE_NOT_COMPLETED gate error on vote pages`

---

## Task 4:(可选,待确认)已通过提名展示

- [ ] **待产品确认** `GET /nominations/approved` 的消费页面后再实现。本期默认不做。

---

## 手工验收清单
- [ ] 提名:正常 URL → 提示「已提交待审核」
- [ ] 提名:含不在白名单的域名 → 提示该条「域名不允许」,其余正常提交
- [ ] 提名:重复同一作品 → 提示「重复提名已跳过」
- [ ] 提名窗关闭(后端返回 422)→ 提示「提名通道已关闭」
- [ ] 投票:正常流程不受影响
- [ ] 投票:模拟后端 `QUESTIONNAIRE_NOT_COMPLETED` → 友好提示并引导回问卷,不崩溃

---

## 注意
- 前端**不实现**任何安全校验(域名/时间/去重/审核全在后端);前端只负责正确呈现后端结果。
- 联调前严格以后端 SDL 字段命名为准,避免 camelCase/snake_case 不一致。
