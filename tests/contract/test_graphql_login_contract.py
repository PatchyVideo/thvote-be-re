import pytest

from src.api.graphql.schema import schema

INTROSPECT = """
{ __schema { mutationType { fields { name } } } }
"""


@pytest.mark.asyncio
async def test_login_mutations_present_and_camelcase():
    result = await schema.execute(INTROSPECT)
    assert result.errors is None
    names = {f["name"] for f in result.data["__schema"]["mutationType"]["fields"]}
    expected = {
        "requestPhoneCode",
        "requestEmailCode",
        "loginPhone",
        "loginEmail",
        "loginEmailPassword",
    }
    missing = expected - names
    assert not missing, f"missing mutations: {missing}"
    # submit bridge mutations must still be present (old submitCharacter
    # etc. were removed as dead code, 2026-07-14)
    assert "submitCharacterVote" in names


VOTERFE_TYPE = """
{ __type(name: "VoterFE") { fields { name type { kind } } } }
"""


@pytest.mark.asyncio
async def test_voterfe_created_at_is_non_null():
    # createdAt must stay NON_NULL — the Pydantic VoterFE always provides it,
    # so the frontend codegen contract must not treat it as nullable.
    result = await schema.execute(VOTERFE_TYPE)
    assert result.errors is None
    fields = {f["name"]: f for f in result.data["__type"]["fields"]}
    assert fields["createdAt"]["type"]["kind"] == "NON_NULL"
