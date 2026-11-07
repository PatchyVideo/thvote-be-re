# CI/CD 流水线说明

> 创建：2026-04-27。最后核对：2026-11-08，按当前 workflow 源码更新。
> 本文说明代码中的通道与条件；没有重新验证生产／测试机器、Secrets、Nacos 或实际部署状态，不构成执行发布的授权。

## 当前流水线

仓库使用 [deploy-test.yml](../../.github/workflows/deploy-test.yml) 一个 workflow 管理后端检查、构建和部署。它已有独立 `deploy-prod` job；不需要另有 `deploy-prod.yml` 才算具备生产通道。B-028 原“没有 prod 路径”已结项，见 [BACKLOG 核对记录](../migration/backlog-audit-2026-11-08.md)。

| 触发 | 源码行为 |
|---|---|
| push 到 main／zfq_dev，命中 paths | lint → test → build-backend → deploy-test |
| 针对上述分支的 PR | lint、test；build-backend 限 push／workflow_dispatch，不发布 |
| workflow_dispatch | 可用 skip_tests 跳过 test；lint 成功后构建并部署测试环境 |
| workflow_dispatch 且 deploy_prod=true | build-backend 与 deploy-test 成功后再执行 deploy-prod，复用同一镜像 digest |

`zfq_dev` 属合作者分支，仍遵守工作区只读约定。本文记录触发器，不授权修改或推送该分支。

## 检查、镜像与部署职责

| Job | 当前代码 |
|---|---|
| lint | Python 3.12；安装 flake8／black／isort／mypy，实际只执行 `flake8 src/ --max-line-length=88`，为硬失败。未运行 mypy；不再描述为 `\|\| true` 软门禁 |
| test | Postgres 15 与 Redis 7 服务；应用 `alembic upgrade head` 并查看 current 后，运行带覆盖率的 pytest。未设置固定 fail_under=80 门禁 |
| build-backend | 构建后端 production 镜像，输出 tag 与 digest；main 使用 prod 标签，其他分支使用 test 标签。标签本身不触发生产 job |
| deploy-test | 使用测试目标和 Nacos 配置；先执行迁移，再重建 backend。实际环境及状态本轮未核验 |
| deploy-prod | 仅手动 deploy_prod=true；使用独立 PROD_SERVER_* 与 PROD_SERVER_DIR，默认目录 `/opt/thvote/prod`，同样先迁移后重建；不能与测试目标混称 |
| notify | 当前依赖 deploy-test 的通知；不据此推断生产发布完成 |

push 的路径过滤包含 `src/**`、`alembic/**`、`pyproject.toml`、`Dockerfile`、`scripts/**`、`docker/**` 与 workflow 本身；仅文档变化不触发 push 发布路径。

## 配置与操作边界

- Nacos 配置由既有 GitHub Secrets／Variables 和部署配置交付；workflow 使用 dataId `thvote_be`。不要照早期文档中的 `thvote-be` 示例直接覆盖实际配置。
- 生产与测试使用各自 namespace／部署目录；具体值以受控配置为准，不在文档中保存明文认证值。
- 后端改配置仍需按现有启动／重建流程生效；实际部署必须遵循项目 AGENTS 的服务器约束及用户当前授权，不据本页自动执行。
- 本 workflow 只负责后端。Touhou-Vote 前端由独立仓库流水线处理，不能用后端状态推断前端已发布。

## 历史跟踪项的处理

- B-027 旧 flake8 软门禁已不存在；B-028 生产通道已有代码。
- B-020 事实是“安装 mypy 但未执行”；是否加入门禁由实际需求决定。
- B-026 更细的 model-diff／alembic check 仍为治理建议，不能把缺少可选检查描述成当前迁移完全无检查。
- B-031 仍有配置格式兼容解析；当前配置写法未核验，不直接删除兼容。
- 旧 B-025／029／030 等过程记录保留在历史提交和 BACKLOG 归档，不从过期 checklist 重新安排工作。
- 2026-05-12 删除过独立的 deploy-prod.yml／deploy.yml／pylint.yml，属于历史文件收敛；2026-10-29 在现有 workflow 内加入生产 job，已取代“需要恢复旧 prod 文件”的建议。
