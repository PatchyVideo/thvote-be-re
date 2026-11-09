"""Tests: per-questionnaire completion and the overall main/extra policy.

Since R-01/D-08 completion also requires *substantive* answers for the groups
the frontend actually renders — a stored but empty row no longer unlocks voting.
"""

import pytest


def _structure(required_groups, required=True):
    return {"questionnaires": [
        {"id": 1, "key": "a", "category": "main", "required": required, "order": 1,
         "questionGroups": [{"id": gid, "order": i, "hiddenByDefault": False,
                             "questions": []}
                            for i, gid in enumerate(required_groups)]},
        {"id": 2, "key": "b", "category": "extra", "required": False, "order": 2,
         "questionGroups": [{"id": 99, "order": 1, "hiddenByDefault": False,
                             "questions": []}]},
    ]}


@pytest.mark.parametrize("groups", [[], [10], [10, 11]])
def test_unconfigured_questionnaires_never_count_as_completed(groups):
    from src.apps.questionnaire.completion import completed_questionnaire_ids, is_complete
    from src.apps.questionnaire.structure_index import StructureIndex

    s = _structure(groups)
    answers = [{"questionnaire_id": 1, "group_id": gid} for gid in groups]
    answers.append({"questionnaire_id": 2, "group_id": 99})
    assert completed_questionnaire_ids(StructureIndex(s), answers) == set()
    assert is_complete(s, answers) is False


def test_incomplete_when_required_group_missing():
    from src.apps.questionnaire.completion import is_complete
    s = real_structure()
    assert is_complete(s, [_row(10, 100, [1000]), _extra_answer()]) is False


def test_unconfigured_stored_rows_with_old_question_ids_do_not_complete():
    from src.apps.questionnaire.completion import is_complete
    from src.apps.questionnaire.validation import validate_answer_rows
    from src.common.exceptions import ValidationError

    s = _structure([10])
    historical = {"questionnaire_id": 1, "group_id": 10,
                  "active_question_id": 100, "selected_option_ids": [1000]}
    assert is_complete(s, [historical, dict(historical),
                           {"questionnaire_id": 2, "group_id": 99}]) is False
    # Unknown references are also rejected by the write path.
    with pytest.raises(ValidationError):
        validate_answer_rows(s, [historical])


def test_required_questionnaire_alone_is_not_overall_complete():
    from src.apps.questionnaire.completion import is_complete
    s = real_structure()
    assert is_complete(s, [_row(10, 100, [1000]), _row(11, 110, text="完成")]) is False


def test_no_required_questionnaires_cannot_unlock_voting():
    from src.apps.questionnaire.completion import is_complete
    s = real_structure()
    s["questionnaires"][0]["required"] = False
    assert is_complete(s, _answered_all(s)) is False


# ── content-required branch (structure with real questions) ───────────────

def real_structure(*, hidden_group=False, trigger=None) -> dict:
    """Required questionnaire 1 with a choice group (10) and a text group (11).

    ``hidden_group`` adds a hiddenByDefault group 12; ``trigger`` lists the
    relatedQuestionIds of option 1000 so the hidden group becomes visible.
    """
    groups = [
        {"id": 10, "order": 1, "hiddenByDefault": False, "questions": [
            {"id": 100, "type": "Single", "maxInputLen": 100, "options": [
                {"id": 1000, "relatedQuestionIds": list(trigger or [])},
            ]},
        ]},
        {"id": 11, "order": 2, "hiddenByDefault": False, "questions": [
            {"id": 110, "type": "Input", "maxInputLen": 100, "options": []},
        ]},
    ]
    if hidden_group:
        groups.append(
            {"id": 12, "order": 3, "hiddenByDefault": True, "questions": [
                {"id": 120, "type": "Single", "options": [
                    {"id": 1200, "relatedQuestionIds": []},
                ]},
            ]}
        )
    return {"questionnaires": [
        {"id": 1, "key": "a", "category": "main", "required": True, "order": 1,
         "questionGroups": groups},
        {"id": 2, "key": "b", "category": "extra", "required": False,
         "questionGroups": [{"id": 20, "order": 1, "questions": [
             {"id": 200, "type": "Input", "options": []},
         ]}]},
    ]}


def _row(gid, qid, opts=None, text=""):
    return {"questionnaire_id": 1, "group_id": gid, "active_question_id": qid,
            "selected_option_ids": opts or [], "input_text": text}


def _answered_all(s):
    """Rows a real user submits for every visible group of ``real_structure``."""
    rows = [_row(10, 100, [1000]), _row(11, 110, [], "我的回答"), _extra_answer()]
    return rows


def _extra_answer():
    return {"questionnaire_id": 2, "group_id": 20, "active_question_id": 200,
            "selected_option_ids": [], "input_text": "选填回答"}


