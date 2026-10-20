"""Unit tests: structured questionnaire answer validation (R-01/D-08).

The GraphQL payload is a JSON scalar, so these checks are the only thing that
stops forged answer rows (made-up ids / another questionnaire's group / unknown
options) from being stored and then unlocking voting.
"""
import pytest

from src.apps.questionnaire.validation import validate_answer_rows
from src.common.exceptions import ValidationError


def structure() -> dict:
    return {"questionnaires": [
        {
            "id": 1, "key": "main", "category": "main", "required": True, "order": 1,
            "questionGroups": [
                {"id": 10, "order": 1, "hiddenByDefault": False, "questions": [
                    {"id": 100, "type": "Single", "maxInputLen": 100, "options": [
                        {"id": 1000, "relatedQuestionIds": []},
                        {"id": 1001, "relatedQuestionIds": []},
                    ]},
                ]},
                {"id": 11, "order": 2, "hiddenByDefault": False, "questions": [
                    {"id": 110, "type": "Input", "maxInputLen": 20, "options": []},
                ]},
                {"id": 12, "order": 3, "hiddenByDefault": True, "questions": [
                    {"id": 120, "type": "Single", "options": [
                        {"id": 1200, "relatedQuestionIds": []},
                    ]},
                ]},
            ],
        },
        {
            "id": 2, "key": "extra", "category": "extra", "required": False,
            "order": 2,
            "questionGroups": [
                {"id": 20, "order": 1, "hiddenByDefault": False, "questions": [
                    {"id": 200, "type": "Single", "options": [{"id": 2000}]},
                ]},
            ],
        },
    ]}


def row(**over) -> dict:
    base = {
        "questionnaire_id": 1,
        "group_id": 10,
        "active_question_id": 100,
        "selected_option_ids": [1000],
        "input_text": "",
    }
    base.update(over)
    return base


def _assert_invalid(rows):
    with pytest.raises(ValidationError) as ei:
        validate_answer_rows(structure(), rows)
    assert ei.value.message == "INVALID_PAPER_ANSWER"
    return str(ei.value.human_readable_message)


def test_valid_rows_pass():
    validate_answer_rows(structure(), [
        row(),
        row(group_id=11, active_question_id=110, selected_option_ids=[], input_text="x"),
    ])


def test_untouched_group_row_passes():
    """The frontend submits one row per group, untouched ones are all-empty."""
    validate_answer_rows(structure(), [
        row(group_id=12, active_question_id=None, selected_option_ids=[], input_text=""),
    ])


def test_unknown_group_rejected():
    msg = _assert_invalid([row(group_id=999)])
    assert "题组999" in msg


def test_unknown_questionnaire_rejected():
    msg = _assert_invalid([row(questionnaire_id=99)])
    assert "不属于问卷99" in msg


def test_group_of_another_questionnaire_rejected():
    """(questionnaire 2, group of questionnaire 1) must not alias."""
    msg = _assert_invalid([row(questionnaire_id=2, group_id=10)])
    assert "不属于问卷2" in msg


def test_question_of_another_group_rejected():
    msg = _assert_invalid([row(group_id=10, active_question_id=110)])
    assert "题目110" in msg


def test_unknown_option_rejected():
    msg = _assert_invalid([row(selected_option_ids=[999999])])
    assert "选项999999" in msg


def test_option_of_another_question_rejected():
    msg = _assert_invalid([
        row(group_id=10, active_question_id=100, selected_option_ids=[2000]),
    ])
    assert "选项2000" in msg


def test_option_without_active_question_rejected():
    msg = _assert_invalid([
        row(active_question_id=None, selected_option_ids=[1000]),
    ])
    assert "未选择题目" in msg


def test_text_without_active_question_rejected():
    msg = _assert_invalid([
        row(active_question_id=None, selected_option_ids=[], input_text="hi"),
    ])
    assert "未选择题目" in msg


def test_duplicate_rows_rejected():
    msg = _assert_invalid([row(), row()])
    assert "重复作答" in msg


def test_duplicate_option_rejected():
    msg = _assert_invalid([row(selected_option_ids=[1000, 1000])])
    assert "重复选择选项" in msg


def test_input_over_max_len_rejected():
    msg = _assert_invalid([
        row(group_id=11, active_question_id=110, selected_option_ids=[],
            input_text="x" * 21),
    ])
    assert "20" in msg


def test_input_at_max_len_passes():
    validate_answer_rows(structure(), [
        row(group_id=11, active_question_id=110, selected_option_ids=[],
            input_text="x" * 20),
    ])


@pytest.mark.parametrize("bad", ["1", 1.5, True, None])
def test_non_integer_ids_rejected(bad):
    _assert_invalid([row(questionnaire_id=bad)])
