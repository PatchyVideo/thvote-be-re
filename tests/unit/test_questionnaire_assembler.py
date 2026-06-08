"""Tests: assemble DB rows -> {"questionnaires":[...]} array."""


def _q(id, key, category="main", required=False, title="t", introduction="i", order=0):
    return {"id": id, "key": key, "category": category, "required": required,
            "title": title, "introduction": introduction, "order": order}


def _g(id, questionnaire_id, order=0, hidden_by_default=False):
    return {"id": id, "questionnaire_id": questionnaire_id, "order": order,
            "hidden_by_default": hidden_by_default}


def _qn(id, group_id, type="Single", content="c", introduction="i", order=0,
        max_input_len=1000):
    return {"id": id, "group_id": group_id, "type": type, "content": content,
            "introduction": introduction, "order": order,
            "max_input_len": max_input_len}


def _o(id, question_id, content="o", related=None, mutex=None, group=0, order=0):
    return {"id": id, "question_id": question_id, "content": content,
            "related_question_ids": related or [], "mutex_option_ids": mutex or [],
            "option_group": group, "order": order}


def test_assemble_array_shape_and_order():
    from src.apps.questionnaire.assembler import assemble_structure

    questionnaires = [_q(2, "b", order=2, required=False),
                      _q(1, "a", order=1, required=True, title="必填")]
    groups = [_g(10, 1, order=1, hidden_by_default=True)]
    questions = [_qn(100, 10, type="Single")]
    options = [_o(1000, 100, related=[101], mutex=[1001])]

    out = assemble_structure(questionnaires, groups, questions, options)
    qs = out["questionnaires"]
    assert [q["id"] for q in qs] == [1, 2]  # sorted by order
    q1 = qs[0]
    assert q1["key"] == "a" and q1["required"] is True and q1["category"] == "main"
    assert q1["title"] == "必填"
    g = q1["questionGroups"][0]
    assert g["hiddenByDefault"] is True
    qout = g["questions"][0]
    assert qout["maxInputLen"] == 1000
    opt = qout["options"][0]
    assert opt["relatedQuestionIds"] == [101]
    assert opt["mutexOptionIds"] == [1001]
    assert opt["optionGroup"] == 0
    assert qs[1]["questionGroups"] == []  # questionnaire with no groups still appears


def test_assemble_orders_groups_and_questions():
    from src.apps.questionnaire.assembler import assemble_structure

    questionnaires = [_q(1, "a", order=1)]
    groups = [_g(12, 1, order=2), _g(11, 1, order=1)]
    questions = [_qn(2, 11, order=2), _qn(1, 11, order=1)]
    options = []
    out = assemble_structure(questionnaires, groups, questions, options)
    grps = out["questionnaires"][0]["questionGroups"]
    assert [g["id"] for g in grps] == [11, 12]
    assert [q["id"] for q in grps[0]["questions"]] == [1, 2]