def test_empty_rows_do_not_complete():
    """Rows with valid ids but no answer must not unlock voting (R-01)."""
    from src.apps.questionnaire.completion import is_complete
    s = real_structure()
    empty = [_row(10, 100, []), _row(11, 110, [], ""), _extra_answer()]
    assert is_complete(s, empty) is False


def test_partial_rows_do_not_complete():
    from src.apps.questionnaire.completion import is_complete
    s = real_structure()
    assert is_complete(s, [_row(10, 100, [1000]), _row(11, 110, [], ""),
                           _extra_answer()]) is False


def test_choice_and_text_answers_complete():
    from src.apps.questionnaire.completion import is_complete
    s = real_structure()
    assert is_complete(s, _answered_all(s)) is True


def test_choice_group_cannot_be_answered_by_text_only():
    from src.apps.questionnaire.completion import is_complete
    s = real_structure()
    rows = [_row(10, 100, [], "不是选项"), _row(11, 110, [], "我的回答"), _extra_answer()]
    assert is_complete(s, rows) is False


def test_text_group_cannot_be_answered_by_options_only():
    from src.apps.questionnaire.completion import is_complete
    s = real_structure()
    rows = [_row(10, 100, [1000]), _row(11, 110, [1000]), _extra_answer()]
    assert is_complete(s, rows) is False


def test_untouched_hidden_group_does_not_block():
    from src.apps.questionnaire.completion import is_complete
    s = real_structure(hidden_group=True)
    rows = _answered_all(s) + [_row(12, None, [], "")]
    assert is_complete(s, rows) is True


def test_triggered_hidden_group_requires_answer():
    from src.apps.questionnaire.completion import is_complete
    s = real_structure(hidden_group=True, trigger=[120])
    rows = _answered_all(s) + [_row(12, None, [], "")]
    assert is_complete(s, rows) is False
    rows_answered = _answered_all(s) + [_row(12, 120, [1200])]
    assert is_complete(s, rows_answered) is True


def test_option_not_belonging_to_question_does_not_count():
    from src.apps.questionnaire.completion import is_complete
    s = real_structure()
    rows = [_row(10, 100, [999]), _row(11, 110, [], "我的回答"), _extra_answer()]
    assert is_complete(s, rows) is False


def test_row_for_unknown_group_is_ignored():
    from src.apps.questionnaire.completion import is_complete
    s = real_structure()
    rows = _answered_all(s) + [_row(999, None, [], "")]
    assert is_complete(s, rows) is True


def test_illegal_questionnaire_does_not_hide_other_valid_completions():
    from src.apps.questionnaire.completion import completed_questionnaire_ids
    from src.apps.questionnaire.structure_index import StructureIndex

    s = real_structure()
    s["questionnaires"][0]["questionGroups"][0]["questions"][0]["options"].append(
        {"id": 1001, "relatedQuestionIds": []}
    )
    rows = [_row(10, 100, [1000, 1001]), _row(11, 110, text="文本"),
            {"questionnaire_id": 2, "group_id": 20, "active_question_id": 200,
             "selected_option_ids": [], "input_text": "另一份合法回答"}]
    assert completed_questionnaire_ids(StructureIndex(s), rows) == {2}


def test_completion_rejects_untriggered_variant_and_mutex_conflict():
    from src.apps.questionnaire.completion import is_complete

    s = real_structure()
    target = s["questionnaires"][0]["questionGroups"][1]
    target["questions"].append({"id": 111, "type": "Input", "options": []})
    assert is_complete(s, [_row(10, 100, [1000]), _row(11, 111, text="错误分支"),
                           _extra_answer()]) is False
    target["questions"] = [{"id": 110, "type": "Single", "options": [{"id": 1100}]}]
    source = s["questionnaires"][0]["questionGroups"][0]["questions"][0]["options"][0]
    source["mutexOptionIds"] = [1100]
    assert is_complete(s, [_row(10, 100, [1000]), _row(11, 110, [1100]),
                           _extra_answer()]) is False


def test_overall_policy_requires_a_and_any_of_bcd():
    from src.apps.questionnaire.completion import meets_completion_policy

    definitions = [
        {"id": 1, "required": True, "category": "main"},
        *[{"id": i, "required": False, "category": "extra"} for i in (2, 3, 4)],
    ]
    assert not meets_completion_policy(definitions, set())
    assert not meets_completion_policy(definitions, {1})
    assert not meets_completion_policy(definitions, {2, 3, 4})
    for selected in (2, 3, 4):
        assert meets_completion_policy(definitions, {1, selected})
    assert meets_completion_policy(definitions, {1, 2, 3, 4})
    assert not meets_completion_policy(definitions[:1], {1})
    assert not meets_completion_policy(definitions[1:], {2, 3, 4})
