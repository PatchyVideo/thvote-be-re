# Mongodump BSON 离线导入 Design

> 创建日期: 2026-06-09  
> 最后更新: 2026-06-09  
> 前置: MongoDB dump 文件已提供 (`dump260311_2`)

---

## 诊断

- 原 MongoDB 在线同步 (`sync/runner.py`) 依赖 `pymongo` 直连 MongoDB，但 MongoDB 实例已不可用
- 前任负责人提供了 `mongodump` 格式的 BSON dump（4 个库，1.6GB），可用 `bson` 包直接解码
- 现有 mapper 函数和 `ON CONFLICT DO NOTHING` 写入逻辑完全可复用

## Dump 结构

| 目录 (DB) | Collection | PG 目标表 | 现有 mapper |
|---|---|---|---|
| `thvote_users/` | `voters` | `user` | `map_voter` |
| `submits_v1/` | `raw_character/music/cp/dojin/paper` (5) | 同名 (5) | `map_raw_submit` / `map_raw_paper` |
| `submits_v1_final/` | `chars` | `candidate_character` | `map_candidate_character` |
| `submits_v1_final/` | `musics` | `candidate_music` | `map_candidate_music` |
| `submits_v1_final/` | `final_ranking_char/music` | `final_ranking` | `map_final_ranking` |
| `admin/` | `system.version` | — | 跳过 |
| `submits_v1_final/` | `cache_*/covote_*/votes/paper_result/...` | — | 跳过 |

## 设计

### 新建 `scripts/import_mongo_dump.py`

单文件 CLI 脚本，输入 dump 目录路径，批量导入到 PostgreSQL。

### 流程

```
读取配置 → 遍历 dump 目录 → 每个 .bson 文件:
  for doc in bson.decode_all():
    row = mapper(doc)           # 复用现有 mapper
    batch.append(row)
    if len(batch) >= batch_size:
      INSERT ... ON CONFLICT DO NOTHING  # 复用现有逻辑
  输出进度: collection → total → inserted/skipped/errors
```

### 复用代码

- `src/apps/admin/sync/runner.py`: `map_voter`, `map_raw_submit`, `map_raw_paper`, `map_candidate_character`, `map_candidate_music`, `map_final_ranking`, `_CONFLICT_COLS`
- 去重策略: `ON CONFLICT (key) DO NOTHING`（与在线 sync 一致）

### 依赖

- `pymongo`（提供 `bson` 解码）—— 已存在于 `pyproject.toml` 的可选依赖
- PostgreSQL 连接复用 `src.common.config` → `get_settings().database_url`
