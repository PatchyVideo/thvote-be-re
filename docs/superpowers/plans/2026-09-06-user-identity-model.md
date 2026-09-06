# 用户身份模型归一化 实施计划

> **状态**:已实施(2026-09-06)。
> Spec:[`../specs/2026-09-06-user-identity-model-design.md`](../specs/2026-09-06-user-identity-model-design.md)。本计划只列任务切分与关键决定,细节以 spec 为准。

**目标**:`user` 只留账号,`user_identity` 一行一个认证来源;登录/绑定/改绑/注销收敛到一条按 `(provider, subject)` 查身份的路径;迁移 0018,无兼容期。

**测试命令**:`python -m pytest tests/ -q`(conda 的 python 3.13;PATH 上的 `pytest` 是 3.10 的,不能用)。lint:`flake8 src/ --max-line-length=88`。

## 任务

1. **模型 + identity 规则**
   - `src/db_model/user_identity.py` 新建;`src/db_model/user.py` 删七列与 CHECK,加 `identities`(selectin);`db_model/__init__.py` 导出。
   - `src/apps/user/identity.py`:`IdentityProvider`、`normalize_subject`、`vote_eligible_providers()`(读 `settings.vote_eligible_providers`,默认 `["email","phone"]`)。config 加字段。
   - 单测:normalize 规则、资格集合解析。
2. **DAO**
   - `UserIdentityDAO`(find_user / get / add / delete / delete_all_for_user / touch_last_login);`UserDAO` 删四个按列查找,`search_users` join。
   - 测试 helper `tests/helpers/users.py::make_user(session, *, email=None, phone=None, qq=None, thbwiki=None, password=None, removed=False)`,所有直接构造 `User(email=...)` 的测试改用它。
3. **Service 收敛**
   - `src/apps/user/identity_service.py`:`IdentityBinder`(`_bind_identity` 语义)+ 登录注册的 `_login_by_identity`;`UserService` 变薄。
   - 删 legacy 密码路径(`password.py`、`security/__init__.py`、`utils/security.py`)。
   - `voter_fe_from_user`、`_maybe_sign_vote_token`、`remove_voter`、`_merge_sso_session`(冲突跳过)按 spec §五。
   - 集成测试:spec §八 清单;重写 `test_sso_flows`、`test_update_and_remove`、`test_vote_token_and_me`(删 bcrypt 用例)、`test_graphql_login`、`test_voter_fe_serialization`。
4. **管理端 + 同步 + 脚本**
   - admin `_user_to_item` 从身份取;`search_users` 结果不变。
   - 删 `map_voter` 与 voters 同步项、`_CONFLICT_COLS["user"]`;`scripts/bson_to_sql.py`、`scripts/import_mongo_dump.py` 去掉 voters 注册;`test_sync_mapping`/`test_sync_service` 的 voters 用例改用 raw_character 或删除。
5. **迁移 0018** + PG 专属唯一约束测试(从 `DATABASE_URL` 自建 engine,非 PG skip)。
6. **文档**:`docs/migration/user-manager.md` §一、CHANGELOG、BACKLOG(关 B-008/B-011/B-022/B-024)、spec 与本计划状态、`docs/README.md`。

提交拆分:`refactor:`(任务 1-5 代码)、`test:`、`docs:`;若任务 3 改动过大,任务 1-2 单独一个 `refactor:` 先提交。
