"""Pure compute functions for result aggregation.

All functions here are side-effect-free: they take data as arguments and
return computed results. No database or Redis access.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations
from typing import Any

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
    candidates: dict[str, CandidateMeta],
    gender_map: dict[str, str],
    historical: dict[str, dict],
    vote_start: datetime,
    total_hours: int,
) -> tuple[list[dict], dict]:
    """Compute character or music ranking.

    votes: list of (user_id, submit_datetime, items)
           each item: {"id": str, "first": bool, "reason": str|None}
    historical: name → {"rank_1", "votes_1", "first_1", "rank_2", "votes_2", "first_2"}
    Returns (ranking_list, global_stats_dict)
    """
    vote_count: dict[str, int] = defaultdict(int)
    first_count: dict[str, int] = defaultdict(int)
    reasons: dict[str, list[str]] = defaultdict(list)
    male_count: dict[str, int] = defaultdict(int)
    female_count: dict[str, int] = defaultdict(int)
    trend: dict[str, list[int]] = defaultdict(lambda: [0] * max(total_hours, 1))
    trend_first: dict[str, list[int]] = defaultdict(lambda: [0] * max(total_hours, 1))
    total_voters = len(votes)

    for user_id, submit_dt, items in votes:
        gender = gender_map.get(user_id, "unknown")
        # ensure submit_dt is timezone-aware for subtraction
        if submit_dt.tzinfo is None:
            submit_dt = submit_dt.replace(tzinfo=timezone.utc)
        hour_bucket = max(
            0,
            min(
                int((submit_dt - vote_start).total_seconds() / 3600),
                total_hours - 1,
            ),
        )
        for item in items:
            name = item.get("id", "")
            if not name:
                continue
            is_first = bool(item.get("first", False))
            reason = item.get("reason")
            vote_count[name] += 1
            if is_first:
                first_count[name] += 1
            if reason:
                reasons[name].append(reason)
            if gender == "male":
                male_count[name] += 1
            elif gender == "female":
                female_count[name] += 1
            trend[name][hour_bucket] += 1
            if is_first:
                trend_first[name][hour_bucket] += 1

    all_names = set(vote_count.keys())
    total_votes = sum(vote_count.values())

    def weighted(name: str) -> int:
        return first_count[name] * 3 + vote_count[name]

    sorted_names = sorted(all_names, key=lambda n: (-weighted(n), -vote_count[n]))

    ranking = []
    prev_weighted = None
    prev_display_rank = 0
    tied_count = 0
    for i, name in enumerate(sorted_names):
        w = weighted(name)
        if w != prev_weighted:
            prev_display_rank = i + 1
            tied_count = 1
            prev_weighted = w
        else:
            tied_count += 1

        vc = vote_count[name]
        fc = first_count[name]
        vp = vc / total_voters if total_voters else 0.0
        fp = fc / vc if vc else 0.0

        rank_snapshots = [
            {
                "rank": i + 1,
                "vote_count": vc,
                "favorite_vote_count": fc,
                "favorite_percentage": int(fp * 100),
                "vote_percentage": round(vp * 100, 2),
            }
        ]
        hist = historical.get(name, {})
        if hist.get("rank_1"):
            h1_vc = hist["votes_1"]
            h1_fc = hist["first_1"]
            rank_snapshots.append(
                {
                    "rank": hist["rank_1"],
                    "vote_count": h1_vc,
                    "favorite_vote_count": h1_fc,
                    "favorite_percentage": int(h1_fc / h1_vc * 100) if h1_vc else 0,
                    "vote_percentage": 0.0,
                }
            )
        if hist.get("rank_2"):
            h2_vc = hist["votes_2"]
            h2_fc = hist["first_2"]
            rank_snapshots.append(
                {
                    "rank": hist["rank_2"],
                    "vote_count": h2_vc,
                    "favorite_vote_count": h2_fc,
                    "favorite_percentage": int(h2_fc / h2_vc * 100) if h2_vc else 0,
                    "vote_percentage": 0.0,
                }
            )

        mc = male_count[name]
        fc_gender = female_count[name]
        meta = candidates.get(name, CandidateMeta(name, "", "未知", "未知", None))

        ranking.append(
            {
                "rank": rank_snapshots,
                "display_rank": prev_display_rank,
                "name": name,
                "favorite_vote_count_weighted": weighted(name),
                "type": meta.type or "未知",
                "origin": meta.origin or "未知",
                "first_appearance": meta.first_appearance or "",
                "album": meta.album or "",
                "name_jp": meta.name_jp or "",
                "favorite_percentage": round(fp * 100, 2),
                "male_vote_count": {
                    "vote_count": mc,
                    "percentage_per_char": round(mc / vc, 4) if vc else 0.0,
                    "percentage_per_total": (
                        round(mc / total_voters, 4) if total_voters else 0.0
                    ),
                },
                "female_vote_count": {
                    "vote_count": fc_gender,
                    "percentage_per_char": round(fc_gender / vc, 4) if vc else 0.0,
                    "percentage_per_total": (
                        round(fc_gender / total_voters, 4) if total_voters else 0.0
                    ),
                },
                "reasons": reasons[name],
                "reasons_count": len(reasons[name]),
                "trend": [
                    {"hrs": h, "cnt": c} for h, c in enumerate(trend[name]) if c > 0
                ],
                "trend_first": [
                    {"hrs": h, "cnt": c}
                    for h, c in enumerate(trend_first[name])
                    if c > 0
                ],
            }
        )

    global_stats = {
        "total_unique_items": len(all_names),
        "total_first": sum(first_count.values()),
        "total_votes": total_votes,
        "average_votes_per_item": total_votes / len(all_names) if all_names else 0.0,
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
    gender_map: dict[str, str],
    historical: dict[str, dict],
    vote_start: datetime,
    total_hours: int,
) -> tuple[list[dict], dict]:
    """Compute CP ranking.

    Each item: {"id_a", "id_b", "id_c", "active", "first", "reason"}
    CP key: "A×B" or "A×B×C"
    """
    vote_count: dict[str, int] = defaultdict(int)
    first_count: dict[str, int] = defaultdict(int)
    reasons: dict[str, list[str]] = defaultdict(list)
    active_count: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    cp_meta: dict[str, dict] = {}
    trend: dict[str, list[int]] = defaultdict(lambda: [0] * max(total_hours, 1))
    trend_first: dict[str, list[int]] = defaultdict(lambda: [0] * max(total_hours, 1))
    total_voters = len(cp_votes)

    for user_id, submit_dt, items in cp_votes:
        if submit_dt.tzinfo is None:
            submit_dt = submit_dt.replace(tzinfo=timezone.utc)
        hour_bucket = max(
            0,
            min(
                int((submit_dt - vote_start).total_seconds() / 3600),
                total_hours - 1,
            ),
        )
        for item in items:
            a = item.get("id_a", "")
            b = item.get("id_b", "")
            c = item.get("id_c")
            key = f"{a}×{b}×{c}" if c else f"{a}×{b}"
            active = item.get("active") or "none"
            is_first = bool(item.get("first", False))
            reason = item.get("reason")

            vote_count[key] += 1
            if is_first:
                first_count[key] += 1
            if reason:
                reasons[key].append(reason)
            active_count[key][active] += 1
            trend[key][hour_bucket] += 1
            if is_first:
                trend_first[key][hour_bucket] += 1
            if key not in cp_meta:
                cp_meta[key] = {"id_a": a, "id_b": b, "id_c": c}

    all_keys = set(vote_count.keys())
    total_votes = sum(vote_count.values())

    def weighted(k: str) -> int:
        return first_count[k] * 3 + vote_count[k]

    sorted_keys = sorted(all_keys, key=lambda k: (-weighted(k), -vote_count[k]))

    ranking = []
    prev_w = None
    prev_dr = 0
    tied_count = 0
    for i, key in enumerate(sorted_keys):
        w = weighted(key)
        if w != prev_w:
            prev_dr = i + 1
            tied_count = 1
            prev_w = w
        else:
            tied_count += 1

        vc = vote_count[key]
        fc = first_count[key]
        ac = active_count[key]
        meta = cp_meta[key]

        def _rate(who: str) -> float:
            return round(ac.get(who, 0) / vc, 4) if vc else 0.0

        ranking.append(
            {
                "rank": [
                    {
                        "rank": i + 1,
                        "vote_count": vc,
                        "favorite_vote_count": fc,
                        "favorite_percentage": int(fc / vc * 100) if vc else 0,
                        "vote_percentage": (
                            round(vc / total_voters * 100, 2) if total_voters else 0.0
                        ),
                    }
                ],
                "display_rank": prev_dr,
                "name": key,
                "id_a": meta["id_a"],
                "id_b": meta["id_b"],
                "id_c": meta["id_c"],
                "favorite_vote_count_weighted": w,
                "favorite_percentage": round(fc / vc * 100, 2) if vc else 0.0,
                "active_a": _rate(meta["id_a"]),
                "active_b": _rate(meta["id_b"]),
                "active_c": _rate(meta["id_c"]) if meta["id_c"] else 0.0,
                "active_none": _rate("none"),
                "reasons": reasons[key],
                "reasons_count": len(reasons[key]),
                "trend": [
                    {"hrs": h, "cnt": c} for h, c in enumerate(trend[key]) if c > 0
                ],
                "trend_first": [
                    {"hrs": h, "cnt": c}
                    for h, c in enumerate(trend_first[key])
                    if c > 0
                ],
            }
        )

    global_stats = {
        "total_unique_items": len(all_keys),
        "total_first": sum(first_count.values()),
        "total_votes": total_votes,
        "average_votes_per_item": total_votes / len(all_keys) if all_keys else 0.0,
        "median_votes_per_item": _median(list(vote_count.values())),
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
