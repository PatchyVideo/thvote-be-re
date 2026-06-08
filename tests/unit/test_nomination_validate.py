"""Unit tests for nomination pure validation helpers."""
from datetime import datetime, timezone


def test_extract_domain():
    from src.apps.submit.nomination_service import extract_domain
    assert extract_domain("https://www.bilibili.com/video/BV1?x=1") == "bilibili.com"
    assert extract_domain("http://youtube.com/watch") == "youtube.com"
    assert extract_domain("not a url") is None


def test_domain_allowed():
    from src.apps.submit.nomination_service import domain_allowed
    allow = ["bilibili.com", "youtube.com"]
    assert domain_allowed("https://www.bilibili.com/x", allow) is True
    assert domain_allowed("https://evil.com/x", allow) is False
    # empty allowlist → everything allowed
    assert domain_allowed("https://anything.com", []) is True
    # subdomain of allowed host
    assert domain_allowed("https://m.bilibili.com/x", allow) is True


def test_within_window():
    from src.apps.submit.nomination_service import within_window
    s = "2026-01-01T00:00:00+00:00"
    e = "2026-12-31T23:59:59+00:00"
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    assert within_window(now, s, e) is True
    before = datetime(2025, 6, 1, tzinfo=timezone.utc)
    assert within_window(before, s, e) is False
    # missing bounds → treated as open
    assert within_window(now, None, None) is True


def test_publish_date_eligible():
    from src.apps.submit.nomination_service import publish_date_eligible
    pub = datetime(2026, 3, 1, tzinfo=timezone.utc)
    assert publish_date_eligible(
        pub, "2026-01-01T00:00:00+00:00", "2026-12-31T00:00:00+00:00"
    ) is True
    assert publish_date_eligible(pub, "2027-01-01T00:00:00+00:00", None) is False
    # unknown publish date → eligible (defer to manual review)
    assert publish_date_eligible(None, "2026-01-01T00:00:00+00:00", None) is True
