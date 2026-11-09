# 测试数据清理前核查与 raw_paper 退出准备

日期：2026-11-10。用户要求先看云端模拟提交和旧统计，准备清理，随后系统性退出 raw_paper。
本记录包含最初只读调查和随后用户明确授权的清理；已删除24行新版答卷及47个旧统计键，未执行删表、迁移、重启、部署或统计重算。完整结果见文末。

## Actions 只读实测结果

用户提出改用 Actions 后，已复用 TEST_SERVER_* Secrets 及 test Environment，
在独立临时分支覆盖部署 workflow 为单个手动 SSH 只读任务。没有构建、迁移、重启、计票或删除步骤，未改 main/feat/合作者分支。

- [运行记录 42661928457](https://github.com/PatchyVideo/thvote-be-re/actions/runs/42661928457)：success。
- 远端任务提交 `f819b0f44c5aeb6a8cfd095fc492791b7d1eba93`，基于 origin/main `d7cf8cb`；临时分支 `codex/test-data-readonly-20261109-170956`。
- 核查完成后已删除本次临时分支，Actions 运行记录保留；当前本地功能分支和共享分支均未改动。
- 实测时间：2026-11-10 01:10:14 北京时间（UTC 2026-11-09 17:10:14）。
- 数据库 `test_db`，迁移 `0022`，当前配置 vote_year=12；PostgreSQL 事务确认 transaction_read_only=on。
- 通过运行中 thvote-backend 的应用配置连接，未读取/打印原始 .env、数据库凭据或个人记录。

以下为清理前的只读快照，后续已授权执行的变化见文末。

| 原始提交/结果表 | 总行数 | mock- 行数 | 结论 |
|---|---:|---:|---|
| raw_character | 0 | 0 | 无需再删模拟角色票 |
| raw_music | 0 | 0 | 无需再删模拟音乐票 |
| raw_cp | 0 | 0 | 无需再删模拟组合票 |
| paper_answer | 24 | 0 | 1位非mock投票者，第12届，均创建于2026-10-30 02:32:15 UTC；是否删除须单独确认 |
| raw_paper | 0 | 0 | 旧表为空，当前没有入/出外键依赖；代码入口尚未退出 |
| raw_dojin / raw_work | 0 / 0 | 0 / 0 | 无存量 |
| character / music / cp / questionnaire | 均0 | 不适用 | 旧路径表为空 |
| final_ranking | 0 | 不适用 | 无持久化历史结果行 |

| Redis 范围 | 键数 | 内容分组 |
|---|---:|---|
| result:12:* | 37 | paper 26；chars/musics/cps/covote各2；completion_rates/global_stats/snapshot_version各1 |
| result:2026:* | 10 | chars/musics/cps/covote各2；completion_rates/global_stats各1 |
| 合计 | 47 | 没有 adv 结果键，两个年份均无 compute_lock；monitor 缓存键为0 |

第12届 global_stats 与公开接口一致，仍显示3984参与者；2026的旧快照显示2参与者。
这些 global_stats 均无过期时间，且均无 timeline；第12届 snapshot_version=1789485920。
当前原始角色/音乐/组合票已空，因此这些快照是需要处理的旧结果，不能作为当前原始提交量。

明确保留的基础数据实测：work=77，voteable_character=250，voteable_music=617；
第12届 candidate_character=250、candidate_music=617；问卷定义8、题组24、题32、选项40；user=8、user_identity=8、legacy_user_mapping=5。
这也证明当前库的问卷定义仍是8份，不能假定已经配置成业务要求的A/B/C/D四份。

## 本机访问情况（改用 Actions 前）

- 测试服务 `http://154.37.215.62:18000/health` 返回 status=ok、db_status=ok、vote_year=12。
- 公开 GraphQL 第12届统计读取成功，结果如下；它们来自结果快照，不是 PostgreSQL 原始行计数，也不能据此区分模拟/手工数据。
- SSH 测试机 root 登录失败（publickey/password 未授权），当前会话未注入数据库、Redis 或管理员连接配置，本机无 thvote 运行容器可复用。
- 已询问可用 SSH 别名/账户或只读数据库入口；未读取 .env、密钥或原始认证内容。
- 当时无法直接查询原始计数，随后已通过 Actions 完成，结果见文首。备份和删除仍未执行；历史4000模拟投票者记录不能作为本次删除数量。

| 公开结果项 | 清理前快照值 |
|---|---:|
| numVote | 3984 |
| numChar | 3407 |
| numMusic | 3231 |
| numCp | 1626 |
| numDoujin | 0 |
| numMale / numFemale | 1502 / 1311 |
| 旧完成率 questionnaire.numComplete | 2813 |

## 本次核查口径（已通过 Actions 执行）

1. 核对当前数据库名称、迁移版本，PostgreSQL 查询使用只读事务；只报告聚合数量，不读取个人联系方式、凭证或作答正文。
2. 对 raw_character/raw_music/raw_cp/paper_answer 分别统计总行数、mock- 行数及去重投票者、非mock数量、最早/最晚时间；paper_answer 再按 vote_year 分组。
3. raw_paper、raw_dojin、raw_work 及旧 character/music/cp/questionnaire 表分别检查存量和引用，不能因为旧或测试就自动归入同一删除范围。
4. final_ranking 按届次/类别统计，判断是否含导入的历史正式结果；它不等于 Redis 当前测试快照，不自动删除。
5. 记录 work、voteable_character/music、candidate_character/music、问卷四层定义及用户相关表的聚合数量，作为明确保留的数据范围。
6. Redis 仅 SCAN/读取相关元信息：按届次统计 result:* 主榜、paper、adv、timeline、snapshot_version 键；读取现有生成时间及 compute_lock 存在状态。不读取验证码/会话值，不执行全库清空。

## 根据实测收敛的清理范围（清理前方案）

- 四类提交中的 mock- 均已为0，不再运行无意义的 mock 清理。24行非mock新版答卷单列供用户决定；现有 wipe_mock_rows 不限制届次，也不会删除这24行。
- raw_paper 已为空，不需要清行；删表仍属于系统性退出的一部分，先移除活跃代码依赖，再安排 schema 迁移。
- Redis 当前待清范围为 result:12:* 的37键与 result:2026:* 的10键，执行前重新核对计数并备份，不使用 FLUSHDB/FLUSHALL。重新计票会覆盖当前题目结果，但不会删除已经消失的旧题目键。
- 保留账号/身份、角色/音乐/作品、候选配置和问卷定义；不执行“整库重置”。

## 备份与恢复准备

执行删除前先导出实际目标库的三份基础资料 JSON，再将待删提交及确认的历史结果做可恢复数据库备份，记录表/条件/行数。
业务 JSON 不包含数据库 ID，不能替代原始提交回滚所需的数据库备份。Redis 如清理旧结果，需先保留对应键值/TTL或明确按原始记录重建的办法。
恢复提交应使用保留 ID 的数据库备份；结果按需要恢复旧快照或重新计票。该准备阶段尚无备份，后续实际文件见文末；没有执行恢复演练。

## raw_paper 源码退出检查表

- 旧 GraphQL submitPaperVote/getSubmitPaperVote，REST 旧问卷提交/回填，以及 submit service/DAO/schema。
- /user-token-status 内旧 papers_json 回填与旧 papers 状态；登录有效性校验继续保留。
- 管理台概览、CSV 导出、monitor 的 paper 类别、账号详情及提示文案。
- Mongo 同步默认集合、runner mapper、历史导入/转换/回滚脚本；不能让同步再灌回旧数据。
- 前端残留旧问卷请求和类型，单独核对真实调用；不因为删除后端接口就让残留入口失效。
- ORM 导出、迁移及相关测试/文档；旧表删除须先退出活跃读写，再按实际数据库依赖安排。
- 新版答卷管理采用 paper_answer；批次作废及其门禁、统计、趋势口径仍需独立明确，不能用删旧系统代替实现。

## 用户授权及客户端影响

用户随后明确授权将24行非mock新版答卷与47个旧统计键全部清除。范围不包含账号、基础资料、候选或问卷定义；raw_paper 已空，本次不删表。

当前前端源码 restorePaperV2 在后端答案为空时保留 localStorage 中的 questionnaireDataLocalV2。
完成标记和进入投票页的预判基于本地草稿，因此删除后可能暂时显示已填完，而服务端认为没有保存答案。
这不改变账号/登录凭据，也不会自动写回答案；用户重新提交后才重新形成服务器记录。
对这次测试环境重置，建议测试人员退出再登录一次；现有 deleteUserData 会清理问卷本地草稿。
不自动将“后端无答案”改成“删除本地草稿”，因为正常未提交草稿也会遇到同一情况。
清空结果键后，结果接口会处于未计票状态，直到之后明确触发新一轮计票。

已准备一次性 Actions 清理任务：先确认目标、原始行数与键数，再向现有持久化 logs 挂载内写入0700目录/0600备份文件，校验后删除目标答卷ID及备份过的结果键。
备份包含完整原始答卷行、Redis DUMP及PTTL，恢复时可按原ID插回答卷并使用Redis RESTORE恢复键；不通过业务导入恢复原始提交。
任务不重启、部署、迁移或重新计票，实际执行结果如下。

## 授权清理执行结果

- 用户授权：24行非mock新版答卷及47个旧统计键均可删除；基础资料、账号、候选、问卷定义保留。
- 首次 [42666175457](https://github.com/PatchyVideo/thvote-be-re/actions/runs/42666175457) 在备份目录 mkdir 时因运行用户无父目录写权限退出；数据库删除0、Redis删除0。
- 修正仅为 root 创建本次唯一0700目录并将其交给容器运行用户；不改变已有日志目录权限，应用配置和业务代码均未部署。
- 再次 [42666434886](https://github.com/PatchyVideo/thvote-be-re/actions/runs/42666434886) success，远端临时任务提交 `574ac2f7f788d5491555b5094dcb1b83dbfb96f8`。
- 完成后已删除本次临时清理分支，保留两次运行日志；当前开发分支、main及合作者分支未更改。
- 核查/清理时间：2026-11-10 01:37:40 北京时间（UTC 2026-11-09 17:37:40）。目标 test_db，配置届次12。
- 删除 paper_answer 中备份过的24个主键对应的第12届答案；清理后该表0行。
- 删除备份过的47个结果键；复查 result:12:* 与 result:2026:* 均0。
- 保留表逐项计数与清理前相同：work77、角色250、音乐617、候选250/617、定义8/24/32/40、user8、identity8、mapping5。
- 公网 /health 仍为 status=ok/db_status=ok/vote_year=12；queryGlobalStats(voteYear:12) 返回 RESULT_NOT_COMPUTED，未重新计票。

私有备份保存在宿主机 `/opt/thvote/test/logs/test-data-cleanup-20261109-173314/`，通过现有 /app/logs bind mount 持久化，目录0700、文件0600：

| 文件 | 大小 | SHA-256 |
|---|---:|---|
| paper_answer.json | 7300字节 | df0976ef3eb3d88bee8c954bcd313ea96f30e5f1146c34dff4c53fac18d190ca |
| redis-results.json | 1108960字节 | 208a6e88b4fa8aebc1252b7b504bd82b2a8613fd27d507e48216a7605f3287c6 |

同目录 manifest-before.json/manifest-after.json 记录范围与结果。备份包含原始答卷及Redis DUMP/PTTL，未输出其正文，也未复制到Git仓库。
需要撤销时，由有权访问该私有目录的操作者按原ID/字段恢复答卷、按DUMP/PTTL执行Redis RESTORE；后续若已有新数据，先核对冲突再恢复，不直接覆盖。
浏览器本地草稿未被服务器清理，测试人员应退出重登清除旧草稿。没有改动前端缓存协议、会话或账号状态字段。
