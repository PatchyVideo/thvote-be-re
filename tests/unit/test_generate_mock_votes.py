"""mock 投票数据生成器纯逻辑单测(scripts/generate_mock_votes.py)。

只测纯函数:数据集生成的不变量、确定性、簇差异、code 回填规划。
DB 写入/清理见 tests/integration/test_generate_mock_votes_db.py。
"""

from __future__ import annotations

from datetime import datetime, timezone

from scripts.generate_mock_votes import (
    MOCK_PREFIX,
    QuestionSpec,
    cluster_shuffled,
    generate_dataset,
    make_vote_id,
    plan_code_backfill,
)

VOTE_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
VOTE_END = datetime(2026, 3, 1, tzinfo=timezone.utc)

CHAR_POOL = [str(i) for i in range(100, 160)]   # 60 个角色 id
MUSIC_POOL = [str(i) for i in range(500, 580)]  # 80 个曲目 id

# paper_answer 表有 UNIQUE(vote_id, vote_year, questionnaire_id, group_id):
# 每票每题组只有一行,active_question_id 是组内被答的那道题——因此常规
# 结构是一题一组;共组场景见 TestPaperRows 的专项测试。
QUESTIONS = [
    QuestionSpec(
        question_id=1, questionnaire_id=1, group_id=1,
        qtype="Single", option_ids=(11, 12),
    ),
    QuestionSpec(
        question_id=2, questionnaire_id=1, group_id=2,
        qtype="Multiple", option_ids=(21, 22, 23),
    ),
]


def _gen(voters: int = 400, seed: int = 42):
    return generate_dataset(
        voters=voters,
        char_pool=CHAR_POOL,
        music_pool=MUSIC_POOL,
        questions=QUESTIONS,
        gender_question_id=1,
        male_option_id=11,
        female_option_id=12,
        vote_year=2026,
        vote_start=VOTE_START,
        vote_end=VOTE_END,
        seed=seed,
    )


class TestVoteId:
    def test_prefix_and_padding(self):
        assert make_vote_id(7) == f"{MOCK_PREFIX}00007"

    def test_all_rows_prefixed_and_unique_per_table(self):
        ds = _gen()
        for rows in (ds.char_rows, ds.music_rows, ds.cp_rows):
            ids = [r["vote_id"] for r in rows]
            assert all(v.startswith(MOCK_PREFIX) for v in ids)
            assert len(ids) == len(set(ids))  # 每 vote_id 每表至多一行


class TestPayloadInvariants:
    def test_char_payload_shape(self):
        ds = _gen()
        assert ds.char_rows  # 参与率 >0
        for row in ds.char_rows:
            items = row["payload"]
            assert 1 <= len(items) <= 8
            ids = [it["id"] for it in items]
            assert len(ids) == len(set(ids))  # 同票内不重复
            assert set(ids) <= set(CHAR_POOL)
            assert sum(1 for it in items if it["first"]) <= 1
            for it in items:
                assert set(it) == {"id", "first", "reason"}

    def test_music_payload_shape(self):
        ds = _gen()
        for row in ds.music_rows:
            items = row["payload"]
            assert 1 <= len(items) <= 12
            assert {it["id"] for it in items} <= set(MUSIC_POOL)

    def test_cp_payload_shape(self):
        ds = _gen()
        assert ds.cp_rows
        for row in ds.cp_rows:
            for it in row["payload"]:
                assert set(it) == {
                    "id_a", "id_b", "id_c", "active", "first", "reason",
                }
                assert it["id_a"] in CHAR_POOL and it["id_b"] in CHAR_POOL
                assert it["id_a"] != it["id_b"]
                assert it["active"] in {"a", "b", "c", "none"}
                if it["id_c"] is not None:
                    assert it["id_c"] in CHAR_POOL
                    assert it["id_c"] not in (it["id_a"], it["id_b"])

    def test_row_columns_for_model(self):
        ds = _gen()
        row = ds.char_rows[0]
        assert row["attempt"] == 1
        assert row["invalidated"] is False
        assert isinstance(row["user_ip"], str) and row["user_ip"]
        assert isinstance(row["fill_duration_ms"], int)

    def test_timestamps_within_window(self):
        ds = _gen()
        for rows in (ds.char_rows, ds.music_rows, ds.cp_rows):
            for row in rows:
                assert VOTE_START <= row["created_at"] < VOTE_END


