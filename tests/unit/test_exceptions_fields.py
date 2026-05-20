from src.common.exceptions import AppException, ValidationError


def test_appexception_carries_optional_diagnostic_fields():
    exc = ValidationError(
        "INVALID_PHONE",
        details=400,
        error_message="bad number",
        upstream_response_string="isv.MOBILE_NUMBER_ILLEGAL",
    )
    assert exc.message == "INVALID_PHONE"
    assert exc.details == 400
    assert exc.error_message == "bad number"
    assert exc.upstream_response_string == "isv.MOBILE_NUMBER_ILLEGAL"


def test_appexception_defaults_diagnostic_fields_to_none():
    exc = AppException("X")
    assert exc.error_message is None
    assert exc.upstream_response_string is None


def test_human_readable_message_roundtrip():
    exc = AppException("INVALID_CONTENT", details=422, human_readable_message="多个本命")
    assert exc.human_readable_message == "多个本命"


def test_human_readable_message_defaults_none():
    assert AppException("X").human_readable_message is None
