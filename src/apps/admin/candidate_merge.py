"""Candidate dedup/merge detection — pure logic, no DB.

Rules (per vote_year):
- character: same name → merge (重名角色合并).
- music: same name → merge regardless of album (同曲名不同专辑合并).

The canonical (kept) row is the smallest id in each name group; every other
row in the group is mapped to it. Returns [(dup_id, canonical_id), ...].
"""
from __future__ import annotations


def detect_merges(category: str, rows: list[dict]) -> list[tuple[int, int]]:
    groups: dict[tuple[int, str], list[int]] = {}
    for r in rows:
        key = (r["vote_year"], r["name"])
        groups.setdefault(key, []).append(r["id"])

    merges: list[tuple[int, int]] = []
    for ids in groups.values():
        if len(ids) < 2:
            continue
        canonical = min(ids)
        for dup in ids:
            if dup != canonical:
                merges.append((dup, canonical))
    return merges
