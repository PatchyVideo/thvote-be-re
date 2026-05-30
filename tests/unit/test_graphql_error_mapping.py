import pytest
from fastapi import HTTPException
from graphql import GraphQLError

from src.api.graphql.resolvers.user import _client_ip_from_info, map_app_errors
from src.common.exceptions import RateLimitError, ValidationError


@pytest.mark.asyncio
async def test_maps_appexception_to_rust_extension_shape():
    with pytest.raises(GraphQLError) as ei:
        async with map_app_errors(service="user-manager"):
            raise ValidationError("INCORRECT_PASSWORD", details=400)
    ext = ei.value.extensions
    assert ext["service"] == "user-manager"
    assert ext["error_kind"] == "INCORRECT_PASSWORD"
    assert ext["url"] is None
    assert ext["human_readable_message"] is None


@pytest.mark.asyncio
async def test_passes_upstream_fields_through():
    with pytest.raises(GraphQLError) as ei:
        async with map_app_errors(service="sms-service"):
            raise RateLimitError(
                "REQUEST_TOO_FREQUENT", details=429,
                error_message="m", upstream_response_string="isv.X",
            )
    ext = ei.value.extensions
    assert ext["error_kind"] == "REQUEST_TOO_FREQUENT"
    assert ext["error_message"] == "m"
    assert ext["upstream_response_string"] == "isv.X"


@pytest.mark.asyncio
async def test_maps_ratelimit_httpexception_detail_to_error_kind():
    with pytest.raises(GraphQLError) as ei:
        async with map_app_errors(service="user-manager"):
            raise HTTPException(status_code=429, detail="REQUEST_TOO_FREQUENT")
    assert ei.value.extensions["error_kind"] == "REQUEST_TOO_FREQUENT"


@pytest.mark.asyncio
async def test_unexpected_exception_maps_to_internal_error():
    with pytest.raises(GraphQLError) as ei:
        async with map_app_errors(service="user-manager"):
            raise RuntimeError("boom")
    assert ei.value.extensions["error_kind"] == "INTERNAL_ERROR"


def test_client_ip_from_dict_context():
    class _C:
        host = "9.9.9.9"

    class _R:
        client = _C()
        headers: dict = {}

    class _Info:
        context = {"request": _R()}

    assert _client_ip_from_info(_Info()) == "9.9.9.9"
