# 候选项管理增强（导入/编辑/详情 + 白色主题）— 设计稿

> 创建日期：2026-06-08
> 最后更新：2026-06-08

## 一、背景与目标

管理端「候选项」Tab 当前只能**查看 + 删除**。运营需要的批量**导入**(`POST /admin/import-candidates`)只有 REST API、Web UI 上没有入口；单条**编辑**完全缺失。同时现有管理端是深色主题,本次一并改为白色主题。

本次交付:
1. **导入 UI** —— 支持 CSV / JSON,粘贴文本或上传文件,带 dry-run 预览确认
2. **单条编辑** —— 点行打开编辑弹窗(= 详情页),全字段可编辑,含删除
3. **列表页完善** —— 加导入按钮、每行编辑按钮
4. **白色主题** —— 整个管理端由深色改为白色,弹窗统一 460px

## 二、关键设计决策(brainstorm 结论)

| 决策 | 选定 |
|---|---|
| 交互模型 | **模态弹窗式**:列表为主界面,导入/编辑都是浮层弹窗 |
| 导入流程 | **带 dry-run 预览**:解析+校验 → 预览(有效/错误行)→ 确认导入 |
| 解析位置 | **后端**(Python `csv.DictReader` / `json.loads`),前端零解析逻辑 |
| 校验位置 | **后端权威**:必填、insertSelective、丢弃未知列都在后端 |
| 字段集合 | **从模型列推导**,非硬编码;前端经 schema 端点动态渲染 |
| 必填判定 | 列 `nullable=False 且 server_default is None` → 必填(当前仅 `name`) |
| 空值语义 | **insertSelective**:空/缺列 → 不写该字段 → 落库用 `server_default` |
| 编辑 name | **可改**,改后与同年份其它行冲突则 `409` |
| 主题 | **整个管理端**改白色;弹窗统一 460px |

## 三、字段集合(从表结构推导,非硬编码)

排除自增主键 `id`(忽略)和 `vote_year`(UI 选)。必填 = `nullable=False 且无 server_default`。

**character** (`candidate_character`):
| 列 | 必填 | 空值落库 |
|---|---|---|
| `name` | ✅ | —— |
| `name_jp` | 选填 | `""` |
| `origin` | 选填 | `""` |
| `type` | 选填 | `""` |
| `first_appearance` | 选填 | `NULL` |

**music** (`candidate_music`):
| 列 | 必填 | 空值落库 |
|---|---|---|
| `name` | ✅ | —— |
| `name_jp` | 选填 | `""` |
| `type` | 选填 | `""` |
| `first_appearance` | 选填 | `NULL` |
| `album` | 选填 | `NULL` |

> 以后表加列,必填/选填自动跟着变,无需改前后端代码。

## 四、导入数据流(dry-run 预览)

```
前端:选 类别+年份 → 粘贴文本/上传文件 → 拿到原始文本 + 格式(auto/csv/json)
  → POST /admin/candidates/import { vote_year, category, format, content, dry_run:true }
  → 后端 解析 + 校验 → { valid:[...], rejected:[{line,reason}], valid_count }
  → 前端渲染预览表(valid 前若干行 + 错误行摘要)
  → 用户「确认导入」→ 同端点 dry_run:false → 解析+校验+upsert → { imported, rejected }
```

### 解析规则
- `format:"auto"` → 文本 `strip()` 后以 `[` 或 `{` 开头按 JSON,否则 CSV
- CSV:`csv.DictReader`(原生 quote-aware,处理含逗号/引号字段);表头必须等于列名
- JSON:`json.loads`,必须是对象数组(`list[dict]`)

### 校验规则(逐条)
1. 丢弃未知列(character 填了 `album` → 忽略)
2. insertSelective:值为空串或缺列 → 该字段不写入
3. 必填:`name` 缺失或空 → 进 `rejected`,记 `{line, reason:"缺少 name"}`(行号:CSV 为数据行号含表头偏移;JSON 为数组下标)
4. 通过的进 `valid`

