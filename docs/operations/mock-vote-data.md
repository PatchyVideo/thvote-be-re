# Mock 投票数据生成器使用手册

> 创建日期:2026-08-14
> 脚本:`scripts/generate_mock_votes.py`
> 适用环境:**仅测试环境**。生产库禁止执行(脚本运行前会打印目标库并要求确认)。

## 这是什么、为什么存在

result 模块(排名/趋势/高级搜索/问卷统计)需要**有一定规模、分布真实**的投票数据才能联调和演示;手动投票一次只能造一票,覆盖不了长尾、趋势曲线、高级搜索子集筛选这些场景。本脚本一条命令向测试库灌入几千个合成投票者的完整投票(角色/音乐/CP/问卷),并可随时一条命令清干净。

**看到测试机结果站上有几千票时不要慌**——那不是真人数据,是本脚本灌的,识别与清理方式见下。

## 数据形态与安全约定

| 约定 | 说明 |
|---|---|
| **`mock-` 前缀** | 所有合成投票的 `vote_id` 形如 `mock-00042`。这是与真人数据的**唯一区分标志**,查库一眼可辨:`SELECT ... WHERE vote_id LIKE 'mock-%'` |
| **只动自己的数据** | 每次运行先删旧 `mock-%` 行再重灌(幂等,可反复跑);清理也只删该前缀。**无前缀的真人投票绝不触碰**,有集成测试锁死这一点 |
| **可复现** | 同 `--seed`(默认 42)生成完全相同的数据集 |
| **影响的表** | `raw_character_submit` / `raw_music_submit` / `raw_cp_submit` / `paper_answer`(写入);`question_def` / `option_def` 的 **code 列**(只填空值,见下) |

**分布设计**(为什么榜单看起来像真的):投票者分 3 个偏好簇,簇内按 Zipf 分布选候选 → 头部角色几百票、长尾零星;不同簇偏好不同 → 高级搜索按角色/曲目筛出的子集榜与全量榜明显不同(这正是演示高级搜索的价值);提交时间铺满投票窗口并偏向晚间 → 趋势曲线有形状;性别题按 55/45 采样 → 性别维度统计有数。

## 问卷测试 code 回填(与 B-054 的关系)

测试库的问卷是占位题且语义 code 未回填(BACKLOG B-054,等出题方),code 为空时性别分段、问卷统计、高级搜索 `q` 原子全部出不了数。本脚本顺带做最小回填:

- 第一道 code 为空的单选题 → 填 Nacos 配置的性别题 code(默认 `11011`,前两个选项 `1101101`/`1101102`);
- 其余空 code 的题/选项 → 填 `9` 开头的顺延测试 code;
- **已有 code 的行绝不覆盖**。B-054 真题定稿后通过 admin 整树导入重建结构即可,测试 code 不构成障碍。

## 怎么跑(测试机后端容器内)

```bash
# 1. SSH 到测试机后找到后端容器名(通常是 thvote-be 或 compose 服务名 backend)
docker ps --format '{{.Names}}' | grep -i -E 'backend|thvote'

# 2. 灌数据(默认 4000 人,--force 跳过交互确认;容器内配置/DB 连接现成)
docker exec <backend容器> python scripts/generate_mock_votes.py --voters 4000 --force

# 3. 触发计票——不跑这步结果站不会变!
curl -X POST 'http://127.0.0.1:18000/api/v1/admin/compute-results' \
     -H 'X-Admin-Secret: <ADMIN_SECRET>'   # secret 在 Nacos thvote_be 配置里

# 4. 验证:结果站 :8084 应能看到几千票的榜单;或直接查 GraphQL:
curl -s -X POST http://127.0.0.1:18000/graphql -H 'Content-Type: application/json' \
     -d '{"query":"query { queryGlobalStats { numVote numMale numFemale } }"}'
```

**清理(恢复原状)**:

```bash
docker exec <backend容器> python scripts/generate_mock_votes.py --wipe-only --force
# 之后同样要再触发一次 compute,榜单才会回到清理后的状态
```

**参数速查**:`--voters N`(规模)| `--seed N`(换一套数据)| `--vote-year Y`(默认取 settings)| `--wipe-only`(只清)| `--force`(跳过确认,非交互场景必需)。

## 常见问题

- **灌完结果站没变化?** 没跑第 3 步 compute。计票是显式触发的,不会自动跟着写库跑。
- **高级搜索的 `q11011=1101101` 筛不出东西?** 确认灌数据时问卷结构已存在(脚本会自动回填 code);若问卷结构后来被重建过,重跑一次脚本即可。
- **想要不同的榜单形状?** 换 `--seed`。
- **会影响反作弊/监控数据吗?** mock 行的 IP 是保留测试段 `203.0.113.*`、UA 是 `mock-data-generator`,在 admin 监控台里一眼可辨,不会与真人信号混淆。
- **CI 会跑这个脚本吗?** 不会。脚本只能手动执行;它的单测/集成测试(`tests/unit/test_generate_mock_votes.py`、`tests/integration/test_generate_mock_votes_db.py`)在 CI 正常跑。
