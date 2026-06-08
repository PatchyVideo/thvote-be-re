"""Tests for the questionnaire structure assembler (DB rows → questionnaireV2)."""


def _q(id, slot, category, name="n", introduction="i", order=0):
    return {
        "id": id, "slot": slot, "category": category,
        "name": name, "introduction": introduction, "order": order,
    }


def _g(id, questionnaire_id, order=0, initial_question_id=0):
    return {
        "id": id, "questionnaire_id": questionnaire_id,
        "order": order, "initial_question_id": initial_question_id,
    }


def _qn(id, group_id, type="Single", content="c", introduction="i", order=0):
    return {
        "id": id, "group_id": group_id, "type": type,
        "content": content, "introduction": introduction, "order": order,
    }


def _o(id, question_id, content="o", related=None, mutex=None, group=0, order=0):
    return {
        "id": id, "question_id": question_id, "content": content,
        "related_question_ids": related or [], "mutex_option_ids": mutex or [],
        "option_group": group, "order": order,
    }


def test_assemble_basic_shape():
    from src.apps.questionnaire.assembler import assemble_structure

    questionnaires = [
        _q(11, "required", "main", name="必填"),
        _q(12, "optional1", "main"),
        _q(13, "optional2", "main"),
        _q(21, "ex1", "extra"),
        _q(22, "ex2", "extra"),
        _q(23, "ex3", "extra"),
        _q(24, "ex4", "extra"),
        _q(25, "ex5", "extra"),
    ]
    groups = [_g(1101, 11, order=1, initial_question_id=11011)]
    questions = [_qn(11011, 1101, type="Single", content="q1")]
    options = [
        _o(1101101, 11011, content="opt1", related=[11012], mutex=[1101102]),
    ]

    out = assemble_structure(questionnaires, groups, questions, options)

    assert set(out.keys()) == {"mainQuestionnaire", "extraQuestionnaire"}
    main = out["mainQuestionnaire"]
    assert set(main.keys()) == {
        "requiredQuestionnaire", "optionalQuestionnaire1", "optionalQuestionnaire2"
    }
    req = main["requiredQuestionnaire"]
    assert req["id"] == 11
    assert req["name"] == "必填"
    assert len(req["questionGroups"]) == 1
    grp = req["questionGroups"][0]
    assert grp["id"] == 1101
    assert grp["questionnaireId"] == 11
    assert grp["initialQuestionId"] == 11011
    q = grp["questions"][0]
    assert q["id"] == 11011
    assert q["type"] == "Single"
    opt = q["options"][0]
    assert opt["id"] == 1101101
    assert opt["relatedQuestionIds"] == [11012]
    assert opt["mutexOptionIds"] == [1101102]
    assert opt["optionGroup"] == 0

    extra = out["extraQuestionnaire"]
    assert set(extra.keys()) == {
        "exQuestionnaire1", "exQuestionnaire2", "exQuestionnaire3",
        "exQuestionnaire4", "exQuestionnaire5",
    }
    assert extra["exQuestionnaire1"]["id"] == 21


def test_assemble_orders_groups_and_questions():
    from src.apps.questionnaire.assembler import assemble_structure

    questionnaires = [
        _q(11, "required", "main"), _q(12, "optional1", "main"),
        _q(13, "optional2", "main"), _q(21, "ex1", "extra"),
        _q(22, "ex2", "extra"), _q(23, "ex3", "extra"),
        _q(24, "ex4", "extra"), _q(25, "ex5", "extra"),
    ]
    groups = [_g(1102, 11, order=2), _g(1101, 11, order=1)]
    questions = [_qn(2, 1101, order=2), _qn(1, 1101, order=1)]
    options = []

    out = assemble_structure(questionnaires, groups, questions, options)
    grps = out["mainQuestionnaire"]["requiredQuestionnaire"]["questionGroups"]
    assert [g["id"] for g in grps] == [1101, 1102]
    qs = grps[0]["questions"]
    assert [q["id"] for q in qs] == [1, 2]
