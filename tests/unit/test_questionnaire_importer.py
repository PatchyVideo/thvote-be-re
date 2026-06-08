"""Tests for the questionnaire tree importer (questionnaireV2 JSON → rows)."""


def _tree():
    return {
        "mainQuestionnaire": {
            "requiredQuestionnaire": {
                "id": 11, "name": "必填", "introduction": "intro",
                "questionGroups": [
                    {
                        "id": 1101, "questionnaireId": 11, "order": 1,
                        "initialQuestionId": 11011,
                        "questions": [
                            {
                                "id": 11011, "type": "Single",
                                "content": "q1", "introduction": "qi",
                                "options": [
                                    {
                                        "id": 1101101, "content": "o1",
                                        "relatedQuestionIds": [11012],
                                        "mutexOptionIds": [1101102],
                                        "optionGroup": 0,
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            "optionalQuestionnaire1": {"id": 12, "questionGroups": []},
            "optionalQuestionnaire2": {"id": 13, "questionGroups": []},
        },
        "extraQuestionnaire": {
            "exQuestionnaire1": {"id": 21, "questionGroups": []},
        },
    }


def test_parse_tree_counts_and_slots():
    from src.apps.questionnaire.importer import parse_structure_tree

    qns, groups, questions, options = parse_structure_tree(_tree())

    by_id = {q["id"]: q for q in qns}
    assert by_id[11]["slot"] == "required"
    assert by_id[11]["category"] == "main"
    assert by_id[12]["slot"] == "optional1"
    assert by_id[13]["slot"] == "optional2"
    assert by_id[21]["slot"] == "ex1"
    assert by_id[21]["category"] == "extra"
    assert by_id[11]["name"] == "必填"

    assert groups[0]["id"] == 1101
    assert groups[0]["questionnaire_id"] == 11
    assert groups[0]["initial_question_id"] == 11011

    assert questions[0]["id"] == 11011
    assert questions[0]["group_id"] == 1101
    assert questions[0]["type"] == "Single"

    assert options[0]["id"] == 1101101
    assert options[0]["question_id"] == 11011
    assert options[0]["related_question_ids"] == [11012]
    assert options[0]["mutex_option_ids"] == [1101102]


def test_parse_tree_roundtrips_through_assembler():
    from src.apps.questionnaire.assembler import assemble_structure
    from src.apps.questionnaire.importer import parse_structure_tree

    qns, groups, questions, options = parse_structure_tree(_tree())
    out = assemble_structure(qns, groups, questions, options)
    req = out["mainQuestionnaire"]["requiredQuestionnaire"]
    assert req["id"] == 11
    assert req["questionGroups"][0]["questions"][0]["options"][0]["id"] == 1101101
