# 作品批量导入实施计划

> 用户已确认设计并要求开干；当前执行者按 executing-plans 直接实施，不再询问执行方式。

**Goal:** works.json 能通过作品页预览并批量导回。

**Architecture:** 在现有 WorkService 处理解析、匹配及一次事务写入；管理员路由只做契约和缓存衔接；作品页复用既有 Modal 和 API 客户端。

**Tech Stack:** 现有 FastAPI/Pydantic/SQLAlchemy/Vue/TypeScript，无新依赖。

**Spec:** [已确认规则](../specs/2026-11-10-work-bulk-import-design.md)。

## 全局约束

沿用当前 feat 分支并保留无关改动。无真实数据操作、提交、推送或部署；不扩大到 candidate、角色音乐导入或旧单条作品接口修复。验证仅相关已有检查及新增关键行为覆盖，无浏览器交互。

## Task 1：导入契约和业务处理

**Files:** src/apps/admin/schemas.py、work_service.py、router.py；tests/integration/test_admin_voteables.py。

- [x] 先在既有测试中覆盖 JSON 新增/更新/跳过及预览不写、CSV 解析、错误整批不写、管理员保护。
- [x] 新增显式请求/响应模型；WorkService.import_works 解析、按名称规划并提交一次；错误时返回 applied=false。
- [x] 静态 /works/import 路由置于 /works/{work_id} 之前，写入成功后复用缓存失效。
- [x] 扩展现有导出往返测试，使作品也通过实际新接口恢复；验证更新保持作品 ID 与角色/音乐关联。

## Task 2：页面及集中交付

**Files:** admin-ui/src/api/works.ts、views/WorksView.vue、src/admin_ui 构建产物、接口文档及 changelog。

- [x] 文件选择支持 JSON/CSV，可查看/修改内容；展示预览分类和错误，内容变化时清除旧预览，确认后显示实际结果。
- [x] 同步文档说明 name/type、dry_run、错误不写及恢复顺序；旧导出文档标记作品导入已补齐。
- [x] python -m pytest tests/integration/test_admin_voteables.py tests/integration/test_voteable_import.py -q；admin-ui 的 pnpm build；改动 Python 的 flake8 及 git diff --check。
- [x] 最后一轮只读审阅，记录实际证据与未验证范围，不为理论风险扩大验证。

## Review Focus

预览不得改变持久化；有错误不得部分落库；名称匹配保留旧关联；静态路由不被动态路由遮蔽；导出文件可以导入且页面旧预览不能被误用。

## 执行记录

- 新行为在实现前验证为9 failed、1 passed，失败均为静态导入路由尚未建立而被旧动态路由匹配为422；管理员鉴权检查原本已通过。
- `python -m pytest tests/integration/test_admin_voteables.py tests/integration/test_voteable_import.py -q`：37 passed（12.63s），2条已有弃用警告。
- `pnpm build`（admin-ui）：vue-tsc 和 Vite 通过，静态产物同步到 src/admin_ui。
- `python -m flake8 src/apps/admin/work_service.py src/apps/admin/schemas.py src/apps/admin/router.py`、`git diff --check`：通过。
- 通过临时 SQLite 的真实 HTTP/数据库读写验证预览、提交、错误不写及作品导出后重新导入；真实云端全库恢复、浏览器交互与 PostgreSQL 运行未验证。
- 独立只读审阅未发现阻塞性缺陷，已核对预览不写、错误整批拒绝、更新保留关联、路由顺序、JSON 导回及页面预览失效逻辑。
- 实现阶段未操作真实数据库、提交、推送或部署；用户随后要求本阶段提交，本次一并更新 BACKLOG 接手队列，提交状态以 Git 记录为准。
