"""Unit tests for Task 4 compute gaps.

Covers two small gaps the GraphQL contract layer (Task 5-6) needs:

- ``compute_completion_rates`` must return numerator/denominator alongside
  the rate (``CompletionRateItem`` needs ``num_complete``/``total``, not
  just ``rate``).
- ``compute_covote`` must filter pairs to a whitelist and emit display
  names instead of raw hash ids.
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.apps.result.compute import compute_completion_rates, compute_covote
from src.apps.result.whitelist import Whitelist, WhitelistEntry

VOTE_START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _dt(hour_offset: int) -> datetime:
    return VOTE_START + timedelta(hours=hour_offset)


def _vote(user_id: str, items: list[dict]) -> tuple[str, datetime, list[dict]]:
    return (user_id, _dt(1), items)


def _wl() -> Whitelist:
    return Whitelist([
        WhitelistEntry(
            id="id_a", name="角色甲", name_jp="", origin="", type="",
            first_appearance=None, album=None, system_id=1,
        ),
        WhitelistEntry(
            id="id_b", name="角色乙", name_jp="", origin="", type="",
            first_appearance=None, album=None, system_id=2,
        ),
    ])


CHAR_VOTES = [
    _vote("u1", [{"id": "id_a", "first": True, "reason": None}]),
    _vote("u2", [{"id": "id_a", "first": False, "reason": None}]),
    _vote("u3", [{"id": "id_b", "first": True, "reason": None}]),
]


def test_completion_rates_returns_counts():
    res = compute_completion_rates(CHAR_VOTES, [], [], [], {"u1", "u2", "u3"})
    assert res["character"]["num_complete"] == 3
    assert res["character"]["total"] == 3
    assert res["character"]["rate"] == pytest.approx(1.0)


def test_covote_uses_names_and_filters_whitelist():
    votes = [
        _vote("u1", [{"id": "id_a"}, {"id": "id_b"}, {"id": "UNKNOWN"}]),
        _vote("u2", [{"id": "id_a"}]),
    ]
    items = compute_covote(votes, _wl(), top_k=10)
    names = {n for i in items for n in (i["a"], i["b"])}
    assert names <= {"角色甲", "角色乙"}      # 出人名,且 UNKNOWN 被丢
    assert all(i["cs"] == 0.0 and i["mi"] == 0.0 for i in items)
