"""Pure compute functions for result aggregation.

All functions here are side-effect-free: they take data as arguments and
return computed results. No database or Redis access.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import combinations
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.apps.result.whitelist import Whitelist


# ── Segmentation (generalized gender) ──────────────────────────────────


def build_segment_map(
    questionnaire_votes: list[tuple[str, list[dict]]],
    question_code: str,
    label_by_option: dict[str, str],
) -> dict[str, str]:
    """Map user_id → segment label from questionnaire data.

    A "segment" is just the answer a voter gave to a designated
    questionnaire question (``question_code``), projected through
    ``label_by_option`` (option code → label, e.g. {"1101101": "male"}).
    Gender is no longer special-cased: it is simply the segment produced
    when the demographic-axis question happens to be the gender question.
    No match (question not answered, or answer not in label_by_option) →
    ``"unknown"``.
    """
    result: dict[str, str] = {}
    for user_id, q_list in questionnaire_votes:
        label = "unknown"
        for item in q_list:
            if item.get("id") == question_code:
                ans = item.get("answer")
                val = (
                    (ans[0] if isinstance(ans, list) and ans else None)
                    or item.get("answer_str")
                    or ""
                )
                label = label_by_option.get(val, "unknown")
                break
        result[user_id] = label
    return result


def _segment_breakdown(
    segs: dict[str, int], vc: int, segment_totals: dict[str, int]
) -> dict[str, dict]:
    """按 label 展开 vote_count / percentage_per_item / percentage_per_total。

    ``percentage_per_total`` 的分母是**该 label 自己的总人数**（旧网关口径
    ``male_percentage_per_total = male_count / total_male``，即"占总体男性
    比例"，不是"占全体投票人数比例"）——``segment_totals`` 由调用方按同一批
    ``votes`` 统计出的每个 label 的人数传入，不能用共享的 ``total_voters``
    代替，否则值系统性偏小。
    """

    def _one(label: str, count: int) -> dict:
        denom = segment_totals.get(label, 0)
        return {
            "vote_count": count,
            "percentage_per_item": round(count / vc, 4) if vc else 0.0,
            "percentage_per_total": round(count / denom, 4) if denom else 0.0,
        }

    return {label: _one(label, count) for label, count in segs.items()}


def _legacy_gender_projection(segments: dict[str, dict]) -> tuple[dict, dict]:
    """把 segments["male"/"female"] 投影为旧字段形状（供未迁移的消费方过渡用）。

    旧字段用 percentage_per_char 而非 percentage_per_item；缺失该 label 时
    返回全 0，不报错。
    """
    zero = {"vote_count": 0, "percentage_per_item": 0.0, "percentage_per_total": 0.0}

    def _proj(label: str) -> dict:
        s = segments.get(label, zero)
        return {
            "vote_count": s["vote_count"],
            "percentage_per_char": s["percentage_per_item"],
            "percentage_per_total": s["percentage_per_total"],
        }

    return _proj("male"), _proj("female")


# ── Character / Music Ranking ─────────────────────────────────────────


def compute_ranking(
    votes: list[tuple[str, datetime, list[dict]]],
    whitelist: "Whitelist",
    segment_map: dict[str, str],
    historical: dict[str, dict],
    vote_start: datetime,
    total_hours: int,
) -> tuple[list[dict], dict]:
    """按 id 归票的角色/音乐排名（B-050）。

    votes: (vote_id, submit_datetime, items)，item = {"id", "first", "reason"}
    whitelist: id 白名单/展示注册表；不在白名单的 id 直接丢弃。
    segment_map: vote_id → 分段标签（如 "male"/"female"，或其它问卷题的选项
    label）；由 build_segment_map 构造，性别只是其中一种特例。
    历史键仍按 name（final_ranking 是 name-keyed）；v1 传空 dict。
    返回 (ranking_list, global_stats_dict)
    """
    vote_count: dict[str, int] = defaultdict(int)      # 按 oid
    first_count: dict[str, int] = defaultdict(int)
    reasons: dict[str, list[str]] = defaultdict(list)
    segment_count: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    trend: dict[str, list[int]] = defaultdict(lambda: [0] * max(total_hours, 1))
    trend_first: dict[str, list[int]] = defaultdict(lambda: [0] * max(total_hours, 1))
    total_voters = len(votes)
    # 每个 label(如 male/female)在本类别投票人群中的总人数——
    # percentage_per_total 的分母（旧网关口径，见 _segment_breakdown）。
    segment_totals = Counter(
        segment_map.get(user_id, "unknown") for user_id, _, _ in votes
    )

    for user_id, submit_dt, items in votes:
        segment = segment_map.get(user_id, "unknown")
        if submit_dt.tzinfo is None:
            submit_dt = submit_dt.replace(tzinfo=timezone.utc)
        hour_bucket = max(0, min(
            int((submit_dt - vote_start).total_seconds() / 3600), total_hours - 1))
        seen_in_vote: set[str] = set()
        for item in items:
            oid = item.get("id", "")
            if not oid or oid not in whitelist:
                continue
            if oid in seen_in_vote:  # 同一账号同一 id 只计一次
                continue
            seen_in_vote.add(oid)
            is_first = bool(item.get("first", False))
            reason = item.get("reason")
            vote_count[oid] += 1
            if is_first:
                first_count[oid] += 1
            if reason:
                reasons[oid].append(reason)
            segment_count[oid][segment] += 1
            trend[oid][hour_bucket] += 1
            if is_first:
                trend_first[oid][hour_bucket] += 1

    all_ids = set(vote_count.keys())
    total_votes = sum(vote_count.values())
    total_first = sum(first_count.values())

    # 名次：票数→本命数→系统ID
    sorted_ids = sorted(
        all_ids,
        key=lambda o: (-vote_count[o], -first_count[o], whitelist.system_id_of(o)),
    )

    ranking = []
    prev_vc = None
    prev_display_rank = 0
    for i, oid in enumerate(sorted_ids):
        vc = vote_count[oid]
        fc = first_count[oid]
        if vc != prev_vc:            # 同票数同名次；不同则虚位递推
            prev_display_rank = i + 1
            prev_vc = vc
        vp = vc / total_voters if total_voters else 0.0
        fp = fc / vc if vc else 0.0
        fpa = fc / total_first if total_first else 0.0

        # 百分比字段全部是 0..1 的分数(旧网关口径,前端 toPercentageString
        # 自己 *100 拼 '%')——不要在这里预乘 100,否则前端会再乘一次到 8000%。
        rank_snapshots = [{
            "rank": i + 1,
            "vote_count": vc,
            "favorite_vote_count": fc,
            "favorite_percentage": round(fp, 4),
            "vote_percentage": round(vp, 4),
        }]
        hist = historical.get(whitelist.name_of(oid), {})
        for suffix in ("1", "2"):
            if hist.get(f"rank_{suffix}"):
                hvc = hist[f"votes_{suffix}"]
                hfc = hist[f"first_{suffix}"]
                rank_snapshots.append({
                    "rank": hist[f"rank_{suffix}"],
                    "vote_count": hvc,
                    "favorite_vote_count": hfc,
                    "favorite_percentage": round(hfc / hvc, 4) if hvc else 0.0,
                    "vote_percentage": 0.0,
                })

        meta = whitelist.get(oid)
        name = meta.name if meta else oid
        segments = _segment_breakdown(segment_count[oid], vc, segment_totals)
        male_proj, female_proj = _legacy_gender_projection(segments)

        # rank_snapshots[0]["rank"] = i+1，原始 1-based 序号，永不并列；
        # display_rank = 名次（同票数同名次、虚位递推），前端展示用这个。
        ranking.append({
            "rank": rank_snapshots,
            "display_rank": prev_display_rank,
            "id": oid,
            "name": name,
            "favorite_vote_count_weighted": vc + fc,
            "type": (meta.type if meta else "") or "未知",
            "origin": (meta.origin if meta else "") or "未知",
            "first_appearance": (meta.first_appearance if meta else "") or "",
            "album": (meta.album if meta else "") or "",
            "name_jp": (meta.name_jp if meta else "") or "",
            "favorite_percentage": round(fp, 4),
            "favorite_percentage_of_all": round(fpa, 4),
            "segments": segments,
            "male_vote_count": male_proj,
            "female_vote_count": female_proj,
            "reasons": reasons[oid],
            "reasons_count": len(reasons[oid]),
            "trend": [{"hrs": h, "cnt": c} for h, c in enumerate(trend[oid]) if c > 0],
            "trend_first": [
                {"hrs": h, "cnt": c} for h, c in enumerate(trend_first[oid]) if c > 0
            ],
        })

    global_stats = {
        "total_unique_items": len(all_ids),
        "total_first": total_first,
        "total_votes": total_votes,
        "average_votes_per_item": total_votes / len(all_ids) if all_ids else 0.0,
        "median_votes_per_item": _median(list(vote_count.values())),
    }
    return ranking, global_stats


def _median(values: list[int]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return (s[mid] + s[~mid]) / 2.0


# ── CP Ranking ────────────────────────────────────────────────────────


def compute_cp_ranking(
    cp_votes: list[tuple[str, datetime, list[dict]]],
    whitelist: "Whitelist",
    segment_map: dict[str, str],
    historical: dict[str, dict],
    vote_start: datetime,
    total_hours: int,
) -> tuple[list[dict], dict]:
    """按无序 multiset 归票的 CP 排名（B-050）。

    item: {"id_a","id_b","id_c","active","first","reason"}
    key = tuple(sorted([id_a,id_b,id_c?去None]))；顺序/主动方/first 不进 key。
    任一成员不在白名单 → 整条 CP 丢弃；组合票数==1 不计入。
    segment_map: vote_id → 分段标签，用法同 compute_ranking。
    """
    vote_count: dict[tuple, int] = defaultdict(int)
    first_count: dict[tuple, int] = defaultdict(int)
    reasons: dict[tuple, list[str]] = defaultdict(list)
    active_count: dict[tuple, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    segment_count: dict[tuple, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    members_of: dict[tuple, list[str]] = {}
    trend: dict[tuple, list[int]] = defaultdict(lambda: [0] * max(total_hours, 1))
    trend_first: dict[tuple, list[int]] = defaultdict(lambda: [0] * max(total_hours, 1))
    total_voters = len(cp_votes)
    # 每个 label 在本类别(CP)投票人群中的总人数——percentage_per_total 的分母。
    segment_totals = Counter(
        segment_map.get(user_id, "unknown") for user_id, _, _ in cp_votes
    )

    for user_id, submit_dt, items in cp_votes:
        segment = segment_map.get(user_id, "unknown")
        if submit_dt.tzinfo is None:
            submit_dt = submit_dt.replace(tzinfo=timezone.utc)
        hour_bucket = max(0, min(
            int((submit_dt - vote_start).total_seconds() / 3600), total_hours - 1))
        seen_in_vote: set[tuple] = set()
        for item in items:
            raw_members = [item.get("id_a", ""), item.get("id_b", "")]
            if item.get("id_c"):
                raw_members.append(item["id_c"])
            if any((not m) or (m not in whitelist) for m in raw_members):
                continue  # 未知成员 → 整条丢
            key = tuple(sorted(raw_members))  # multiset，保留重复
            if key in seen_in_vote:
                continue
            seen_in_vote.add(key)
            is_first = bool(item.get("first", False))
            reason = item.get("reason")
            active = item.get("active") or "none"

            vote_count[key] += 1
            if is_first:
                first_count[key] += 1
            if reason:
                reasons[key].append(reason)
            active_count[key][active] += 1
            segment_count[key][segment] += 1
            trend[key][hour_bucket] += 1
            if is_first:
                trend_first[key][hour_bucket] += 1
            members_of.setdefault(key, list(key))

    # 组合票数==1 不计入
    all_keys = [k for k in vote_count if vote_count[k] >= 2]
    total_votes = sum(vote_count[k] for k in all_keys)
    # 提示：sum(first_count[k] for k in all_keys) 在 favorite_percentage_of_all
    # 与 global_stats 中重复用到；一次性算好复用，避免 O(n^2)（brief 原文是逐条重算）。
    total_first_cp = sum(first_count[k] for k in all_keys)

    def system_id_a(k: tuple) -> int:
        return whitelist.system_id_of(members_of[k][0])

    sorted_keys = sorted(
        all_keys,
        key=lambda k: (-vote_count[k], -first_count[k], system_id_a(k)),
    )

    ranking = []
    prev_vc = None
    prev_display_rank = 0
    for i, key in enumerate(sorted_keys):
        vc = vote_count[key]
        fc = first_count[key]
        if vc != prev_vc:
            prev_display_rank = i + 1
            prev_vc = vc
        members = members_of[key]
        a = members[0]
        b = members[1] if len(members) > 1 else ""
        c = members[2] if len(members) > 2 else None
        ac = active_count[key]
        segments = _segment_breakdown(segment_count[key], vc, segment_totals)
        male_proj, female_proj = _legacy_gender_projection(segments)

        def _rate(mid: str) -> float:
            return round(ac.get(mid, 0) / vc, 4) if vc else 0.0

        # "rank" 内的 rank = i+1，原始 1-based 序号，永不并列；
        # display_rank = 名次（同票数同名次、虚位递推），前端展示用这个。
        # 百分比字段全部是 0..1 的分数,与角色/音乐口径一致(见 compute_ranking
        # 里的同款注释)。
        ranking.append({
            "rank": [{
                "rank": i + 1,
                "vote_count": vc,
                "favorite_vote_count": fc,
                "favorite_percentage": round(fc / vc, 4) if vc else 0.0,
                "vote_percentage": (
                    round(vc / total_voters, 4) if total_voters else 0.0
                ),
            }],
            "display_rank": prev_display_rank,
            "name": "×".join(whitelist.name_of(m) for m in members),
            "id_a": a,
            "id_b": b,
            "id_c": c,
            "favorite_vote_count_weighted": vc + fc,
            "favorite_percentage": round(fc / vc, 4) if vc else 0.0,
            "favorite_percentage_of_all": (
                round(fc / total_first_cp, 4) if total_first_cp else 0.0
            ),
            "segments": segments,
            "male_vote_count": male_proj,
            "female_vote_count": female_proj,
            "active_a": _rate(a),
            "active_b": _rate(b) if b else 0.0,
            "active_c": _rate(c) if c else 0.0,
            "active_none": _rate("none"),
            "reasons": reasons[key],
            "reasons_count": len(reasons[key]),
            "trend": [
                {"hrs": h, "cnt": cc} for h, cc in enumerate(trend[key]) if cc > 0
            ],
            "trend_first": [
                {"hrs": h, "cnt": cc} for h, cc in enumerate(trend_first[key]) if cc > 0
            ],
        })

    global_stats = {
        "total_unique_items": len(all_keys),
        "total_first": total_first_cp,
        "total_votes": total_votes,
        "average_votes_per_item": total_votes / len(all_keys) if all_keys else 0.0,
        "median_votes_per_item": _median([vote_count[k] for k in all_keys]),
    }
    return ranking, global_stats


# ── Global Stats ──────────────────────────────────────────────────────


def compute_global_stats(
    char_votes: list[tuple[str, datetime, list[dict]]],
    music_votes: list[tuple[str, datetime, list[dict]]],
    cp_votes: list[tuple[str, datetime, list[dict]]],
    questionnaire_votes: list[tuple[str, list[dict]]],
    segment_map: dict[str, str],
) -> dict[str, Any]:
    char_users = {uid for uid, _, _ in char_votes}
    music_users = {uid for uid, _, _ in music_votes}
    cp_users = {uid for uid, _, _ in cp_votes}
    q_users = {uid for uid, _ in questionnaire_votes}
    all_users = char_users | music_users | cp_users | q_users
    male = sum(1 for uid in all_users if segment_map.get(uid) == "male")
    female = sum(1 for uid in all_users if segment_map.get(uid) == "female")
    finished = char_users & music_users
    return {
        "num_vote": len(all_users),
        "num_char": len(char_users),
        "num_music": len(music_users),
        "num_cp": len(cp_users),
        "num_doujin": 0,
        "num_male": male,
        "num_female": female,
        "num_finished_voting": len(finished),
        "num_finished_paper": len(q_users),
    }


# ── Completion Rates ──────────────────────────────────────────────────


def compute_completion_rates(
    char_votes: list[tuple[str, datetime, list[dict]]],
    music_votes: list[tuple[str, datetime, list[dict]]],
    cp_votes: list[tuple[str, datetime, list[dict]]],
    questionnaire_votes: list[tuple[str, list[dict]]],
    all_voters: set[str],
) -> dict[str, dict]:
    """各分类的完成率，附带分子/分母（供 CompletionRateItem 直接消费）。

    返回 {category: {"rate": float, "num_complete": int, "total": int}}。
    ``total`` 对所有分类相同（都是 all_voters 的规模），分子是该分类投票者
    与 all_voters 的交集大小。
    """
    total = len(all_voters)

    def _item(voters: set[str]) -> dict:
        num_complete = len(voters & all_voters)
        return {
            "rate": (num_complete / total) if total else 0.0,
            "num_complete": num_complete,
            "total": total,
        }

    return {
        "character": _item({uid for uid, _, _ in char_votes}),
        "music": _item({uid for uid, _, _ in music_votes}),
        "cp": _item({uid for uid, _, _ in cp_votes}),
        "questionnaire": _item({uid for uid, _ in questionnaire_votes}),
    }


# ── Paper (Questionnaire) Results ─────────────────────────────────────


def compute_paper_results(
    questionnaire_votes: list[tuple[str, list[dict]]],
    segment_map: dict[str, str],
) -> dict[str, dict]:
    """Compute per-question statistics (incl. gender crosstab) from questionnaire votes.

    Returns {question_id: {"answers_cat": [...], "answers_str": [...], "total": int,
    "total_male": int, "total_female": int}}，其中 answers_cat 项另带
    male_votes/female_votes。

    简化说明（与设计稿的偏差，见 CHANGELOG）：聚合按**答案形状**分派——`answer`
    是非空 list → 按选项计数；`answer_str` 非空 → 收字符串——不引入
    `question_def.type` 映射。形状已经足以区分单选/多选/填空题，引入类型表只
    会多一次 DB 往返，没有实际收益。
    """
    question_cat: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    question_cat_gender: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"male": 0, "female": 0})
    )
    question_str: dict[str, list[str]] = defaultdict(list)
    question_total: dict[str, int] = defaultdict(int)
    question_gender_total: dict[str, dict[str, int]] = defaultdict(
        lambda: {"male": 0, "female": 0}
    )

    for user_id, q_list in questionnaire_votes:
        segment = segment_map.get(user_id, "unknown")
        for item in q_list:
            qid = str(item.get("id", ""))
            if not qid:
                continue
            question_total[qid] += 1
            if segment == "male":
                question_gender_total[qid]["male"] += 1
            elif segment == "female":
                question_gender_total[qid]["female"] += 1
            ans = item.get("answer")
            ans_str = item.get("answer_str")
            if isinstance(ans, list):
                for a in ans:
                    aid = str(a)
                    question_cat[qid][aid] += 1
                    if segment == "male":
                        question_cat_gender[qid][aid]["male"] += 1
                    elif segment == "female":
                        question_cat_gender[qid][aid]["female"] += 1
            if ans_str and str(ans_str).strip() and str(ans_str).strip() != "无":
                question_str[qid].append(str(ans_str).strip())

    result: dict[str, dict] = {}
    for qid in question_total:
        result[qid] = {
            "question_id": qid,
            "answers_cat": [
                {
                    "aid": k,
                    "count": v,
                    "male_votes": question_cat_gender[qid][k]["male"],
                    "female_votes": question_cat_gender[qid][k]["female"],
                }
                for k, v in question_cat[qid].items()
            ],
            "answers_str": question_str[qid],
            "total": question_total[qid],
            "total_male": question_gender_total[qid]["male"],
            "total_female": question_gender_total[qid]["female"],
        }
    return result


# ── Covote ────────────────────────────────────────────────────────────


def compute_covote(
    votes: list[tuple[str, datetime, list[dict]]],
    whitelist: "Whitelist",
    top_k: int = 100,
) -> list[dict]:
    """Compute pairwise co-vote statistics for the top-k whitelisted entities.

    id 先经白名单过滤（不在白名单的 id 直接丢弃，不参与配对），输出的
    ``a``/``b`` 用 ``whitelist.name_of()`` 转成人名，而不是原始 8 位 hash id。
    """
    vote_count: dict[str, int] = defaultdict(int)
    user_voted: dict[str, set[str]] = {}

    for user_id, _, items in votes:
        ids = {
            item.get("id", "") for item in items
            if item.get("id") and item["id"] in whitelist
        }
        user_voted[user_id] = ids
        for oid in ids:
            vote_count[oid] += 1

    top_ids = sorted(vote_count, key=lambda n: -vote_count[n])[:top_k]
    total = len(user_voted)

    result = []
    for a, b in combinations(top_ids, 2):
        # a/b 都来自 top_ids 本身，天然在 top_set 里；非白名单 id 已在上面的
        # user_voted 构造阶段被过滤掉，这里不需要再判一次 in top_set。
        voters_a = {uid for uid, ids in user_voted.items() if a in ids}
        voters_b = {uid for uid, ids in user_voted.items() if b in ids}
        m11 = len(voters_a & voters_b)
        m10 = len(voters_a - voters_b)
        m01 = len(voters_b - voters_a)
        m00 = total - m11 - m10 - m01
        union = m11 + m10 + m01
        cv = m11 / union if union else 0.0
        result.append(
            {
                "a": whitelist.name_of(a),
                "b": whitelist.name_of(b),
                "m00": m00,
                "m01": m01,
                "m10": m10,
                "m11": m11,
                "cv": round(cv, 4),
                # cs/mi: 契约类型已声明字段，但相关性/互信息统计本轮未实现
                # （前端 connect 页仍是占位、无消费方），先置 0，待有消费方
                # 再补真实计算。
                "cs": 0.0,
                "mi": 0.0,
            }
        )

    return sorted(result, key=lambda x: -x["cv"])
