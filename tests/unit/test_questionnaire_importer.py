"""Tests: parse {"questionnaires":[...]} tree -> DB row dicts."""


def _tree():
    return {"questionnaires": [
        {"id": 1, "key": "a", "title": "必填", "introduction": "ai",
         "category": "main", "required": True, "order": 1, "questionGroups": [
            {"id": 10, "order": 1, "hiddenByDefault": False, "questions": [
                {"id": 100, "type": "Single", "content": "q1", "introduction": "",
                 "maxInputLen": 1000, "options": [
                    {"id": 1000, "content": "o1", "relatedQuestionIds": [101],
                     "mutexOptionIds": [1001], "optionGroup": 0}]}]}]},
        {"id": 2, "key": "b", "title": "额外", "category": "extra", "required": False,
         "order": 2, "questionGroups": []},
    ]}


def test_parse_array():
    from src.apps.questionnaire.importer import parse_structure_tree
    qns, groups, questions, options = parse_structure_tree(_tree())
    by_id = {q["id"]: q for q in qns}
    assert by_id[1]["key"] == "a"
    assert by_id[1]["required"] is True
    assert by_id[1]["category"] == "main"
    assert by_id[1]["title"] == "必填"
    assert by_id[2]["category"] == "extra"
    assert groups[0]["questionnaire_id"] == 1
    assert groups[0]["hidden_by_default"] is False
    assert questions[0]["group_id"] == 10
    assert questions[0]["max_input_len"] == 1000
    assert options[0]["question_id"] == 100
    assert options[0]["related_question_ids"] == [101]
    assert options[0]["mutex_option_ids"] == [1001]
    assert options[0]["option_group"] == 0


def test_roundtrip_through_assembler():
    from src.apps.questionnaire.assembler import assemble_structure
    from src.apps.questionnaire.importer import parse_structure_tree
    rows = parse_structure_tree(_tree())
    out = assemble_structure(*rows)
    qs = out["questionnaires"]
    assert qs[0]["key"] == "a"
    assert qs[0]["questionGroups"][0]["questions"][0]["id"] == 100
    assert qs[0]["questionGroups"][0]["questions"][0]["options"][0]["id"] == 1000
