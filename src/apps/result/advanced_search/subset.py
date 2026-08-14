"""子集圈选:事实索引 + 名字解析 + AST 求值(设计稿 §五/§六)。

数据源与 compute_all 完全同源(ComputeDAO.load_*_votes 已做"每 vote_id
取最新、排除 invalidated"),本模块只做纯内存集合运算。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.apps.result.advanced_search.dsl import (
    And,
    CharAny,
    CharFirst,
    MusicAny,
    MusicFirst,
    Node,
    Or,
    QCond,
)
from src.apps.result.whitelist import Whitelist
from src.common.exceptions import ValidationError

CharMusicVotes = list[tuple[str, datetime, list[dict]]]
QVotes = list[tuple[str, list[dict]]]


@dataclass
class VoteFacts:
    """per-vote 事实索引;id 均为 canonical str(candidate_id)。"""

    char_ids: dict[str, set[str]]
    char_first: dict[str, set[str]]
    music_ids: dict[str, set[str]]
    music_first: dict[str, set[str]]
    q_answers: dict[str, dict[str, set[str]]]
    all_vote_ids: set[str]


def _canon(wl: Whitelist, raw: object) -> str:
    token = str(raw)
    return wl.canonical(token) or token


def build_facts(
    char_votes: CharMusicVotes,
    music_votes: CharMusicVotes,
    cp_votes: CharMusicVotes,
    q_votes: QVotes,
    char_wl: Whitelist,
    music_wl: Whitelist,
) -> VoteFacts:
    char_ids: dict[str, set[str]] = {}
    char_first: dict[str, set[str]] = {}
    for vid, _dt, items in char_votes:
        char_ids[vid] = {_canon(char_wl, it.get("id", "")) for it in items}
        char_first[vid] = {
            _canon(char_wl, it.get("id", "")) for it in items if it.get("first")
        }
    music_ids: dict[str, set[str]] = {}
    music_first: dict[str, set[str]] = {}
    for vid, _dt, items in music_votes:
        music_ids[vid] = {_canon(music_wl, it.get("id", "")) for it in items}
        music_first[vid] = {
            _canon(music_wl, it.get("id", "")) for it in items if it.get("first")
        }
    q_answers: dict[str, dict[str, set[str]]] = {}
    for vid, entries in q_votes:
        per_question: dict[str, set[str]] = {}
        for entry in entries:
            per_question.setdefault(str(entry.get("id", "")), set()).update(
                str(a) for a in (entry.get("answer") or [])
            )
        q_answers[vid] = per_question
    all_vote_ids = (
        set(char_ids) | set(music_ids)
        | {vid for vid, _dt, _items in cp_votes} | set(q_answers)
    )
    return VoteFacts(
        char_ids=char_ids, char_first=char_first,
        music_ids=music_ids, music_first=music_first,
        q_answers=q_answers, all_vote_ids=all_vote_ids,
    )


def _name_index(wl: Whitelist) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for e in wl.entries:
        index.setdefault(e.name, set()).add(str(e.candidate_id))
        if e.name_jp:
            index.setdefault(e.name_jp, set()).add(str(e.candidate_id))
    return index


def resolve_names(
    node: Node, char_wl: Whitelist, music_wl: Whitelist
) -> dict[tuple[str, str], set[str]]:
    """AST 里所有名字 → canonical id 集合;未知名字聚合后一次性报错。

    name 与 name_jp 精确匹配任一即命中;同名撞多条时取并集(投任一即
    满足,与组内 OR 语义一致,设计稿 §十二风险2)。
    """
    char_idx = _name_index(char_wl)
    music_idx = _name_index(music_wl)
    resolved: dict[tuple[str, str], set[str]] = {}
    unknown: list[str] = []

    def visit(n: Node) -> None:
        if isinstance(n, (And, Or)):
            for child in n.children:
                visit(child)
            return
        if isinstance(n, (CharAny, CharFirst)):
            names = n.names if isinstance(n, CharAny) else (n.name,)
            for name in names:
                ids = char_idx.get(name)
                if ids:
                    resolved[("character", name)] = ids
                else:
                    unknown.append(name)
        elif isinstance(n, (MusicAny, MusicFirst)):
            names = n.names if isinstance(n, MusicAny) else (n.name,)
            for name in names:
                ids = music_idx.get(name)
                if ids:
                    resolved[("music", name)] = ids
                else:
                    unknown.append(name)

    visit(node)
    if unknown:
        uniq = list(dict.fromkeys(unknown))
        raise ValidationError(
            "ADVANCED_SEARCH_UNKNOWN_NAME",
            human_readable_message="未知的角色/曲目名: " + "、".join(uniq),
        )
    return resolved


def evaluate_subset(
    node: Node,
    facts: VoteFacts,
    resolved: dict[tuple[str, str], set[str]],
) -> set[str]:
    """对全集逐 vote_id 求 AST 真值,返回满足约束的 vote_id 集合。"""

    def ok(n: Node, vid: str) -> bool:
        if isinstance(n, And):
            return all(ok(c, vid) for c in n.children)
        if isinstance(n, Or):
            return any(ok(c, vid) for c in n.children)
        if isinstance(n, QCond):
            return n.ocode in facts.q_answers.get(vid, {}).get(n.qcode, set())
        if isinstance(n, CharAny):
            voted = facts.char_ids.get(vid, set())
            return any(resolved[("character", nm)] & voted for nm in n.names)
        if isinstance(n, CharFirst):
            return bool(
                resolved[("character", n.name)] & facts.char_first.get(vid, set())
            )
        if isinstance(n, MusicAny):
            voted = facts.music_ids.get(vid, set())
            return any(resolved[("music", nm)] & voted for nm in n.names)
        if isinstance(n, MusicFirst):
            return bool(
                resolved[("music", n.name)] & facts.music_first.get(vid, set())
            )
        raise TypeError(f"unknown AST node: {n!r}")

    return {vid for vid in facts.all_vote_ids if ok(node, vid)}
