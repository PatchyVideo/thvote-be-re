# 管理端（Admin Panel）— 设计稿

> 创建日期：2026-06-07
> 最后更新：2026-06-07

## 一、背景与目标

现有管理端有 3 个 REST 端点（compute-results、import-candidates、finalize-ranking），鉴权依赖 `X-Admin-Secret` header，无 Web 界面，只能通过 curl/脚本调用。

本文档设计：
1. **REST API 扩展**——补全运营操作所需的端点
2. **简单 Web UI**——单 HTML 文件，供运营人员在浏览器中操作，托管在当前 FastAPI 服务内

---

## 二、鉴权模型

**现有机制保持不变**：所有 `/admin/*` 端点读取 `X-Admin-Secret` header，与 `Settings.admin_secret` 比对，不匹配返回 403。

Web UI 的处理：
- 首次访问弹出输入框，要求填写 Admin Secret
- 存入 `sessionStorage`（浏览器会话级，关闭标签页即失效）
- 所有 `fetch` 请求自动带上 `X-Admin-Secret` header

---

## 三、REST API 扩展

现有端点（不变）：`compute-results`、`import-candidates`、`finalize-ranking`、`reload-config`、`discover`、`discover-self`

### 3.1 同步管理

详见 [mongodb-sync-design.md](./2026-06-07-mongodb-sync-design.md) §六。

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/admin/sync/start` | 启动 MongoDB 历史数据同步 |
| `GET` | `/admin/sync/status` | 当前运行进度 |
| `GET` | `/admin/sync/history` | 历史运行记录（分页） |
| `POST` | `/admin/sync/retry/{run_id}` | 从断点续跑 |
| `POST` | `/admin/sync/cancel` | 取消当前运行 |

### 3.2 用户管理

| 方法 | 路径 | Query Params | 说明 |
|---|---|---|---|
| `GET` | `/admin/users` | `phone`, `email`, `page`(1), `page_size`(20) | 按手机或邮箱搜索用户 |
| `GET` | `/admin/users/{user_id}` | — | 用户详情 + 各类别投票提交状态 |
| `PATCH` | `/admin/users/{user_id}/ban` | — | 软删除（`removed=true`） |
| `PATCH` | `/admin/users/{user_id}/unban` | — | 恢复（`removed=false`） |

`GET /admin/users/{user_id}` 响应包含：
```json
{
  "user": { "id", "nickname", "email", "phone", "email_verified", "phone_verified", "register_date", "removed" },
  "vote_submitted": { "character": bool, "music": bool, "cp": bool, "paper": bool, "dojin": bool }
}
```

### 3.3 统计与排名

| 方法 | 路径 | Query Params | 说明 |
|---|---|---|---|
| `GET` | `/admin/stats` | `vote_year`(可选) | 总用户数、各类别提交数、投票窗口状态 |
| `GET` | `/admin/ranking/preview` | `vote_year`, `category`, `limit`(50) | 预览 Redis 中当前计算结果（不写 DB） |

`GET /admin/stats` 响应：
```json
{
  "vote_year": 2024,
  "total_users": 12345,
  "vote_window": { "status": "open/closed/upcoming", "start": "ISO", "end": "ISO" },
  "submissions": { "character": 9800, "music": 7600, "cp": 5200, "paper": 4100, "dojin": 1800 }
}
```

### 3.4 候选项管理

| 方法 | 路径 | Query Params | 说明 |
|---|---|---|---|
| `GET` | `/admin/candidates` | `category`(character/music), `vote_year`, `q`(名称模糊搜索), `page`(1), `page_size`(50) | 候选项列表 |
| `DELETE` | `/admin/candidates/{id}` | — | 删除单条候选项 |

### 3.5 运维

| 方法 | 路径 | Query Params | 说明 |
|---|---|---|---|
| `GET` | `/admin/activity-logs` | `user_id`, `action`, `since`(ISO), `page`(1), `page_size`(50) | 审计日志查询 |
| `GET` | `/admin/export/votes` | `vote_year`, `category`(character/music/cp/paper/dojin) | 流式导出 CSV，`Content-Disposition: attachment` |

---

## 四、Web UI 设计

### 4.1 托管方式

```python
# src/main.py
from fastapi.staticfiles import StaticFiles
app.mount("/admin-ui", StaticFiles(directory="src/admin_ui", html=True), name="admin_ui")
```

文件结构：
```
src/admin_ui/
  index.html    # 单文件，包含全部 HTML / CSS / JS
```

访问地址：`http://host/admin-ui/`

### 4.2 登录覆盖层

- 页面加载时检查 `sessionStorage.getItem("adminSecret")`
- 若不存在，渲染全屏覆盖层：输入框 + "进入" 按钮
- 提交后向 `/admin/stats` 发一次探测请求；返回 200 则保存并隐藏覆盖层，返回 403 则提示错误

### 4.3 页面布局

