"""Account-management mutations must stay wired with the EXACT GraphQL field
and argument names the frontend (UserSettings.vue) sends.

A rename or arg-type drift here silently turns into a frontend
``Cannot query field ...`` (which also crashes its error handler), the same
class of contract break that caused the login bounce.  Pin the SDL.
"""

from __future__ import annotations

import pytest

from src.api.graphql.schema import schema

# Exact signatures the frontend depends on (Strawberry camelCases the args).
EXPECTED_SIGNATURES = [
    "updateNickname(userToken: String!, newNickname: String!): Boolean!",
    "updatePassword(userToken: String!, newPassword: String!, "
    "oldPassword: String = null): Boolean!",
    "updatePhone(userToken: String!, phone: String!, verifyCode: String!): Boolean!",
    "updateEmail(userToken: String!, email: String!, verifyCode: String!): Boolean!",
]


@pytest.mark.parametrize("signature", EXPECTED_SIGNATURES)
def test_account_mutation_exposed_with_frontend_contract(signature: str) -> None:
    sdl = schema.as_str()
    assert signature in sdl, f"missing or renamed mutation: {signature}"
