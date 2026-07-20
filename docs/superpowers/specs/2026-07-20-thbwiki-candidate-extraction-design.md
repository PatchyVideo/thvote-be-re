# THBWiki 角色候选数据抽取工具 —— 设计文档

- 日期：2026-07-20
- 状态：待实现（第一轮：纯抽取，不接 diff/写库）
- 关联：`docs/superpowers/specs/2026-06-08-candidate-management-design.md`（candidate 管理后台设计，定义了 `candidate_character` 的字段与导入契约）

## 1. 背景与问题

`candidate_character` 表（后端）和 `Touhou-Vote/packages/shared/data/character.ts` 的 `characterList`（前端）都是人工维护的"候选角色清单"，每年办投票前都要手动核对 THBWiki 上的角色信息，容易漏、容易错，且两边各维护一份、互不同步。

目标：做一个实验性、可反复运行的工具，从 THBWiki 抽取角色结构化信息，作为未来生成/核对候选清单的数据源。

**本轮范围明确收窄**：
- 只做角色（人物），不做作品/音乐目录（作品目录留到下一轮迭代）。
- 只做「抓取 → 清洗 → 抽取 → 落盘结构化数据」，**不**对接 `candidate_character` 表或 `character.ts` 做 diff、**不**自动写入任何正式数据源。diff/审核环节是明确的下一轮工作，本文档不展开设计。

## 2. 已有基础设施（复用而非重造）

`~/BFV/data-curation` 项目已经是一个专门针对 thbwiki.cc 的通用爬虫流水线（任务队列 + AI 审阅候选链接决定要不要跟进 + page_id 优先的去重存储 + 页面链接图谱），种子页面里已包含"官方角色列表/纯文字列表"，2026-03-20 完整跑过一轮，产出 8730 个页面的清洗后 Markdown（`pageid_store_v1/`）。

但那个项目定位是"THB 全量爬取、构建 agent 知识库"，偏重、一次性跑，用 BFS 式链接发现 + AI 审阅决定要不要继续抓某个链接。我们的需求集合是确定的、小的（列表页 + 它直接链接的角色详情页，量级几百个页面），不需要那套发现机制。

**复用的部分**：
- HTML→Markdown 清洗规则（`CONTENT_SELECTORS`、`FILTER_CLASSES`、`KEEP_TAGS` 的思路），搬一份精简版到本模块，不做跨仓库运行时依赖。
- LLM 调用方式（同一个 dashscope/qwen 兼容 OpenAI 接口的调用模式）。

**不复用的部分**：任务队列/AI 审阅链接 keep-skip 环节、page_id 去重存储机制——这些是为"发现范围未知的全站抓取"设计的，我们的抓取范围是确定的，用不上。

## 3. 抓取范围

- 种子页：`https://thbwiki.cc/官方角色列表/纯文字列表`
- 从种子页解析出的每一个角色详情页链接（一跳，不递归）
- 不做链接发现，不追踪详情页内的其他链接

样本验证（已人工核对）：
- 列表页结构：按"旧作/新作"分节 → 按具体作品（如"东方红魔乡"）分小节 → 每行 `- [中文名](链接 "标题")／日文名／罗马音`。
- 详情页结构：开头可能有消歧义提示（需要识别、避免误收消歧义变体页），随后是"角色信息"下的"基本信息" markdown 表格（人物名/日文名/英文名/种族/职业/能力），再往下是自由文本的"角色介绍"。

## 4. 流水线结构

```
[抓取层 fetch] → [清洗层 clean] → [抽取层 extract] → [落盘 output]
```

### 4.1 抓取层

- 下载列表页 + 全部详情页原始 HTML。
- 幂等：维护 `fetch_manifest.json`（`url -> {content_hash, fetched_at, html_path}`）。重跑时先取列表页判断内容 hash 是否变化：
  - 未变 → 复用上次的角色链接集合，跳过重新拉取列表页。
  - 单个详情页只有 hash 变化才重新走清洗+抽取，否则复用上次抽取结果（省 LLM 调用）。
- 缓存目录（原始 HTML、manifest）不进 git。

### 4.2 清洗层

- 复用 `~/BFV/data-curation` 的 HTML→Markdown 清洗规则，转成纯净 Markdown 正文。

### 4.3 抽取层

