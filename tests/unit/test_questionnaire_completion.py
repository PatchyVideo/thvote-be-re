"""Tests for questionnaire completion pure logic."""


def _structure_with_required_groups(group_ids):
    """A minimal assembled structure: requiredQuestionnaire with given groups."""
    return {
        "mainQuestionnaire": {
            "requiredQuestionnaire": {
                "id": 11,
                "name": "required",
                "introduction": "",
                "questionGroups": [
                    {
                        "id": gid, "questionnaireId": 11, "order": i,
                        "initialQuestionId": gid * 10 + 1, "questions": [],
                    }
                    for i, gid in enumerate(group_ids)
                ],
            },
            "optionalQuestionnaire1": {"id": 12, "questionGroups": []},
            "optionalQuestionnaire2": {"id": 13, "questionGroups": []},
        },
        "extraQuestionnaire": {},
    }


def test_complete_when_all_required_groups_answered():
    from src.apps.questionnaire.completion import is_complete

    structure = _structure_with_required_groups([1101, 1102])
    answers = [
        {"questionnaire_id": 11, "group_id": 1101},
        {"questionnaire_id": 11, "group_id": 1102},
    ]
    assert is_complete(structure, answers) is True


def test_incomplete_when_a_required_group_missing():
    from src.apps.questionnaire.completion import is_complete

    structure = _structure_with_required_groups([1101, 1102])
    answers = [{"questionnaire_id": 11, "group_id": 1101}]
    assert is_complete(structure, answers) is False


def test_optional_groups_do_not_block():
    from src.apps.questionnaire.completion import is_complete

    structure = _structure_with_required_groups([1101])
    # required group answered; optionals ignored
    answers = [{"questionnaire_id": 11, "group_id": 1101}]
    assert is_complete(structure, answers) is True


def test_no_required_groups_is_complete():
    from src.apps.questionnaire.completion import is_complete

    structure = _structure_with_required_groups([])
    assert is_complete(structure, []) is True
