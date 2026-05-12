"""Contract: router exposes the 12 expected endpoints with matching HTTP methods.

This test does NOT hit a database or Redis; it inspects the FastAPI app's
route table only.  The goal is to detect accidental endpoint removals or
method changes during refactoring.
"""

from __future__ import annotations

import pytest

from src.apps.user.router import router

EXPECTED = {
    ("POST", "/user/login-email-password"),
    ("POST", "/user/login-email"),
    ("POST", "/user/login-phone"),
    ("POST", "/user/send-email-code"),
    ("POST", "/user/send-sms-code"),
    ("POST", "/user/update-email"),
    ("POST", "/user/update-phone"),
    ("POST", "/user/update-nickname"),
    ("POST", "/user/update-password"),
    ("POST", "/user/token-status"),
    ("POST", "/user/remove-voter"),
    ("GET", "/user/me"),
}


def test_router_registers_exact_set_of_endpoints() -> None:
    actual = set()
    for route in router.routes:
        for method in route.methods or set():
            if method in {"HEAD", "OPTIONS"}:
                continue
            actual.add((method, route.path))

    assert actual == EXPECTED, f"unexpected diff: {actual ^ EXPECTED}"


@pytest.mark.parametrize(
    "removed_path",
    ["/user/login", "/user/login/email", "/user/register", "/user/{user_id}"],
)
def test_legacy_endpoints_are_gone(removed_path: str) -> None:
    paths = {r.path for r in router.routes}
    assert removed_path not in paths, f"legacy endpoint still registered: {removed_path}"