```
┌──────────────────────────────────────────────────────────────┐
│  THVote Admin                                         [退出] │
├──────────────────────────────────────────────────────────────┤
│  [Dashboard] [用户管理] [数据同步] [候选项] [审计日志] [导出] │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  < 当前 Tab 内容区 >                                          │
│                                                              │
└──────────────────────────────────────────────────────────────┘
│  < Toast 通知（底部浮动，3s 自动消失）>                        │
```

### 4.4 各 Tab 规格

**Dashboard**

内容：
- 统计卡片行：总用户 / 角色投票数 / 音乐投票数 / CP 投票数 / 投票窗口状态（页面加载时调 `/admin/stats`）
- 快捷操作按钮（点击前弹确认对话框）：
  - Compute Results（POST /admin/compute-results）
  - Finalize Ranking（POST /admin/finalize-ranking，需先选 vote_year）
  - Reload Config（POST /admin/reload-config）

---

**用户管理**

内容：
- 搜索表单（手机号 / 邮箱输入框 + 搜索按钮）
- 结果表格列：ID（截短显示）、昵称、邮箱、手机、邮箱已验证、手机已验证、注册时间、状态
- 每行操作：Ban / Unban 按钮（点击确认后 PATCH）
- 点击行展开：显示各类别投票提交情况

---

**数据同步**

内容：
- MongoDB 连接状态提示（已配置 / 未配置，调 `/admin/sync/status` 判断）
- 同步设置：集合勾选框（voters / raw_character / ... / final_ranking_char / chars）+ 批次大小输入
- Start 按钮 / Cancel 按钮
- 进度区（运行时显示）：进度条 + 当前集合名 + 已处理/总数/错误数（每 2s 轮询 `/admin/sync/status`）
- 历史记录表格：run_id（前8位）、开始时间、状态、集合、插入数、错误数、操作（Retry）

---

**候选项**

内容：
- 筛选栏：category 下拉 + vote_year 输入 + 名称搜索框
- 分页表格：name、name_jp、type、origin/album、first_appearance、操作（Delete）
- Delete 点击后确认对话框，成功后刷新当页

---

**审计日志**

内容：
- 筛选栏：user_id 输入 + action 输入 + since 日期选择器
- 分页表格：时间、user_id、action、IP

---

**导出**

内容：
- vote_year 输入 + category 下拉
- "Download CSV" 按钮 → 触发 `GET /admin/export/votes?vote_year=&category=` 作为文件下载（`window.location` 或 hidden anchor）

---

### 4.5 实现约束

- **零外部依赖**：原生 `fetch`，无 npm/构建步骤，无 CDN 引用
- **fetch 封装**：统一函数 `adminFetch(path, opts)` 自动附加 `X-Admin-Secret`，统一处理 403（清除 sessionStorage，跳回登录）和网络错误（Toast 提示）
- **动态渲染**：表格内容通过 `innerHTML` 构建（admin-only 页面，无 XSS 风险）
- **样式**：内联 `<style>` 块，深色主题，无外部字体/图标库，移动端不做适配

---

## 五、文件变更一览

| 文件 | 操作 | 说明 |
|---|---|---|
| `src/admin_ui/index.html` | 新建 | Web UI 单文件 |
| `src/main.py` | 修改 | 挂载 StaticFiles |
| `src/apps/admin/router.py` | 修改 | 新增 §三全部端点 |
| `src/apps/admin/service.py` | 修改 | 新增用户管理、stats、preview、候选项删除、日志、导出逻辑 |
| `src/apps/admin/schemas.py` | 修改 | 新增请求/响应模型 |
| `src/apps/admin/sync/` | 新建目录 | 见 mongodb-sync-design.md |
| `src/apps/user/dao.py` | 修改 | 新增 `search_users()`、`ban_user()`、`unban_user()` |
| `src/apps/result/dao.py` | 修改 | 新增 `get_preview_ranking()` |
| `src/db_model/candidate.py` | 修改 | 无（复用现有 CandidateCharacter/Music） |

---

## 六、测试策略

| 层次 | 覆盖内容 |
|---|---|
| unit | `AdminService` 各方法：mock DAO，验证调用链和参数 |
| unit | `export_votes_csv()`：验证 CSV 列名和行格式 |
| integration | `GET /admin/users`：搜索返回正确用户；ban/unban 正确修改 `removed` 字段 |
| integration | `GET /admin/stats`：返回各类别正确统计数 |
| contract | 所有新端点：无 Secret → 403；有 Secret → 响应结构符合 schema |

Web UI 为静态 HTML，不进入自动化测试（手工验收）。

---

## 七、关联文档

- MongoDB 同步设计：[`docs/superpowers/specs/2026-06-07-mongodb-sync-design.md`](./2026-06-07-mongodb-sync-design.md)
- 现有管理端代码：`src/apps/admin/router.py`、`src/apps/admin/service.py`
- BACKLOG 追踪：新增 B-034（admin panel）
