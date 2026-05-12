# Submit 模块补完设计规格

> 创建日期：2026-05-13
> 最后更新：2026-05-13
>
> 关联：`src/apps/submit/`，BACKLOG B-003

---

## 一、背景

Submit 模块 12 个端点功能已完整，但存在以下缺口：
1. **B-003**：无 vote_token JWT 鉴权（任意 vote_id 可提交）
2. `validate_paper` 是空实现（问卷直通）
3. `get_statistics()` 中 `num_finished_paper` 硬编码 0
4. 测试覆盖 0%

---

## 二、vote_token 鉴权（B-003）

### SubmitMetadata 变更

```python
class SubmitMetadata(BaseModel):
    vote_token: str | None = None   # 新增：提交端点必须携带
    vote_id: str = "<unknown>"      # 保留（用于锁 key 兼容）
    attempt: int | None = None
    created_at: datetime = Field(default_factory=utcnow)
    user_ip: str = "<unknown>"
    additional_fingreprint: str | None = None
```

### 路由层鉴权依赖

新增 `_verify_vote_token(body)` 依赖函数，仅在 5 个提交端点使用（get-* / voting-status 不需要）：

```python
async def _verify_vote_token(body) -> VoteTokenPayload:
    if not body.meta.vote_token:
        raise HTTPException(401, "VOTE_TOKEN_REQUIRED")
    try:
        return decode_vote_token(body.meta.vote_token)
    except JWTValidationError as exc:
        raise HTTPException(401, str(exc))
```

rate_limit 和 lock key 改用 `payload.user_id`（比 vote_id 更可靠）：

```python
await rate_limit(payload.user_id, redis_client)
lock_key, lock_value = await _acquire_vote_lock(payload.user_id)
```

### 错误响应

| 场景 | HTTP 状态 | detail |
|---|---|---|
| vote_token 缺失 | 401 | `VOTE_TOKEN_REQUIRED` |
| 签名无效 / 过期 | 401 | JWT 错误消息 |
| 速率限制 | 429 | `REQUEST_TOO_FREQUENT` |
| 锁定 | 429 | `SUBMIT_LOCKED` |

---

## 三、validate_paper 实现

`papers_json` 是一个 JSON 字符串，内容为问卷答案列表。校验规则：

1. 必须是合法 JSON
2. 解析结果必须是非空 list
3. 每条 item 必须有整数 `id` 字段
4. `answer_str` 如存在，长度 ≤ 4096

```python
def validate_paper(self, data: PaperSubmitRest) -> PaperSubmitRest:
    try:
        items = json.loads(data.papers_json)
    except (json.JSONDecodeError, ValueError):
        raise ValueError("papers_json 不是合法 JSON")
    if not isinstance(items, list) or not items:
        raise ValueError("papers_json 必须为非空列表")
    for item in items:
        if not isinstance(item.get("id"), int):
            raise ValueError("每个 paper item 必须有整数 id")
        ans_str = item.get("answer_str")
        if ans_str is not None and len(str(ans_str)) > 4096:
            raise ValueError("answer_str 过长")
    return data
```

---

## 四、num_finished_paper 修复

`SubmitDAO.get_statistics()` 中：

```python
# 修复前
"num_finished_paper": 0,

# 修复后
paper_count = await self.session.scalar(
    select(func.count(func.distinct(RawPaperSubmit.vote_id)))
)
"num_finished_paper": paper_count or 0,
```

---

## 五、测试套件

### 单元测试（`tests/unit/test_submit_validator.py`）

测试 `SubmitValidator` 的 5 个方法：

| 测试函数 | 验证内容 |
|---|---|
| `test_validate_character_ok` | 合法数据通过 |
| `test_validate_character_too_many` | >8 个角色 → ValueError |
| `test_validate_character_duplicate` | 重复 id → ValueError |
| `test_validate_character_multiple_first` | 多个本命 → ValueError |
| `test_validate_character_reason_too_long` | 理由 >4096 → ValueError |
| `test_validate_music_ok` | 合法音乐数据通过 |
| `test_validate_music_too_many` | >12 首 → ValueError |
| `test_validate_cp_ok` | 合法 CP 数据通过 |
| `test_validate_cp_invalid_active` | active 不在 id_a/id_b/id_c → ValueError |
| `test_validate_paper_ok` | 合法 papers_json 通过 |
| `test_validate_paper_invalid_json` | 非法 JSON → ValueError |
| `test_validate_paper_empty_list` | 空列表 → ValueError |
| `test_validate_paper_missing_id` | item 无整数 id → ValueError |
| `test_validate_dojin_ok` | 合法同人数据通过 |
| `test_validate_dojin_reason_too_long` | reason >4096 → ValueError |

### 集成测试（`tests/integration/test_submit.py`）

使用 SQLite + fakeredis + 真实 vote_token：

| 测试函数 | 验证内容 |
|---|---|
| `test_submit_character_ok` | 合法提交 → 201，DB 有记录 |
| `test_submit_character_no_token` | 缺 vote_token → 401 |
| `test_submit_character_invalid_token` | 无效 token → 401 |
| `test_get_character_submit` | 提交后 get → 返回 payload |
| `test_voting_status` | 提交角色后 has_characters=True |
| `test_statistics_num_finished_paper` | 提交 paper 后统计数正确 |

### 契约测试

扩展 `tests/contract/test_router_endpoints.py`，补全 submit 端点可达性测试。

---

## 六、不在本次范围内

- `papers_json` 内容的语义校验（具体题目 ID 合法性）
- 同人 (`dojin`) 的 URL 格式校验
- submit 端点的 `vote_token` 必需化（当前 `| None`，保留向后兼容）
