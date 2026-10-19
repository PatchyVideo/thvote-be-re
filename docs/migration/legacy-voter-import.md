# 老 Mongo 用户导入测试库（runbook）

> 日期：2026-10-20
> 范围：`thvote_users/voters.bson` → PostgreSQL `user` + `user_identity` + `legacy_user_mapping`
> 决策：D1-A（恢复 bcrypt 兼容）、D2-B（新 UUID4）、D3-A（不导旧选票）、D4-A（按最后登录选优）、D5（测试账号仅测试库/坏邮箱忽略）、D6-B（不导日志）、D7-B（直写测试库）、D8-A（已有账号优先）

## 1. 变更内容

| 变更 | 位置 |
|---|---|
| `user.legacy_salt` 列（bcrypt 盐） | migration `0020` |
| `legacy_user_mapping` 表（旧 `_id` → 新 `user.id`） | migration `0020`（`0021` 把 `role` 放宽到 VARCHAR(32)） |
| Argon2 + bcrypt 双路径校验 | `src/common/security/password.py` |
| 登录/改密/注销三处接 `verify_any_password`，升级时清盐 | `src/apps/user/service.py` |
| 一次性导入器 | `scripts/import_legacy_voters.py` |
| 批次回滚 | `scripts/rollback_legacy_user_import.py` |
| 轻量备份 | `scripts/backup_user_tables.py` |

## 2. 数据口径（实测）

| 指标 | 数值 |
|---|---:|
| 原始文档 | 121,957 |
| 非法邮箱（3 个地址 × 2 条重复） | 6 条，整组跳过 |
| 去重后 winners | 80,053 |
| 合并掉的重复记录 | 41,898 |
| 与测试库已有账号冲突（手机号） | 3 → `conflict_existing` |
| 新建用户 | 80,050 |
| 新增 email / phone 身份 | 46,887 / 33,557（合计 80,444） |
| `legacy_user_mapping` 行 | 121,951 |
| 密码形态（去重后、过滤前） | bcrypt 40,153 / argon2i 1,755 / 无密码 38,148 |

> 测试账号：测试库加 `--include-test-accounts` 导入 `votetester1..5@touhou.ai`；
> 生产导入不要加。3 个非法邮箱按 D5 直接忽略。

## 3. 前置

- 测试库可写（RDS `test_db`，当前 alembic `0019`）。
- 本地 Redis 6380：`docker` 不可用时用 redislite 自带二进制：
  `redis-server --port 6380 --requirepass <env 里的密码> --save ''`。
- Python 依赖：`bcrypt>=4`（运行时）、`pymongo`（导入器，`scripts` extra）。
- 备份不需要 `pg_dump`：`scripts/backup_user_tables.py` 用 asyncpg 导 CSV。

## 4. 执行顺序

```bash
cd thvote-be-re

# 1) 只读预检（不写库）
python scripts/import_legacy_voters.py \
  --dump-dir ../thvote_users --include-test-accounts \
  --report-dir /tmp/thvote-import-preflight --preflight

# 2) 轻量备份
python scripts/backup_user_tables.py --out-dir /tmp/thvote-backup-$(date +%Y%m%d%H%M)

# 3) 迁移（写库，需确认）
alembic upgrade head

# 4) 正式导入（写库，需确认；batch-id 记下来）
python scripts/import_legacy_voters.py \
  --dump-dir ../thvote_users --include-test-accounts \
  --report-dir /tmp/thvote-import-live \
  --batch-id <uuid> --commit

# 5) 验收
#    votetester1@touhou.ai / wlrg6M43tpI6919i → 200 + session_token + vote_token
#    库里该用户 password_hash 以 $argon2id$ 开头、legacy_salt IS NULL
```

## 5. 报告文件

`summary.json`、`conflicts.csv`、`duplicates.csv`、`invalid_email.csv`、
`test_accounts.csv`、`merged_fields.csv`、`manual_review.csv`。
报告含 PII，只留本地，不上传 RDS/仓库。

## 6. 回滚

```bash
# 预检：只统计
python scripts/rollback_legacy_user_import.py --batch-id <uuid>

# 执行；若账号已有投票/日志/复核记录会拒绝，确需强删加 --force
python scripts/rollback_legacy_user_import.py --batch-id <uuid> --commit
```

删除顺序：`legacy_user_mapping`（本批）→ `user`（role=primary 的账号，级联身份）。
`conflict_existing` 指向的既有账号不会被删。

## 7. 已知边界

- `last_login_at` 按 D6-B 留空，首次登录后自动填充。
- `VOTE_YEAR=12` 是测试环境既有值，不是笔误；登录投票 token 只依赖投票窗口。
- 3 个非法邮箱账号不入库，也不占手机号/身份。
- 密码 >72 字节的 bcrypt 行可能校验失败（Python bcrypt 截断语义），会体现在支持工单。
- 旧选票（`submits_v1`）本次不导；将来若要导，用
  `legacy_object_id` 还原 `thvote-{year}-{id}` 即可关联。
