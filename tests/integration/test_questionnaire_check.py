"""Definition inspection and real CLI behavior against a temporary SQLite DB."""
from __future__ import annotations

import copy
import logging
import os
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import create_engine

from scripts.check_questionnaire import check_definitions, main
from src.db_model.questionnaire_def import (
    OptionDef, QuestionDef, QuestionGroupDef, QuestionnaireDef,
)


def valid_rows():
    return (
        [{"id": 1, "key": "a", "category": "main", "required": True},
         {"id": 2, "key": "b", "category": "extra", "required": False}],
        [{"id": 10, "questionnaire_id": 1, "order": 1},
         {"id": 20, "questionnaire_id": 2, "order": 1}],
        [{"id": 100, "group_id": 10, "type": "Single", "code": "11011"},
         {"id": 200, "group_id": 20, "type": "Input", "code": "21011",
          "max_input_len": 1000}],
        [{"id": 1000, "question_id": 100, "content": "选项一",
          "code": "1101101", "option_group": 0,
          "related_question_ids": [], "mutex_option_ids": [1001]},
         {"id": 1001, "question_id": 100, "content": "选项二",
          "code": "1101102", "option_group": 1,
          "related_question_ids": [], "mutex_option_ids": []}],
    )


def test_valid_definitions_are_not_modified():
    rows = valid_rows()
    before = copy.deepcopy(rows)
    assert check_definitions(*rows) == []
    assert rows == before


@pytest.mark.parametrize("table,index,patch,code", [
    (0, 0, {"key": ""}, "INVALID_KEY"),
    (0, 1, {"key": "a"}, "DUPLICATE_KEY"),
    (0, 0, {"required": False}, "MISSING_REQUIRED"),
    (0, 1, {"category": "main"}, "MISSING_EXTRA"),
    (0, 1, {"category": "sub"}, "INVALID_CATEGORY"),
    (1, 0, {"questionnaire_id": 999}, "ORPHAN_GROUP"),
    (1, 0, {"order": 0}, "INVALID_GROUP_ORDER"),
    (1, 0, {"hidden_by_default": True}, "INVALID_FIRST_GROUP"),
    (2, 0, {"group_id": 999}, "ORPHAN_QUESTION"),
    (2, 0, {"type": "Other"}, "INVALID_QUESTION_TYPE"),
    (2, 0, {"type": "Input"}, "INPUT_HAS_OPTIONS"),
    (2, 1, {"max_input_len": 0}, "INVALID_INPUT_LENGTH"),
    (2, 0, {"code": "bad"}, "INVALID_CODE"),
    (3, 0, {"question_id": 999}, "ORPHAN_OPTION"),
    (3, 0, {"content": "  "}, "EMPTY_OPTION_CONTENT"),
    (3, 0, {"option_group": True}, "INVALID_OPTION_GROUP"),
    (3, 1, {"code": "1101101"}, "DUPLICATE_CODE"),
    (3, 0, {"related_question_ids": False}, "INVALID_REFERENCE_LIST"),
    (3, 0, {"related_question_ids": [True]}, "INVALID_REFERENCE_LIST"),
    (3, 0, {"mutex_option_ids": [1000]}, "SELF_MUTEX"),
])
def test_definition_errors_are_located(table, index, patch, code):
    rows = valid_rows()
    node_id = rows[table][index]["id"]
    rows[table][index].update(patch)
    issues = check_definitions(*rows)
    assert any(i.code == code and i.severity == "error" for i in issues)
    # Local errors identify the actual row, not its semantic code.
    if not code.startswith("MISSING_"):
        assert any(i.code == code and i.node_id == node_id for i in issues)


def test_structural_errors_are_reported_together():
    questionnaires, groups, questions, options = valid_rows()
    groups.append({"id": 11, "questionnaire_id": 1, "order": 1})
    questionnaires.append({"id": 3, "key": "c", "category": "extra"})
    questions.append({"id": 101, "group_id": 10, "type": "Single"})
    options.append(dict(options[0]))
    codes = {i.code for i in check_definitions(
        questionnaires, groups, questions, options,
    )}
    assert {"DUPLICATE_ID", "DUPLICATE_GROUP_ORDER", "EMPTY_QUESTIONNAIRE",
            "EMPTY_GROUP", "INVALID_FIRST_GROUP", "EMPTY_OPTIONS"} <= codes


