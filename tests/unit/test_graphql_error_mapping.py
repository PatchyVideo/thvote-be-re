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
    # mapped to a user-facing message (was None before, caused frontend "原因：null")
    assert ext["human_readable_message"] == "密码错误"


@pytest.mark.asyncio
async def test_unmapped_error_kind_has_null_human_readable():
    with pytest.raises(GraphQLError) as ei:
        async with map_app_errors(service="user-manager"):
            raise ValidationError("SOME_NEW_KIND", details=400)
    assert ei.value.extensions["human_readable_message"] is None


@pytest.mark.asyncio
async def test_remap_translates_kind_and_its_human_message():
    # update_phone surfaces the service's USER_ALREADY_EXIST as PHONE_IN_USE,
    # and the human message must follow the *remapped* kind.
    with pytest.raises(GraphQLError) as ei:
        async with map_app_errors(
            service="user-manager", remap={"USER_ALREADY_EXIST": "PHONE_IN_USE"}
        ):
            raise ValidationError("USER_ALREADY_EXIST", details=409)
    ext = ei.value.extensions
    assert ext["error_kind"] == "PHONE_IN_USE"
    assert ext["human_readable_message"] == "该手机号已被使用"


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


def test_client_ip_from_object_context():
    class _C:
        host = "8.8.8.8"

    class _R:
        client = _C()
        headers: dict = {}

    class _Ctx:
        request = _R()

    class _Info:
        context = _Ctx()

    assert _client_ip_from_info(_Info()) == "8.8.8.8"
