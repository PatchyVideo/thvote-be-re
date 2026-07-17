from src.apps.admin.monitor.scoring import (
    AccountFeatures, score_account, SCORING_WEIGHTS,
)


def _clean() -> AccountFeatures:
    return AccountFeatures(
        min_fill_duration_ms=8000, has_client_env=True, ua_is_scripted=False,
        seconds_register_to_first_vote=120, max_ip_group_size=1,
        max_device_group_size=1, has_duplicate_payload=False,
    )


def test_clean_account_scores_zero():
    result = score_account(_clean())
    assert result.score == 0
    assert result.reasons == []


def test_fast_fill_flags_and_weights():
    f = _clean()
    f.min_fill_duration_ms = 500
    result = score_account(f)
    assert result.score == SCORING_WEIGHTS["fast_fill"]
    assert any("fill" in r or "耗时" in r for r in result.reasons)


def test_signals_are_additive():
    f = _clean()
    f.min_fill_duration_ms = 500          # fast_fill
    f.ua_is_scripted = True               # scripted_ua
    f.max_ip_group_size = 6               # ip_cluster
    expected = (
        SCORING_WEIGHTS["fast_fill"]
        + SCORING_WEIGHTS["scripted_ua"]
        + SCORING_WEIGHTS["ip_cluster"]
    )
    assert score_account(f).score == expected
    assert len(score_account(f).reasons) == 3


def test_missing_client_env_flags():
    f = _clean()
    f.has_client_env = False
    assert score_account(f).score == SCORING_WEIGHTS["no_client_env"]