### upsert(复用现有 `upsert_candidates`)
现有行为是**按 `(vote_year, name)` 查找:存在则更新该行字段,不存在则插入**。即重复导入同名候选会**覆盖**其元数据(name_jp/type/...),不会产生重复行。幂等(同输入多次结果一致)。

> 注意这与「DO NOTHING」不同:再次导入会用新值覆盖旧值。若运营预期「已存在就跳过不改」,需在 import 时加 `skip_existing` 选项 —— 本期默认覆盖,不加该选项(YAGNI)。

## 五、后端端点

全部需 `X-Admin-Secret`。

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/admin/candidates/fields?category=` | schema 自省,返回字段 + 必填标记 |
| `POST` | `/admin/candidates/import` | 解析+校验+导入,`dry_run` 控制预览/提交 |
| `PUT` | `/admin/candidates/{id}` | 单条编辑,后端校验 |
| `GET` | `/admin/candidates` | 列表(现有,不改) |
| `DELETE` | `/admin/candidates/{id}` | 删除(现有,不改) |
| `POST` | `/admin/import-candidates` | 结构化 items 导入(现有,保留;与新端点共用 service 核心) |

### 5.1 `GET /admin/candidates/fields`
```json
{ "category": "character",
  "fields": [
    {"name": "name", "required": true},
    {"name": "name_jp", "required": false},
    {"name": "origin", "required": false},
    {"name": "type", "required": false},
    {"name": "first_appearance", "required": false}
  ]}
```

### 5.2 `POST /admin/candidates/import`
请求:
```json
{ "vote_year": 2026, "category": "character",
  "format": "auto", "content": "<原始 CSV 或 JSON 文本>", "dry_run": true }
```
响应:
```json
{ "ok": true,
  "valid_count": 40,
  "imported": 0,
  "valid": [ {"name":"博丽灵梦","name_jp":"博麗霊夢","type":"human","origin":"红魔乡","first_appearance":"1996"}, ... ],
  "rejected": [ {"line": 7, "reason": "缺少 name"}, {"line": 19, "reason": "缺少 name"} ] }
```
- `dry_run:true` → 不写库,`imported:0`,`valid` 返回全部解析结果供预览
- `dry_run:false` → 写库,`imported` = 实际 upsert 行数,`valid` 可省略或返回
- 解析失败(JSON 非数组 / CSV 无表头)→ `400 PARSE_ERROR`,带具体原因

### 5.3 `PUT /admin/candidates/{id}`
请求:
```json
{ "category": "character", "fields": {"name":"博丽灵梦","name_jp":"博麗霊夢","origin":"红魔乡","type":"human","first_appearance":"1996"} }
```
- 只更新 `fields` 里提供的、且属于模型列的字段
- `name` 提供且与原值不同 → 检查同 `vote_year` 是否已有该 name(排除自身)→ 冲突 `409 CANDIDATE_NAME_CONFLICT`
- id 不存在 → `404 CANDIDATE_NOT_FOUND`
- 成功 → `{ "ok": true }`

## 六、后端实现要点

### 新增 service(候选项专属逻辑)
建议在 `src/apps/admin/` 下新增 `candidate_service.py`,封装:
- `parse_content(format, content) -> tuple[list[dict], list[dict]]` —— 返回 (parsed_rows, parse_errors)
- `validate_items(category, rows) -> tuple[list[dict], list[dict]]` —— 返回 (valid, rejected),含必填 + insertSelective + 丢弃未知列
- `import_candidates(vote_year, category, valid, dry_run) -> dict`

> 现有 `POST /admin/import-candidates` 改为调用同一 `validate_items` + `upsert_candidates`,避免两套校验。

### 新增 DAO 方法(`ComputeDAO`)
- `get_candidate_fields(category) -> list[dict]` —— 从 `Model.__table__.columns` 推导
- `update_candidate(candidate_id, category, fields) -> str` —— 返回 `"ok"`/`"not_found"`/`"conflict"`,含 name 冲突检测 + insertSelective setattr

### 复用(不改)
`list_candidates`、`delete_candidate`、`upsert_candidates`

## 七、前端(`src/admin_ui/index.html`)

### 7.1 主题改造(全局)
把 `<style>` 块由深色改为白色:
- 背景 `#f0f2f5`,卡片 `#fff` + 边框 `#e2e2e2`,文字 `#1a1a1a`
- 主按钮蓝 `#2563eb`,成功绿 `#16a34a`,危险红 `#dc2626`,次要按钮白底 ghost
- 表格边框 `#eee`,表头灰字
- 此改动影响所有 Tab(统一白色)

