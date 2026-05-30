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
    for expected in {
        "requestPhoneCode",
        "requestEmailCode",
        "loginPhone",
        "loginEmail",
        "loginEmailPassword",
    }:
        assert expected in names, f"missing mutation {expected}"
    # submit mutations must still be present
    assert "submitCharacter" in names
