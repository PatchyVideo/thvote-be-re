#!/usr/bin/env python3
"""往测试库灌可复现的 mock 投票数据(联调/演示/压测用,禁止对生产库执行)。

为什么存在
----------
result 模块(排名/趋势/高级搜索/问卷统计)需要有一定规模、分布真实的投票
数据才能联调和演示;手动投票一次只能造一票,无法覆盖长尾/趋势/子集筛选
等场景。本脚本直接向 ``raw_character_submit`` / ``raw_music_submit`` /
``raw_cp_submit`` / ``paper_answer`` 四张表写入合成投票,并给占位问卷题
回填测试 code(性别题用 Nacos 配置的 code,其余用 9 开头的测试 code,
只填空值不覆盖;B-054 真题录入时重导结构即可)。

数据约定
--------
- 所有合成投票的 ``vote_id`` 一律带 ``mock-`` 前缀——与真人数据的唯一
  区分标志。默认每次运行先删旧 mock 行再重灌(幂等);``--wipe-only``
  只清不灌。**真人投票(无该前缀)绝不触碰。**
- 投票者分 3 个偏好簇,簇内按 Zipf 分布选择候选 → 榜单有头部/长尾,
  且高级搜索按角色/曲目筛出的子集榜与全量榜明显不同(演示价值所在)。
- 提交时间铺满 ``VOTE_START_ISO..VOTE_END_ISO`` 窗口并偏向晚间 → 趋势
  曲线有形状。

怎么跑(测试机后端容器内,详见 docs/operations/mock-vote-data.md)::

    docker exec <backend容器> python scripts/generate_mock_votes.py \
        --voters 4000 --force        # 非交互;不带 --force 会先打印目标库并要求确认
    docker exec <backend容器> python scripts/generate_mock_votes.py --wipe-only --force

    # 灌完后触发计票,结果站才会出数据:
    curl -X POST 'http://127.0.0.1:8000/api/v1/admin/compute-results' \
        -H 'X-Admin-Secret: <ADMIN_SECRET>'
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 允许 `python scripts/generate_mock_votes.py` 直跑(仿 import_mongo_dump.py)
_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

logger = logging.getLogger("generate_mock_votes")

MOCK_PREFIX = "mock-"
N_CLUSTERS = 3
ZIPF_S = 1.3

# 参与率(占投票者总数比例);单测按 ±0.1 带宽断言,改动需同步测试
P_CHAR = 0.85
P_MUSIC = 0.80
P_CP = 0.40
P_PAPER = 0.70
P_MALE = 0.55  # 性别题答"男"比例(答题者内)

_REASONS = [
    "从一开始就喜欢", "曲子太好听了", "本命,没有理由", "今年的新作表现很棒",
    "永远的神", "被同人作品圈粉", "希望明年也能看到", "气质无敌",
]


@dataclass(frozen=True)
class QuestionSpec:
    """一道可作答的问卷题(从 questionnaire_def 结构表读出)。"""

    question_id: int
    questionnaire_id: int
    group_id: int
    qtype: str  # "Single" / "Multiple"
    option_ids: tuple[int, ...]


@dataclass
class MockDataset:
    """待写入四张表的行(dict 即模型构造参数)。"""

    char_rows: list[dict] = field(default_factory=list)
    music_rows: list[dict] = field(default_factory=list)
    cp_rows: list[dict] = field(default_factory=list)
    paper_rows: list[dict] = field(default_factory=list)


def make_vote_id(index: int) -> str:
    return f"{MOCK_PREFIX}{index:05d}"


def cluster_shuffled(pool: list[str], cluster: int, seed: int) -> list[str]:
    """簇专属的确定性偏好序:同 (cluster, seed) 恒同,不同簇不同。"""
    rng = random.Random(f"{seed}:cluster:{cluster}")
    shuffled = list(pool)
    rng.shuffle(shuffled)
    return shuffled


def _zipf_weights(n: int) -> list[float]:
    return [1.0 / (rank + 1) ** ZIPF_S for rank in range(n)]


def _zipf_distinct(rng: random.Random, pref: list[str], k: int) -> list[str]:
    """按 Zipf 权重从偏好序中取 k 个互异项(k ≤ len(pref))。"""
    weights = _zipf_weights(len(pref))
    picked: list[str] = []
    seen: set[str] = set()
    while len(picked) < k:
        item = rng.choices(pref, weights=weights, k=1)[0]
        if item not in seen:
            seen.add(item)
            picked.append(item)
    return picked


def _evening_biased_time(
    rng: random.Random, vote_start: datetime, vote_end: datetime
) -> datetime:
    """窗口内均匀取日,小时偏向晚间(19-23 点权重加倍)。"""
    total = (vote_end - vote_start).total_seconds()
    t = vote_start + timedelta(seconds=rng.random() * total)
    hours = list(range(24))
    weights = [2.0 if 19 <= h <= 23 else 1.0 for h in hours]
    t = t.replace(hour=rng.choices(hours, weights=weights, k=1)[0])
    return min(max(t, vote_start), vote_end - timedelta(seconds=1))


def _maybe_reason(rng: random.Random, p: float = 0.10) -> str | None:
    return rng.choice(_REASONS) if rng.random() < p else None


def _base_row(vote_id: str, created_at: datetime, rng: random.Random) -> dict:
    return {
        "vote_id": vote_id,
        "attempt": 1,
        "created_at": created_at,
        "user_ip": f"203.0.113.{rng.randrange(1, 255)}",  # TEST-NET-3 段
        "fill_duration_ms": rng.randrange(30_000, 300_000),
        "client_env": {"ua": "mock-data-generator"},
        "invalidated": False,
    }


def generate_dataset(
    *,
    voters: int,
    char_pool: list[str],
    music_pool: list[str],
    questions: list[QuestionSpec],
    gender_question_id: int | None,
    male_option_id: int | None,
    female_option_id: int | None,
    vote_year: int,
    vote_start: datetime,
    vote_end: datetime,
    seed: int,
) -> MockDataset:
    """生成全部合成投票行。同 seed 恒同(可复现),不含任何 IO。"""
    rng = random.Random(seed)
    ds = MockDataset()
    char_prefs = [cluster_shuffled(char_pool, c, seed) for c in range(N_CLUSTERS)]
    music_prefs = [cluster_shuffled(music_pool, c, seed) for c in range(N_CLUSTERS)]

    for i in range(voters):
        vid = make_vote_id(i)
        cluster = rng.randrange(N_CLUSTERS)
        created = _evening_biased_time(rng, vote_start, vote_end)
        char_pref = char_prefs[cluster]
        music_pref = music_prefs[cluster]

        if rng.random() < P_CHAR:
            k = rng.choices(range(1, 9), weights=[1, 2, 4, 5, 5, 4, 2, 1], k=1)[0]
            ids = _zipf_distinct(rng, char_pref, min(k, len(char_pref)))
            has_first = rng.random() < 0.70
            ds.char_rows.append({
                **_base_row(vid, created, rng),
                "payload": [
                    {
                        "id": cid,
                        "first": has_first and idx == 0,
                        "reason": _maybe_reason(rng),
                    }
                    for idx, cid in enumerate(ids)
                ],
            })

        if rng.random() < P_MUSIC:
            k = rng.choices(
                range(1, 13), weights=[1, 2, 3, 4, 5, 5, 4, 3, 2, 1, 1, 1], k=1
            )[0]
            ids = _zipf_distinct(rng, music_pref, min(k, len(music_pref)))
            has_first = rng.random() < 0.70
            ds.music_rows.append({
                **_base_row(vid, created, rng),
                "payload": [
                    {
                        "id": mid,
                        "first": has_first and idx == 0,
                        "reason": _maybe_reason(rng),
                    }
                    for idx, mid in enumerate(ids)
                ],
            })

        if rng.random() < P_CP and len(char_pref) >= 3:
            n_groups = rng.choices([1, 2, 3], weights=[7, 2, 1], k=1)[0]
            groups = []
            for g in range(n_groups):
                members = _zipf_distinct(rng, char_pref, 3)
                has_c = rng.random() < 0.15
                id_c = members[2] if has_c else None
                active = rng.choices(
                    ["a", "b", "c", "none"],
                    weights=[3, 3, (1 if has_c else 0), 4],
                    k=1,
                )[0]
                groups.append({
                    "id_a": members[0],
                    "id_b": members[1],
                    "id_c": id_c,
                    "active": active,
                    "first": g == 0 and rng.random() < 0.5,
                    "reason": _maybe_reason(rng, 0.05),
                })
            ds.cp_rows.append({
                **_base_row(vid, created, rng),
                "payload": groups,
            })

        if rng.random() < P_PAPER:
            # paper_answer 有 UNIQUE(vote_id, vote_year, questionnaire_id,
            # group_id):每票每题组一行,组内挑一道题作答(有性别题恒选它,
            # 保证分段轴数据不被随机挑题稀释)。
            groups: dict[tuple[int, int], list[QuestionSpec]] = {}
            for q in questions:
                if q.option_ids:
                    groups.setdefault(
                        (q.questionnaire_id, q.group_id), []
                    ).append(q)
            for group_questions in groups.values():
                q = next(
                    (g for g in group_questions
                     if g.question_id == gender_question_id),
                    None,
                )
                if q is None:
                    if rng.random() < 0.10:
                        continue  # 无性别题的组 10% 跳答
                    q = rng.choice(group_questions)
                if (
                    q.question_id == gender_question_id
                    and male_option_id is not None
                    and female_option_id is not None
                ):
                    picked = [
                        male_option_id
                        if rng.random() < P_MALE else female_option_id
                    ]
                elif q.qtype == "Single":
                    picked = [rng.choice(q.option_ids)]
                else:
                    n_opts = rng.randrange(1, len(q.option_ids) + 1)
                    picked = sorted(rng.sample(q.option_ids, n_opts))
                ds.paper_rows.append({
                    "vote_id": vid,
                    "vote_year": vote_year,
                    "questionnaire_id": q.questionnaire_id,
                    "group_id": q.group_id,
                    "active_question_id": q.question_id,
                    "selected_option_ids": list(picked),
                    "input_text": None,
                })
    return ds


def plan_code_backfill(
    questions: list[tuple[int, str | None, str]],
    options: dict[int, list[tuple[int, str | None]]],
    gender_question_code: str,
    male_code: str,
    female_code: str,
) -> list[tuple[str, int, str]]:
    """规划占位题/选项的测试 code 回填(纯决策,不做 IO)。

    规则:只给空 code(None/"")分配;第一道空 code 的 Single 题按性别题
    处理(题拿 gender_question_code,前两个空 code 选项拿男/女 code),
    其余一律拿 "9" 开头的顺延测试 code;已有 code 的行绝不出现在计划里。
    返回 [("question"|"option", id, new_code)],new_code 全局唯一。
    """
    used: set[str] = {c for _, c, _ in questions if c}
    for opts in options.values():
        used.update(c for _, c in opts if c)
    used.update({gender_question_code, male_code, female_code})

    counter = 90001

    def next9() -> str:
        nonlocal counter
        while str(counter) in used:
            counter += 1
        code = str(counter)
        used.add(code)
        counter += 1
        return code

    plan: list[tuple[str, int, str]] = []
    gender_assigned = False
    for qid, qcode, qtype in questions:
        is_gender = False
        if not qcode:
            if not gender_assigned and qtype == "Single":
                plan.append(("question", qid, gender_question_code))
                gender_assigned = True
                is_gender = True
            else:
                plan.append(("question", qid, next9()))
        gender_codes = [male_code, female_code] if is_gender else []
        for opt_id, ocode in options.get(qid, []):
            if ocode:
                continue
            if gender_codes:
                plan.append(("option", opt_id, gender_codes.pop(0)))
            else:
                plan.append(("option", opt_id, next9()))
    return plan


# ── DB 编排(以下才碰数据库) ─────────────────────────────────────────


async def wipe_mock_rows(session) -> dict[str, int]:
    """删除四张表里所有 ``mock-`` 前缀的行。只动 mock 数据,返回各表删数。"""
    from sqlalchemy import delete

    from src.db_model.questionnaire_def import PaperAnswer
    from src.db_model.raw_submit import (
        RawCharacterSubmit,
        RawCPSubmit,
        RawMusicSubmit,
    )

    counts: dict[str, int] = {}
    for key, model in (
        ("char", RawCharacterSubmit),
        ("music", RawMusicSubmit),
        ("cp", RawCPSubmit),
        ("paper", PaperAnswer),
    ):
        result = await session.execute(
            delete(model).where(model.vote_id.like(f"{MOCK_PREFIX}%"))
        )
        counts[key] = result.rowcount or 0
    await session.commit()
    return counts


async def _load_question_structure(
    session,
) -> tuple[list[tuple[int, str | None, str]], dict, dict[int, tuple[int, int]]]:
    """读全部题与选项。

    返回 (questions=[(qid, code, type)], options={qid: [(oid, code)]},
    meta={qid: (questionnaire_id, group_id)})。
    """
    from sqlalchemy import select

    from src.db_model.questionnaire_def import (
        OptionDef,
        QuestionDef,
        QuestionGroupDef,
    )

    q_rows = (await session.execute(
        select(
            QuestionDef.id, QuestionDef.code, QuestionDef.type,
            QuestionGroupDef.questionnaire_id, QuestionGroupDef.id,
        ).join(QuestionGroupDef, QuestionDef.group_id == QuestionGroupDef.id)
        .order_by(QuestionDef.id)
    )).all()
    questions = [(qid, code, qtype) for qid, code, qtype, _, _ in q_rows]
    meta = {qid: (paper_id, group_id) for qid, _, _, paper_id, group_id in q_rows}
    o_rows = (await session.execute(
        select(OptionDef.question_id, OptionDef.id, OptionDef.code)
        .order_by(OptionDef.id)
    )).all()
    options: dict[int, list[tuple[int, str | None]]] = {}
    for question_id, opt_id, code in o_rows:
        options.setdefault(question_id, []).append((opt_id, code))
    return questions, options, meta


async def run_generation(
    session,
    *,
    voters: int,
    vote_year: int,
    seed: int,
    vote_start: datetime,
    vote_end: datetime,
    gender_question_code: str,
    male_code: str,
    female_code: str,
) -> dict:
    """清旧 mock → 回填测试 code → 生成 → 写入。幂等,只动 mock 前缀行。"""
    from sqlalchemy import update

    from src.apps.result.whitelist import load_whitelist_db
    from src.db_model.questionnaire_def import OptionDef, PaperAnswer, QuestionDef
    from src.db_model.raw_submit import (
        RawCharacterSubmit,
        RawCPSubmit,
        RawMusicSubmit,
    )

    wiped = await wipe_mock_rows(session)

    char_wl = await load_whitelist_db(session, "character", vote_year)
    music_wl = await load_whitelist_db(session, "music", vote_year)
    char_pool = sorted(str(e.candidate_id) for e in char_wl.entries)
    music_pool = sorted(str(e.candidate_id) for e in music_wl.entries)
    if not char_pool or not music_pool:
        raise RuntimeError(
            f"vote_year={vote_year} 的候选人白名单为空(char={len(char_pool)} "
            f"music={len(music_pool)}),先导入候选人再灌 mock 数据"
        )

    questions, options, meta = await _load_question_structure(session)
    plan = plan_code_backfill(
        questions, options, gender_question_code, male_code, female_code
    )
    for kind, row_id, code in plan:
        model = QuestionDef if kind == "question" else OptionDef
        await session.execute(
            update(model).where(model.id == row_id).values(code=code)
        )
    await session.commit()

    # 回填后重读,按 code 定位性别题/选项 id(可能来自本次回填,也可能原本就有)
    questions, options, meta = await _load_question_structure(session)
    gender_question_id = next(
        (qid for qid, code, _ in questions if code == gender_question_code), None
    )
    male_option_id = female_option_id = None
    if gender_question_id is not None:
        for opt_id, code in options.get(gender_question_id, []):
            if code == male_code:
                male_option_id = opt_id
            elif code == female_code:
                female_option_id = opt_id

    specs = [
        QuestionSpec(
            question_id=qid,
            questionnaire_id=meta[qid][0],
            group_id=meta[qid][1],
            qtype=qtype,
            option_ids=tuple(oid for oid, _ in options.get(qid, [])),
        )
        for qid, _, qtype in questions
    ]

    dataset = generate_dataset(
        voters=voters,
        char_pool=char_pool,
        music_pool=music_pool,
        questions=specs,
        gender_question_id=gender_question_id,
        male_option_id=male_option_id,
        female_option_id=female_option_id,
        vote_year=vote_year,
        vote_start=vote_start,
        vote_end=vote_end,
        seed=seed,
    )

    for model, rows in (
        (RawCharacterSubmit, dataset.char_rows),
        (RawMusicSubmit, dataset.music_rows),
        (RawCPSubmit, dataset.cp_rows),
        (PaperAnswer, dataset.paper_rows),
    ):
        session.add_all(model(**row) for row in rows)
    await session.commit()

    summary = {
        "wiped": wiped,
        "inserted": {
            "char": len(dataset.char_rows),
            "music": len(dataset.music_rows),
            "cp": len(dataset.cp_rows),
            "paper": len(dataset.paper_rows),
        },
        "backfilled_codes": len(plan),
        "gender_question_id": gender_question_id,
    }
    logger.info("mock generation done: %s", summary)
    return summary


# ── CLI 入口 ─────────────────────────────────────────────────────────


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


async def _amain(args: argparse.Namespace) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from src.common.config import get_settings
    from src.common.database import normalize_async_database_url

    settings = get_settings()
    vote_year = args.vote_year or settings.vote_year
    db_url = normalize_async_database_url(settings.database_url)
    safe_url = db_url.split("@")[-1]  # 只露 host/库名,不露凭据

    action = "清除 mock 数据" if args.wipe_only else f"灌入 {args.voters} 个 mock 投票者"
    print(f"目标库: {safe_url}\nvote_year: {vote_year}\n动作: {action}")
    if not args.force:
        if input("确认执行?仅限测试环境![yes/N] ").strip().lower() != "yes":
            print("已取消")
            return

    engine = create_async_engine(db_url, echo=False)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            if args.wipe_only:
                print("wiped:", await wipe_mock_rows(session))
                return
            summary = await run_generation(
                session,
                voters=args.voters,
                vote_year=vote_year,
                seed=args.seed,
                vote_start=_parse_iso(settings.vote_start_iso),
                vote_end=_parse_iso(settings.vote_end_iso),
                gender_question_code=settings.gender_question_code,
                male_code=settings.gender_male_option_code,
                female_code=settings.gender_female_option_code,
            )
            print("summary:", summary)
            print("提示: 数据已入库,需再触发 compute 结果站才会更新"
                  "(POST /api/v1/admin/compute-results,带 X-Admin-Secret)")
    finally:
        await engine.dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--voters", type=int, default=4000, help="投票者数(默认 4000)")
    parser.add_argument("--vote-year", type=int, default=None,
                        help="默认取 settings.vote_year")
    parser.add_argument("--seed", type=int, default=42, help="随机种子,同种子可复现")
    parser.add_argument("--wipe-only", action="store_true", help="只清除 mock 数据")
    parser.add_argument("--force", action="store_true",
                        help="跳过交互确认(容器内非交互执行用)")
    asyncio.run(_amain(parser.parse_args()))


if __name__ == "__main__":
    main()