### 7.2 列表页(候选项 Tab)
- 工具栏加「+ 导入」按钮(绿色,靠右)
- 每行操作列加「编辑」链接(蓝)+「删除」链接(红)
- 保留分页

### 7.3 导入弹窗(460px)
- 顶部:类别下拉 + 年份输入 + 格式分段控件(自动/CSV/JSON)
- 中部:粘贴 textarea + 「选择文件」按钮(读文件文本填入 textarea)
- 「解析预览」→ 调 import(dry_run:true)→ 渲染预览区(✓有效 N / ✗错误行 + 前若干行表格)
- 底部:「确认导入 N 条」(调 import dry_run:false)+「取消」

### 7.4 编辑弹窗 = 详情页(460px)
- 打开时:`GET /candidates/fields?category=` 拿字段列表,按字段动态渲染表单(必填带 `*`),填入该行当前值
- 底部:「保存」(PUT)/「删除」(DELETE,确认)/「取消」
- 保存成功 → 关弹窗 + 刷新列表;冲突 → 提示 name 已存在

### 7.5 文件读取
`<input type=file>` + `FileReader.readAsText` → 填入 textarea,复用同一套「文本 → import」流程。

## 八、错误处理

| 场景 | 后端 | 前端表现 |
|---|---|---|
| CSV 无表头 / JSON 非数组 | `400 PARSE_ERROR` | 预览区红字显示原因 |
| 某行缺 name | 进 `rejected` | 预览区列出错误行号 |
| 编辑 name 冲突 | `409` | toast「该名称在本年份已存在」|
| 编辑 id 不存在 | `404` | toast「候选项不存在」|
| 未配 admin_secret | 现有行为 | —— |

## 九、测试策略

| 层次 | 覆盖 |
|---|---|
| unit | `parse_content`:CSV(含引号逗号)、JSON 数组、auto 检测、非法输入 |
| unit | `validate_items`:必填缺失、空值 insertSelective、未知列丢弃、character/music 差异 |
| unit | `get_candidate_fields`:两 category 字段 + 必填标记正确 |
| integration | `POST /candidates/import` dry_run 预览 + 真实导入 + 幂等 |
| integration | `PUT /candidates/{id}`:正常改、name 冲突 409、id 不存在 404 |
| contract | 新端点 无 secret → 403;响应 shape |

Web UI 为静态 HTML,手工验收。

## 十、文件变更一览

| 文件 | 操作 |
|---|---|
| `src/apps/admin/candidate_service.py` | 新建(parse + validate + import) |
| `src/apps/result/compute_dao.py` | 加 `get_candidate_fields`、`update_candidate` |
| `src/apps/admin/schemas.py` | 加 import/edit/fields 的 request/response 模型 |
| `src/apps/admin/router.py` | 加 3 端点;`import-candidates` 改走共享 service |
| `src/admin_ui/index.html` | 主题改白 + 候选项 Tab 三界面 |
| `tests/unit/test_candidate_import.py` | 新建 |
| `tests/integration/test_candidate_admin.py` | 新建 |
| `tests/contract/test_candidate_endpoints.py` | 新建 |

## 十一、关联文档

- 管理端原设计:[`2026-06-07-admin-panel-design.md`](./2026-06-07-admin-panel-design.md)
- BACKLOG:新增 B-036