**规则抽取（主力，无 LLM 依赖）**：
- 解析列表页分组结构 → 得到 `name`、`origname`（日文名）、罗马音候选、所属 `work`（列表页分节路径，如"新作/东方红魔乡"）。
- 解析详情页"基本信息"表格 → 得到种族/职业等原始文本（`type_raw`）。
- 识别消歧义提示（"关于其他含义，详见……"）→ 只取正文角色本身，不误收消歧义变体条目。

**LLM 兜底（仅用于规则抽不干净的部分）**：
- 从详情页正文/表格备注中提取散落的别名（假名标注、罗马音变体、俗称）→ `altnames`。
- 将 `type_raw`（如"人类 / 巫女"）归一化到受控词表 → `type`。受控词表本轮先用一份小的初始清单（人类/妖怪/神灵/幽灵/其他等大类，基于种族而非职业），实现时从已抓到的 `type_raw` 样本里人工归纳补全，不预先假设完备。
- 每次 LLM 输出都必须附带来源原文片段，禁止无来源凭空生成字段值。
- LLM 调用失败/超时：该字段留空，标记来源为 `llm_failed`，不重试到阻塞整体流程。

`date`（首次登场年月日）本轮**不做**——没有现成的"作品→发售日期"映射（`work.ts` 只有 kind 没日期），强行做会拉出一个新的子项目，超出本轮范围，先留空。

### 4.4 输出

每个角色一条记录，结构大致如下：

```json
{
  "name": "博丽灵梦",
  "origname": "博麗　霊夢",
  "altnames": ["Hakurei Reimu", "はくれい れいむ"],
  "type": "human",
  "type_raw": "人类 / 巫女",
  "work": ["东方灵异传", "东方红魔乡"],
  "source_url": "https://thbwiki.cc/博丽灵梦",
  "extracted_at": "2026-07-20T00:00:00Z",
  "extraction_method": {"work": "rule", "type": "llm_assisted", "altnames": "llm_assisted"},
  "partial_extraction": false
}
```

- 列表页收录的角色全部抽出，不做"是不是候选人"的取舍——取舍是下一轮 diff 阶段的事。
- 详情页结构不符合预期（无"基本信息"表格等特殊页面）：降级为仅用列表页信息，标记 `partial_extraction: true`。
- 单页抓取失败（超时/404）：计入结果里的 `failed` 列表（URL + 原因），不中断整体流程。
- 落盘两份：完整 JSON 数组 + 人类可读的 Markdown 汇总（按作品分组的表格，便于肉眼扫抽取质量）。
- 输出目录：`docs/scraper/candidate-extraction/`，明确标注为实验性产出、非正式数据源，不直接消费于生产代码。

## 5. 代码落地位置

- `thvote-be-re/src/apps/scraper/candidate_sync/`：与现有 `src/apps/scraper/sites/thbwiki.py`（社媒统计爬虫）同域下的姊妹能力。内部按职责拆分：
  - `fetch.py`：抓取 + manifest 缓存
  - `clean.py`：HTML→Markdown
  - `extract_rules.py`：规则抽取
  - `extract_llm.py`：LLM 兜底抽取
  - `output.py`：落盘 JSON/Markdown
- `thvote-be-re/scripts/`：一个薄的 CLI 入口脚本，串联以上模块，供手动/定期触发。

## 6. 明确不做的事（本轮范围外）

- 不对接 `candidate_character` 表或 `character.ts`，不做 diff，不做任何写入。
- 不做作品/音乐目录抽取。
- 不做 `date`（首次登场日期）抽取。
- 不做开放式链接发现/BFS 抓取。
- 不复用 `~/BFV/data-curation` 的任务队列/page_id 存储机制。

## 7. 测试计划

- 规则抽取器：用固定的样本 Markdown（如本文档验证过的"博丽灵梦"详情页、"纯文字列表"片段）做单元测试，覆盖正常情况、消歧义页、无信息表格的降级情况。
- LLM 兜底：mock LLM 响应做单元测试，覆盖正常提取、格式异常、超时/失败三种情况，确认失败不阻塞整体流程。
- 端到端：跑一次真实小范围抓取（如只抓"主角二人组"+"东方红魔乡"分节的角色），人工核对输出 JSON/Markdown 的准确性。
