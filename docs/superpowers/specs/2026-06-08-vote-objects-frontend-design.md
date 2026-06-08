# Block 3B 投票对象迁后端 — 前端设计稿(thvote-fe)

> 创建日期：2026-06-08
> 最后更新：2026-06-08
> 配套后端设计稿：[`2026-06-08-vote-objects-backend-design.md`](./2026-06-08-vote-objects-backend-design.md)
> 仓库：`D:\personal\thvote-fe`，包：`packages/vote`

## 一、背景

角色/音乐投票列表当前 bundle 在前端 `@touhou-vote/shared/data/{character,music}`,前端做分类(按 work/album)。本块**一次性切换**为从后端拉,新建通用"从后端拉投票对象"封装。

## 二、改动点

### 1. 角色投票页 `vote-character`
- 候选列表来源:`shared/data/character` → `GET /vote-objects/characters?vote_year=`。
- 后端已**按首登作品分组**返回,前端直接渲染分类选择组件(不再前端分组)。
- 通过新建的通用 `voteObjectsDataSource` 加载。
- 选择/本命/理由/提交 不变。

### 2. 音乐投票页 `vote-music`
- 同上:`shared/data/music` → `GET /vote-objects/music?vote_year=`(后端按专辑分组)。

### 3. CP 投票页 `vote-couple`
- CP 由角色组合而来;角色列表改从后端拉后,CP 页的角色来源同步切到后端(CP 本身仍是前端组合逻辑)。

### 4. 通用数据加载封装
- 新建 `packages/vote/src/common/lib/voteObjectsDataSource.ts`:`fetchVoteObjects(category, voteYear) → groups`。
- 角色/音乐共用。

## 三、保留 / 弃用
- **弃用**(投票页运行时数据源):`shared/data/character`、`shared/data/music` 作为投票列表来源。
  - 注:这些静态数据可能还被 result 展示/导出图片用作 fallback;只切投票页的来源,其余按需评估。
- **保留**:选择交互、本命、理由、提交逻辑。

## 四、契约
- `GET /vote-objects/characters?vote_year=` → `{vote_year, groups:[{group, items:[{id,name,name_jp,origin,first_appearance}]}]}`
- `GET /vote-objects/music?vote_year=` → `{...groups by album, items:[{id,name,name_jp,album}]}`
- character/music 同族形状。

## 五、测试/验收(手工)
- 角色页:从后端拉到按首登作品分组的列表,渲染与切换前一致。
- 音乐页:按专辑分组正确。
- 合并生效:被合并的重复角色/同曲名不同专辑在列表中只出现规范化主候选。
- CP 页角色来源正常。
- 回归:提交/本命/理由/结果页不受影响。

## 六、文件变更一览(前端)

| 文件 | 操作 |
|---|---|
| `packages/vote/src/common/lib/voteObjectsDataSource.ts` | 新建(通用投票对象数据源) |
| `packages/vote/src/vote-character/lib/*` | 列表来源改后端 |
| `packages/vote/src/vote-music/lib/*` | 同上 |
| `packages/vote/src/vote-couple/lib/*` | 角色来源切后端 |

## 七、依赖与顺序
- 依赖后端 3B 的 `/vote-objects/characters|music` 合并。
- 建议:后端先合并 + 候选数据导入(含自动合并)→ 前端切换 → 联调。

## 八、关联
- 后端设计稿:[`2026-06-08-vote-objects-backend-design.md`](./2026-06-08-vote-objects-backend-design.md)
