"""Tests: completion based on required questionnaires in the array."""


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
