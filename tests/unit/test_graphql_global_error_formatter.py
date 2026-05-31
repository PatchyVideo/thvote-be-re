"""AppGraphQLRouter must backfill an extensions block on errors that bypass
map_app_errors (schema validation, parse errors, unwrapped resolver crashes),
so the frontend can always read extensions.error_kind without crashing.
"""

from __future__ import annotations

import pytest
from graphql import GraphQLError
from strawberry.types.execution import ExecutionResult

from src.api.graphql.http import AppGraphQLRouter
from src.api.graphql.schema import schema


@pytest.fixture
def router() -> AppGraphQLRouter:
    return AppGraphQLRouter(schema)


async def _process(router: AppGraphQLRouter, *errors: GraphQLError) -> list[dict]:
    result = ExecutionResult(data=None, errors=list(errors))
    out = await router.process_result(None, result)
    return out["errors"]


@pytest.mark.asyncio
async def test_validation_error_gets_bad_request_extensions(router) -> None:
    # graphql-core validation errors have no original_error and no extensions.
    errs = await _process(router, GraphQLError("Cannot query field 'x' on Mutation"))
    ext = errs[0]["extensions"]
    assert ext["error_kind"] == "BAD_REQUEST"
    assert ext["human_readable_message"]  # non-empty user-facing text
    # validation message is safe to keep (helps debugging a bad query)
    assert "Cannot query field" in errs[0]["message"]


@pytest.mark.asyncio
async def test_unwrapped_runtime_error_is_masked_as_internal(router) -> None:
    err = GraphQLError(
        "boom: secret connection string", original_error=ValueError("secret")
    )
    errs = await _process(router, err)
    ext = errs[0]["extensions"]
    assert ext["error_kind"] == "INTERNAL_ERROR"
    # raw message must NOT leak to the client
    assert errs[0]["message"] == "Internal server error"
    assert "secret" not in errs[0]["message"]


@pytest.mark.asyncio
async def test_already_shaped_error_is_left_untouched(router) -> None:
    err = GraphQLError(
        "Error",
        extensions={"error_kind": "INCORRECT_PASSWORD", "service": "user-manager"},
    )
    errs = await _process(router, err)
    # map_app_errors already set error_kind — formatter must not overwrite it
    assert errs[0]["extensions"]["error_kind"] == "INCORRECT_PASSWORD"
    assert errs[0]["extensions"]["service"] == "user-manager"


@pytest.mark.asyncio
async def test_successful_result_is_unchanged(router) -> None:
    result = ExecutionResult(data={"ok": True}, errors=None)
    out = await router.process_result(None, result)
    assert out["data"] == {"ok": True}
    assert not out.get("errors")