class TestPaperRows:
    def test_paper_rows_reference_question_options(self):
        ds = _gen()
        assert ds.paper_rows
        by_q = {q.question_id: q for q in QUESTIONS}
        for row in ds.paper_rows:
            q = by_q[row["active_question_id"]]
            assert row["vote_year"] == 2026
            assert row["questionnaire_id"] == q.questionnaire_id
            assert row["group_id"] == q.group_id
            assert set(row["selected_option_ids"]) <= set(q.option_ids)
            assert row["selected_option_ids"]  # 非空
            if q.qtype == "Single":
                assert len(row["selected_option_ids"]) == 1

    def test_at_most_one_row_per_vote_and_group(self):
        ds = _gen(voters=500)
        seen = set()
        for row in ds.paper_rows:
            key = (row["vote_id"], row["questionnaire_id"], row["group_id"])
            assert key not in seen  # UNIQUE(vote_id, vote_year, paper, group)
            seen.add(key)

    def test_shared_group_prefers_gender_question(self):
        shared = [
            QuestionSpec(
                question_id=1, questionnaire_id=1, group_id=1,
                qtype="Single", option_ids=(11, 12),
            ),
            QuestionSpec(
                question_id=2, questionnaire_id=1, group_id=1,
                qtype="Multiple", option_ids=(21, 22, 23),
            ),
        ]
        ds = generate_dataset(
            voters=300, char_pool=CHAR_POOL, music_pool=MUSIC_POOL,
            questions=shared, gender_question_id=1,
            male_option_id=11, female_option_id=12,
            vote_year=2026, vote_start=VOTE_START, vote_end=VOTE_END, seed=3,
        )
        assert ds.paper_rows
        # 组内有性别题时恒答性别题(分段轴数据不因随机挑题而稀释)
        assert all(r["active_question_id"] == 1 for r in ds.paper_rows)

    def test_gender_ratio_roughly_55_45(self):
        ds = _gen(voters=1000)
        gender_rows = [
            r for r in ds.paper_rows if r["active_question_id"] == 1
        ]
        male = sum(1 for r in gender_rows if r["selected_option_ids"] == [11])
        assert gender_rows
        ratio = male / len(gender_rows)
        assert 0.45 <= ratio <= 0.65  # 目标 0.55,给采样波动余量


class TestDistribution:
    def test_deterministic_same_seed(self):
        assert _gen(seed=7) == _gen(seed=7)

    def test_different_seed_differs(self):
        assert _gen(seed=7) != _gen(seed=8)

    def test_clusters_reorder_pool_differently(self):
        a = cluster_shuffled(CHAR_POOL, cluster=0, seed=42)
        b = cluster_shuffled(CHAR_POOL, cluster=1, seed=42)
        assert sorted(a) == sorted(CHAR_POOL) and sorted(b) == sorted(CHAR_POOL)
        assert a != b  # 不同簇不同偏好序
        assert cluster_shuffled(CHAR_POOL, cluster=0, seed=42) == a  # 确定性

    def test_zipf_head_heavier_than_tail(self):
        ds = _gen(voters=1000)
        counts: dict[str, int] = {}
        for row in ds.char_rows:
            for it in row["payload"]:
                counts[it["id"]] = counts.get(it["id"], 0) + 1
        ranked = sorted(counts.values(), reverse=True)
        head = sum(ranked[:6])
        tail = sum(ranked[-6:]) if len(ranked) >= 12 else 0
        assert head > tail * 3  # 头部显著重于长尾

    def test_participation_rates_in_expected_bands(self):
        voters = 1000
        ds = _gen(voters=voters)
        assert 0.75 <= len(ds.char_rows) / voters <= 0.95
        assert 0.70 <= len(ds.music_rows) / voters <= 0.90
        assert 0.30 <= len(ds.cp_rows) / voters <= 0.50


class TestCodeBackfill:
    def test_fills_gender_and_placeholder_codes_only_when_empty(self):
        questions = [
            # (question_id, code, qtype)
            (1, None, "Single"),
            (2, "", "Multiple"),
            (3, "77777", "Single"),  # 已有 code,不许动
        ]
        options = {
            1: [(11, None), (12, None), (13, None)],
            2: [(21, None), (22, "")],
            3: [(31, "7770001")],
        }
        plan = plan_code_backfill(
            questions, options,
            gender_question_code="11011",
            male_code="1101101",
            female_code="1101102",
        )
        assigned = {(kind, oid): code for kind, oid, code in plan}
        # 第一道空 code 的 Single 题成为性别题
        assert assigned[("question", 1)] == "11011"
        assert assigned[("option", 11)] == "1101101"
        assert assigned[("option", 12)] == "1101102"
        # 性别题多余选项与其他空 code 拿 9 系测试 code
        assert assigned[("option", 13)].startswith("9")
        assert assigned[("question", 2)].startswith("9")
        assert assigned[("option", 21)].startswith("9")
        assert assigned[("option", 22)].startswith("9")
        # 已有 code 的一律不出现在计划里
        assert ("question", 3) not in assigned
        assert ("option", 31) not in assigned
        # code 全局不重复
        codes = [c for _, _, c in plan]
        assert len(codes) == len(set(codes))