def test_related_uses_group_order_and_mutex_remains_directed():
    rows = valid_rows()
    rows[2][0]["type"] = "Multiple"
    rows[1].append({"id": 3, "questionnaire_id": 1, "order": 2})
    rows[2].append({"id": 5, "group_id": 3, "type": "Input",
                    "max_input_len": 100, "code": "11012"})
    rows[3][0]["related_question_ids"] = [5]  # Smaller ID, later group.
    assert check_definitions(*rows) == []
    rows[3][0]["related_question_ids"] = [999, 200, 100]
    rows[3][0]["mutex_option_ids"] = [999]
    codes = {i.code for i in check_definitions(*rows)}
    assert {"MISSING_RELATED", "CROSS_QUESTIONNAIRE_RELATED",
            "RELATED_NOT_FORWARD", "MISSING_MUTEX"} <= codes


def test_mutex_cannot_target_another_questionnaire():
    rows = valid_rows()
    rows[2][1]["type"] = "Single"
    rows[3].append({"id": 2000, "question_id": 200, "content": "其他问卷",
                    "option_group": 0, "code": "2101101"})
    rows[3][0]["mutex_option_ids"] = [2000]
    assert "CROSS_QUESTIONNAIRE_MUTEX" in {
        i.code for i in check_definitions(*rows)
    }


def test_missing_codes_are_warnings():
    rows = valid_rows()
    rows[2][0]["code"] = None
    rows[3][0]["code"] = ""
    issues = check_definitions(*rows)
    assert [(i.severity, i.code) for i in issues] == [
        ("warning", "MISSING_CODE"), ("warning", "MISSING_CODE"),
    ]


@pytest.mark.parametrize("case,exit_code", [
    ("valid", 0), ("warning", 0), ("orphan", 1), ("missing_tables", 2),
])
def test_cli_exit_status_and_read_only_database(tmp_path, case, exit_code):
    db_file = tmp_path / "questionnaire.sqlite"
    url = f"sqlite+aiosqlite:///{db_file}"
    engine = create_engine(f"sqlite:///{db_file}")
    rows = valid_rows()
    if case == "warning":
        rows[2][0]["code"] = None
    if case == "orphan":
        rows[1].append({"id": 999, "questionnaire_id": 999, "order": 1})
    with engine.begin() as conn:
        if case != "missing_tables":
            for model, table_rows in zip(
                (QuestionnaireDef, QuestionGroupDef, QuestionDef, OptionDef), rows,
            ):
                model.__table__.create(conn)
                conn.execute(model.__table__.insert(), table_rows)
    engine.dispose()
    before = db_file.read_bytes()
    result = subprocess.run(
        [sys.executable, "-m", "scripts.check_questionnaire"],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "DATABASE_URL": url, "NACOS_ENABLED": "false"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == exit_code, result.stdout + result.stderr
    assert db_file.read_bytes() == before
    if case == "orphan":
        assert "ORPHAN_GROUP" in result.stdout
        assert "999" in result.stdout
    elif case == "warning":
        assert "MISSING_CODE" in result.stdout
    elif case == "missing_tables":
        assert "检查未能执行" in result.stderr
        assert url not in result.stderr


def test_cli_failure_does_not_expose_connection_details():
    result = subprocess.run(
        [sys.executable, "-m", "scripts.check_questionnaire"],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "DATABASE_URL": "invalid://do-not-print-this",
             "NACOS_ENABLED": "false"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 2
    assert "do-not-print-this" not in result.stdout + result.stderr


def test_configuration_failure_logs_cannot_expose_details(monkeypatch, capsys, caplog):
    import src.common.config as config

    def failed_settings():
        logging.getLogger("src.common.config").warning("private-config-address")
        raise RuntimeError("private-config-address")

    monkeypatch.setattr(config, "get_settings", failed_settings)
    assert main([]) == 2
    output = capsys.readouterr()
    assert "RuntimeError" in output.err
    assert "private-config-address" not in output.out + output.err + caplog.text
