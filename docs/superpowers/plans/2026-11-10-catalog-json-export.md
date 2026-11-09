# 基础资料 JSON 导出实施计划

> 由当前执行者按 executing-plans 顺序实施；用户已明确要求写完计划直接开干，不再等待二次确认。

**Goal:** 在现有作品页、资源页下载完整且适配业务导入的 JSON 清单。

**Architecture:** 小型导出 service 只读查询 work/voteable；管理员路由返回 JSON 附件，前端复用 apiRaw 和现有下载方式。

**Tech Stack:** 现有 FastAPI、SQLAlchemy、Vue 3、TypeScript，无新依赖。

**Spec:** [已确认设计](../specs/2026-11-10-catalog-json-export-design.md)。

## 全局约束

- 在当前 feat/questionnaire-backend-source 延续开发，保留上一步资源导入及用户未提交文档；不另建工作区或自动 commit/push。
- 仅作品、角色、音乐业务事实；不接 candidate、不改表、不查写真实云端数据。
- 页面验证不执行浏览器点击或填表；使用现有构建和相关后端检查。

## Task 1：导出 service 与管理员附件接口

**Files:** 新增 src/apps/admin/catalog_export_service.py；修改 src/apps/admin/router.py、tests/integration/test_admin_voteables.py。

**Interfaces:** GET /api/v1/admin/export/catalog?category=work|character|music → UTF-8 JSON 数组附件。

- [x] 在已有测试中覆盖三类真实查询、未参选对象、空作品归属、无关联作品、资源字段、非法类别和管理员鉴权，确认新增路由前失败。
- [x] 实现只读导出、业务字段映射和完整清单；固定排序、保留数组/null，不带数据库 ID。
- [x] 用导出的角色/音乐清单调用现有业务导入，检查资料与作品关联一致。

## Task 2：下载按钮、文档与集中验证

**Files:** 新增 admin-ui/src/api/exportCatalog.ts；修改资源页、作品页、docs/api/voteable-api-contract.md、docs/CHANGELOG.md；构建同步 src/admin_ui 静态产物。

**Interfaces:** 前端 downloadCatalog(category) 调用 Task 1 接口，保存三个约定文件名。

- [x] 复用现有鉴权下载；资源页按当前类别导出，作品页导出全部作品，按钮显示下载中状态及错误提示。
- [x] 更新接口字段、完整导出范围、导入兼容边界与 changelog。
- [x] 集中运行 python -m pytest tests/integration/test_admin_voteables.py tests/integration/test_voteable_import.py -q，预期全部通过。
- [x] 在 admin-ui 执行 pnpm build，并检查改动 Python 的 flake8 和 git diff --check。
- [x] 自查本次实际 diff，记录结果与未验证范围；不因历史理论风险扩大实施。

## Review Focus

重点核对完整读取不误用分页/候选表、work 名称与类别映射、业务字段无遗漏、音乐专属字段边界、未登录下载受保护。

## 执行记录

当前分支包含上一步未提交资源导入，原位修改以保持依赖和用户现场。

- 新增导出检查在接口落地前 5 failed，均为路由尚未存在的 404；实现后集中执行两份相关文件，28 passed，2 条已有弃用警告。
- `python -m pytest tests/integration/test_admin_voteables.py tests/integration/test_voteable_import.py -q`：28 passed（8.97s）。
- `pnpm build`（admin-ui）：vue-tsc 与 Vite 通过；同步更新后端服务的已跟踪静态构建产物。
- `python -m flake8 src/apps/admin/catalog_export_service.py src/apps/admin/router.py src/apps/admin/voteable_import_service.py` 与 `git diff --check` 通过。
- 测试采用临时 SQLite 数据库，通过实际 ORM、HTTP 接口和业务导入验证三类清单及角色/音乐重新导入，不代表真实云端数据已归档。
- 独立只读审阅未发现阻塞性问题，已核对全量读取、作品关联、业务字段、音乐专属字段、管理员鉴权和下载路径。
- 无浏览器交互、真实数据库操作、提交、推送或部署。
