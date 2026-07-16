"""SDL contract: request*Code mutations accept optional captchaVerifyParam (B-043).

Optional-with-default keeps the change backward compatible — existing
frontend calls without the argument must keep validating.
"""

import pytest

from src.api.graphql.schema import schema

INTROSPECT_ARGS = """
{ __schema { mutationType { fields { name args { name type { kind name } } } } } }
"""


@pytest.mark.asyncio
async def test_request_code_mutations_take_optional_captcha_param():
    result = await schema.execute(INTROSPECT_ARGS)
    assert result.errors is None
    fields = {
        f["name"]: {a["name"]: a["type"] for a in f["args"]}
        for f in result.data["__schema"]["mutationType"]["fields"]
    }
    for mutation in ("requestPhoneCode", "requestEmailCode"):
        args = fields[mutation]
        assert "captchaVerifyParam" in args, f"{mutation} missing captchaVerifyParam"
        # optional: kind must NOT be NON_NULL (old callers omit it)
        assert args["captchaVerifyParam"]["kind"] != "NON_NULL"
