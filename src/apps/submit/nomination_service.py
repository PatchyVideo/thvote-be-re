"""Nomination (dojin) pure validation helpers — no DB, no I/O."""
from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse


def extract_domain(url: str) -> str | None:
    """Return the registrable-ish host (www. stripped), or None if unparseable."""
    try:
        host = urlparse(url).hostname
    except Exception:
        return None
    if not host:
        return None
    return host[4:] if host.startswith("www.") else host


def domain_allowed(url: str, allowlist: list[str]) -> bool:
    """True if url's host is in allowlist (or a subdomain of one).

    Empty allowlist means no restriction (all allowed).
    """
    if not allowlist:
        return True
    dom = extract_domain(url)
    if dom is None:
        return False
    return any(dom == a or dom.endswith("." + a) for a in allowlist)


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def within_window(
    now: datetime, start_iso: str | None, end_iso: str | None
) -> bool:
    """True if now is within [start, end]. None bound = unbounded on that side."""
    start = _parse_iso(start_iso)
    end = _parse_iso(end_iso)
    if start and now < start:
        return False
    if end and now > end:
        return False
    return True


def publish_date_eligible(
    publish_date: datetime | None, start_iso: str | None, end_iso: str | None
) -> bool:
    """True if the work's publish date is within the eligible window.

    Unknown publish date (None) is treated as eligible — defer to manual review.
    """
    if publish_date is None:
        return True
    return within_window(publish_date, start_iso, end_iso)
