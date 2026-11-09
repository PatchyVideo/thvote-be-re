"""Rule behavior on a small real definition, IDs independent of ordering."""
from copy import deepcopy

import pytest

from src.apps.questionnaire.validation import validate_answer_rows
from src.common.exceptions import ValidationError


def option(oid, *, related=(), mutex=()):
    return {"id": oid, "relatedQuestionIds": list(related),
            "mutexOptionIds": list(mutex), "optionGroup": 0}


def definition():
    return {"questionnaires": [{"id": 1, "required": True, "questionGroups": [
        {"id": 30, "order": 1, "questions": [
            {"id": 300, "type": "Single", "options": [
                option(3000, related=[101]), option(3001),
            ]},
        ]},
        {"id": 10, "order": 2, "hiddenByDefault": True, "questions": [
            {"id": 100, "type": "Single", "options": [option(1000)]},
            {"id": 101, "type": "Single", "options": [
                option(1010, related=[200]), option(1011),
            ]},
        ]},
        {"id": 20, "order": 3, "hiddenByDefault": True, "questions": [
            {"id": 200, "type": "Input", "options": []},
        ]},
    ]}]}


def answer(gid, qid, options=(), text=""):
    return {"questionnaire_id": 1, "group_id": gid, "active_question_id": qid,
            "selected_option_ids": list(options), "input_text": text}


def test_chain_and_partial_visible_answers_are_legal_without_mutation():
    rows = [answer(30, 300, [3000]), answer(10, 101, [1010]),
            answer(20, 200, text="回答")]
    before = deepcopy(rows)
    validate_answer_rows(definition(), rows)
    assert rows == before
    validate_answer_rows(definition(), [answer(30, 300, [3000]), answer(10, None)])


def test_untriggered_branch_and_hidden_self_trigger_rejected():
    s = definition()
    with pytest.raises(ValidationError):
        validate_answer_rows(s, [answer(30, 300, [3000]), answer(10, 100, [1000])])
    # Without the root choice, a hidden answer cannot reveal itself or its child.
    s["questionnaires"][0]["questionGroups"][1]["questions"][1]["options"][0][
        "relatedQuestionIds"] = [101, 200]
    with pytest.raises(ValidationError):
        validate_answer_rows(s, [answer(30, 300, [3001]), answer(10, 101, [1010]),
                                 answer(20, 200, text="伪造")])


def test_multiple_visible_triggers_allow_either_target():
    s = definition()
    s["questionnaires"][0]["questionGroups"][0]["questions"][0]["options"][0][
        "relatedQuestionIds"] = [100, 101]
    validate_answer_rows(s, [answer(30, 300, [3000]), answer(10, 100, [1000])])
    validate_answer_rows(s, [answer(30, 300, [3000]), answer(10, 101, [1011])])


def test_directed_mutex_rejects_conflict_but_not_target_alone():
    s = definition()
    source = s["questionnaires"][0]["questionGroups"][0]["questions"][0]["options"][0]
    source["mutexOptionIds"] = [1011]
    with pytest.raises(ValidationError):
        validate_answer_rows(s, [answer(30, 300, [3000]), answer(10, 101, [1011])])
    source["mutexOptionIds"] = []
    validate_answer_rows(s, [answer(30, 300, [3000]), answer(10, 101, [1011])])


def test_unreachable_hidden_cycle_does_not_validate_itself():
    s = definition()
    group = s["questionnaires"][0]["questionGroups"][2]
    group["questions"][0] = {"id": 200, "type": "Single",
                              "options": [option(2000, related=[101])]}
    with pytest.raises(ValidationError):
        validate_answer_rows(s, [answer(10, 101, [1010]), answer(20, 200, [2000])])


def test_nonconvergent_branches_report_configuration_error():
    s = definition()
    groups = s["questionnaires"][0]["questionGroups"]
    groups[1]["hiddenByDefault"] = False
    groups[1]["questions"][0]["options"] = [option(1000, related=[201])]
    groups[2]["hiddenByDefault"] = False
    groups[2]["questions"] = [
        {"id": 200, "type": "Single", "options": [option(2000, related=[101])]},
        {"id": 201, "type": "Input", "options": []},
    ]
    with pytest.raises(ValidationError) as error:
        validate_answer_rows(s, [answer(10, 100, [1000]), answer(20, 200, [2000])])
    assert error.value.message == "QUESTIONNAIRE_CONFIGURATION_ERROR"
