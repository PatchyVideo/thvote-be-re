"""Tests: completion based on required questionnaires in the array.

Since R-01/D-08 completion also requires *substantive* answers for the groups
the frontend actually renders — a stored but empty row no longer unlocks voting.
"""


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


def test_complete_when_required_groups_answered():
    from src.apps.questionnaire.completion import is_complete
    s = _structure([10, 11])
    answers = [{"questionnaire_id": 1, "group_id": 10},
               {"questionnaire_id": 1, "group_id": 11}]
    assert is_complete(s, answers) is True


def test_incomplete_when_required_group_missing():
    from src.apps.questionnaire.completion import is_complete
    s = _structure([10, 11])
    assert is_complete(s, [{"questionnaire_id": 1, "group_id": 10}]) is False


def test_non_required_questionnaire_ignored():
    from src.apps.questionnaire.completion import is_complete
    s = _structure([10])
    # answering required q1.g10 suffices; q2 (not required) ignored
    assert is_complete(s, [{"questionnaire_id": 1, "group_id": 10}]) is True


def test_no_required_questionnaires_complete():
    from src.apps.questionnaire.completion import is_complete
    s = _structure([10], required=False)
    assert is_complete(s, []) is True


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
    ]}


def _row(gid, qid, opts=None, text=""):
    return {"questionnaire_id": 1, "group_id": gid, "active_question_id": qid,
            "selected_option_ids": opts or [], "input_text": text}


def _answered_all(s):
    """Rows a real user submits for every visible group of ``real_structure``."""
    rows = [_row(10, 100, [1000]), _row(11, 110, [], "我的回答")]
    return rows


def test_empty_rows_do_not_complete():
    """Rows with valid ids but no answer must not unlock voting (R-01)."""
    from src.apps.questionnaire.completion import is_complete
    s = real_structure()
    empty = [_row(10, 100, []), _row(11, 110, [], "")]
    assert is_complete(s, empty) is False


def test_partial_rows_do_not_complete():
    from src.apps.questionnaire.completion import is_complete
    s = real_structure()
    assert is_complete(s, [_row(10, 100, [1000]), _row(11, 110, [], "")]) is False


def test_choice_and_text_answers_complete():
    from src.apps.questionnaire.completion import is_complete
    s = real_structure()
    assert is_complete(s, _answered_all(s)) is True


def test_choice_group_cannot_be_answered_by_text_only():
    from src.apps.questionnaire.completion import is_complete
    s = real_structure()
    rows = [_row(10, 100, [], "不是选项"), _row(11, 110, [], "我的回答")]
    assert is_complete(s, rows) is False


def test_text_group_cannot_be_answered_by_options_only():
    from src.apps.questionnaire.completion import is_complete
    s = real_structure()
    rows = [_row(10, 100, [1000]), _row(11, 110, [1000])]
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
    rows = [_row(10, 100, [999]), _row(11, 110, [], "我的回答")]
    assert is_complete(s, rows) is False


def test_row_for_unknown_group_is_ignored():
    from src.apps.questionnaire.completion import is_complete
    s = real_structure()
    rows = _answered_all(s) + [_row(999, None, [], "")]
    assert is_complete(s, rows) is True
