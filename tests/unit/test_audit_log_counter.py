import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_safe_log_failure_increments_counter():
    """_safe_log must increment _audit_log_failures when ActivityLogDAO raises."""
    import src.apps.user.service as svc_module
    # Reset counter
    svc_module._audit_log_failures = 0

    dao_mock = AsyncMock()
    dao_mock.write = AsyncMock(side_effect=RuntimeError("db gone"))

    from src.apps.user.service import UserService
    svc = object.__new__(UserService)
    svc.activity_dao = dao_mock

    await svc._safe_log(event_type="test_event")

    assert svc_module._audit_log_failures == 1


def test_get_audit_log_failures_returns_current_count():
    import src.apps.user.service as svc_module
    svc_module._audit_log_failures = 3
    from src.apps.user.service import get_audit_log_failures
    assert get_audit_log_failures() == 3
    svc_module._audit_log_failures = 0  # cleanup
