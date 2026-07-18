"""Pure compute functions for result aggregation.

All functions here are side-effect-free: they take data as arguments and
return computed results. No database or Redis access.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.apps.result.whitelist import Whitelist

KIND_MAPPING: dict[str, str] = {
    "old": "旧作",
    "new": "新作",
    "CD": "专辑",
    "book": "出版物",
    "others": "其他",
    "other": "其他",
    "game": "游戏",
}


@dataclass
class CandidateMeta:
    name: str
    name_jp: str
    origin: str
    type: str
    first_appearance: str | None
    album: str | None = None


# ── Gender ────────────────────────────────────────────────────────────


def compute_gender_map(
    questionnaire_votes: list[tuple[str, list[dict]]],
    gender_question_id: str,
    gender_male_value: str,
    gender_female_value: str,
) -> dict[str, str]:
    """Map user_id → 'male' | 'female' | 'unknown' from questionnaire data."""
    result: dict[str, str] = {}
    for user_id, q_list in questionnaire_votes:
        gender = "unknown"
        for item in q_list:
            if item.get("id") == gender_question_id:
                ans = item.get("answer")
                val = (
                    (ans[0] if isinstance(ans, list) and ans else None)
                    or item.get("answer_str")
                    or ""
                )
                if val == gender_male_value:
                    gender = "male"
                elif val == gender_female_value:
                    gender = "female"
                break
        result[user_id] = gender
    return result


# ── Character / Music Ranking ─────────────────────────────────────────


def compute_ranking(
    votes: list[tuple[str, datetime, list[dict]]],
    whitelist: "Whitelist",
    gender_map: dict[str, str],
    historical: dict[str, dict],
    vote_start: datetime,
    total_hours: int,
) -> tuple[list[dict], dict]:
    """按 id 归票的角色/音乐排名（B-050）。

    votes: (vote_id, submit_datetime, items)，item = {"id", "first", "reason"}
    whitelist: id 白名单/展示注册表；不在白名单的 id 直接丢弃。
    历史键仍按 name（final_ranking 是 name-keyed）；v1 传空 dict。
    返回 (ranking_list, global_stats_dict)
    """
    vote_count: dict[str, int] = defaultdict(int)      # 按 oid
    first_count: dict[str, int] = defaultdict(int)
    reasons: dict[str, list[str]] = defaultdict(list)
    male_count: dict[str, int] = defaultdict(int)
    female_count: dict[str, int] = defaultdict(int)
    trend: dict[str, list[int]] = defaultdict(lambda: [0] * max(total_hours, 1))
    trend_first: dict[str, list[int]] = defaultdict(lambda: [0] * max(total_hours, 1))
    total_voters = len(votes)

    for user_id, submit_dt, items in votes:
        gender = gender_map.get(user_id, "unknown")
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
            if gender == "male":
                male_count[oid] += 1
            elif gender == "female":
                female_count[oid] += 1
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

        rank_snapshots = [{
            "rank": i + 1,
            "vote_count": vc,
            "favorite_vote_count": fc,
            "favorite_percentage": int(fp * 100),
            "vote_percentage": round(vp * 100, 2),
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
                    "favorite_percentage": int(hfc / hvc * 100) if hvc else 0,
                    "vote_percentage": 0.0,
                })

        mc = male_count[oid]
        fc_gender = female_count[oid]
        meta = whitelist.get(oid)
        name = meta.name if meta else oid

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
            "favorite_percentage": round(fp * 100, 2),
            "favorite_percentage_of_all": round(fpa * 100, 2),
            "male_vote_count": {
                "vote_count": mc,
                "percentage_per_char": round(mc / vc, 4) if vc else 0.0,
                "percentage_per_total": round(mc / total_voters, 4) if total_voters else 0.0,
            },
            "female_vote_count": {
                "vote_count": fc_gender,
                "percentage_per_char": round(fc_gender / vc, 4) if vc else 0.0,
                "percentage_per_total": round(fc_gender / total_voters, 4) if total_voters else 0.0,
            },
            "reasons": reasons[oid],
            "reasons_count": len(reasons[oid]),
            "trend": [{"hrs": h, "cnt": c} for h, c in enumerate(trend[oid]) if c > 0],
            "trend_first": [{"hrs": h, "cnt": c} for h, c in enumerate(trend_first[oid]) if c > 0],
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
    gender_map: dict[str, str],
    historical: dict[str, dict],
    vote_start: datetime,
    total_hours: int,
) -> tuple[list[dict], dict]:
    """按无序 multiset 归票的 CP 排名（B-050）。

    item: {"id_a","id_b","id_c","active","first","reason"}
    key = tuple(sorted([id_a,id_b,id_c?去None]))；顺序/主动方/first 不进 key。
    任一成员不在白名单 → 整条 CP 丢弃；组合票数==1 不计入。
    """
    vote_count: dict[tuple, int] = defaultdict(int)
    first_count: dict[tuple, int] = defaultdict(int)
    reasons: dict[tuple, list[str]] = defaultdict(list)
    active_count: dict[tuple, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    members_of: dict[tuple, list[str]] = {}
    trend: dict[tuple, list[int]] = defaultdict(lambda: [0] * max(total_hours, 1))
    trend_first: dict[tuple, list[int]] = defaultdict(lambda: [0] * max(total_hours, 1))
    total_voters = len(cp_votes)

    for user_id, submit_dt, items in cp_votes:
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

        def _rate(mid: str) -> float:
            return round(ac.get(mid, 0) / vc, 4) if vc else 0.0

        ranking.append({
            "rank": [{
                "rank": i + 1,
                "vote_count": vc,
                "favorite_vote_count": fc,
                "favorite_percentage": int(fc / vc * 100) if vc else 0,
                "vote_percentage": round(vc / total_voters * 100, 2) if total_voters else 0.0,
            }],
            "display_rank": prev_display_rank,
            "name": "×".join(whitelist.name_of(m) for m in members),
            "id_a": a,
            "id_b": b,
            "id_c": c,
            "favorite_vote_count_weighted": vc + fc,
            "favorite_percentage": round(fc / vc * 100, 2) if vc else 0.0,
            "favorite_percentage_of_all": (
                round(fc / total_first_cp * 100, 2) if total_first_cp else 0.0
            ),
            "active_a": _rate(a),
            "active_b": _rate(b) if b else 0.0,
            "active_c": _rate(c) if c else 0.0,
            "active_none": _rate("none"),
            "reasons": reasons[key],
            "reasons_count": len(reasons[key]),
            "trend": [{"hrs": h, "cnt": cc} for h, cc in enumerate(trend[key]) if cc > 0],
            "trend_first": [{"hrs": h, "cnt": cc} for h, cc in enumerate(trend_first[key]) if cc > 0],
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
    gender_map: dict[str, str],
) -> dict[str, Any]:
    char_users = {uid for uid, _, _ in char_votes}
    music_users = {uid for uid, _, _ in music_votes}
    cp_users = {uid for uid, _, _ in cp_votes}
    q_users = {uid for uid, _ in questionnaire_votes}
    all_users = char_users | music_users | cp_users | q_users
    male = sum(1 for uid in all_users if gender_map.get(uid) == "male")
    female = sum(1 for uid in all_users if gender_map.get(uid) == "female")
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
) -> dict[str, float]:
    total = len(all_voters)
    if total == 0:
        return {"character": 0.0, "music": 0.0, "cp": 0.0, "questionnaire": 0.0}
    return {
        "character": len({uid for uid, _, _ in char_votes} & all_voters) / total,
        "music": len({uid for uid, _, _ in music_votes} & all_voters) / total,
        "cp": len({uid for uid, _, _ in cp_votes} & all_voters) / total,
        "questionnaire": len({uid for uid, _ in questionnaire_votes} & all_voters)
        / total,
    }


# ── Paper (Questionnaire) Results ─────────────────────────────────────


def compute_paper_results(
    questionnaire_votes: list[tuple[str, list[dict]]],
    vote_start: datetime,
    total_hours: int,
) -> dict[str, dict]:
    """Compute per-question statistics from questionnaire votes.

    Returns {question_id: {"answers_cat": [...], "answers_str": [...], "total": int}}
    """
    question_cat: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    question_str: dict[str, list[str]] = defaultdict(list)
    question_total: dict[str, int] = defaultdict(int)

    for user_id, q_list in questionnaire_votes:
        for item in q_list:
            qid = str(item.get("id", ""))
            if not qid:
                continue
            question_total[qid] += 1
            ans = item.get("answer")
            ans_str = item.get("answer_str")
            if isinstance(ans, list):
                for a in ans:
                    question_cat[qid][str(a)] += 1
            if ans_str and str(ans_str).strip() and str(ans_str).strip() != "无":
                question_str[qid].append(str(ans_str).strip())

    result: dict[str, dict] = {}
    for qid in question_total:
        result[qid] = {
            "question_id": qid,
            "answers_cat": [
                {"aid": k, "count": v} for k, v in question_cat[qid].items()
            ],
            "answers_str": question_str[qid],
            "total": question_total[qid],
        }
    return result


# ── Covote ────────────────────────────────────────────────────────────


def compute_covote(
    votes: list[tuple[str, datetime, list[dict]]],
    top_k: int = 100,
) -> list[dict]:
    """Compute pairwise co-vote statistics for the top-k entities."""
    vote_count: dict[str, int] = defaultdict(int)
    user_voted: dict[str, set[str]] = {}

    for user_id, _, items in votes:
        names = {item.get("id", "") for item in items if item.get("id")}
        user_voted[user_id] = names
        for name in names:
            vote_count[name] += 1

    top_names = sorted(vote_count, key=lambda n: -vote_count[n])[:top_k]
    top_set = set(top_names)
    total = len(user_voted)

    result = []
    for a, b in combinations(top_names, 2):
        voters_a = {
            uid for uid, names in user_voted.items() if a in names and a in top_set
        }
        voters_b = {
            uid for uid, names in user_voted.items() if b in names and b in top_set
        }
        m11 = len(voters_a & voters_b)
        m10 = len(voters_a - voters_b)
        m01 = len(voters_b - voters_a)
        m00 = total - m11 - m10 - m01
        union = m11 + m10 + m01
        cv = m11 / union if union else 0.0
        result.append(
            {
                "a": a,
                "b": b,
                "m00": m00,
                "m01": m01,
                "m10": m10,
                "m11": m11,
                "cv": round(cv, 4),
            }
        )

    return sorted(result, key=lambda x: -x["cv"])
