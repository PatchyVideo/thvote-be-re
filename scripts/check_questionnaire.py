"""Read-only questionnaire definition check: python -m scripts.check_questionnaire.

Exit 0: no errors (warnings allowed); 1: invalid definitions; 2: check failed.
Uses the application's database configuration. Never initializes or edits data.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import logging
import sys
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.apps.questionnaire.code_validation import InvalidCodeError, normalize_code
from src.db_model.questionnaire_def import (
    OptionDef, QuestionDef, QuestionGroupDef, QuestionnaireDef,
)


@dataclass(frozen=True)
class Issue:
    severity: Literal["error", "warning"]
    code: str
    kind: str
    node_id: int | None
    message: str


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _error(code: str, kind: str, row: dict, message: str) -> Issue:
    return Issue("error", code, kind, row.get("id"), message)


def _index(rows: list[dict], kind: str, issues: list[Issue]) -> dict[int, dict]:
    indexed: dict[int, dict] = {}
    for row in rows:
        node_id = row.get("id")
        if not _is_int(node_id):
            issues.append(_error("INVALID_ID", kind, {}, "ID 必须是整数"))
        elif node_id in indexed:
            issues.append(_error("DUPLICATE_ID", kind, row, "ID 重复"))
        else:
            indexed[node_id] = row
    return indexed


def _check_codes(rows: list[dict], kind: str, digits: int) -> list[Issue]:
    issues: list[Issue] = []
    seen: set[str] = set()
    for row in rows:
        try:
            code = normalize_code(row.get("code"), digits)
        except InvalidCodeError as exc:
            issues.append(_error("INVALID_CODE", kind, row, str(exc)))
            continue
        if code is None:
            issues.append(Issue("warning", "MISSING_CODE", kind, row.get("id"),
                                "缺少语义 code，相关结果查询可能不可用"))
        elif code in seen:
            issues.append(_error("DUPLICATE_CODE", kind, row, "语义 code 重复"))
        else:
            seen.add(code)
    return issues


def _check_references(
    options: dict[int, dict], questions: dict[int, dict], groups: dict[int, dict],
) -> list[Issue]:
    issues: list[Issue] = []
    for option in options.values():
        source_question = questions.get(option.get("question_id"), {})
        source_group = groups.get(source_question.get("group_id"), {})
        for field, targets, related in (
            ("related_question_ids", questions, True),
            ("mutex_option_ids", options, False),
        ):
            refs = option.get(field, [])
            if not isinstance(refs, list) or any(not _is_int(v) for v in refs):
                issues.append(_error("INVALID_REFERENCE_LIST", "option", option,
                                     f"{field} 必须是整数 ID 列表"))
                continue
            label = "RELATED" if related else "MUTEX"
            for target_id in refs:
                target = targets.get(target_id)
                if target is None:
                    issues.append(_error(f"MISSING_{label}", "option", option,
                                         f"{field} 目标 ID={target_id} 不存在"))
                    continue
                target_question = target if related else questions.get(
                    target.get("question_id"), {},
                )
                target_group = groups.get(target_question.get("group_id"), {})
                if not source_group or not target_group:
                    continue  # Parent errors are reported separately.
                if source_group["questionnaire_id"] != target_group["questionnaire_id"]:
                    issues.append(_error(f"CROSS_QUESTIONNAIRE_{label}",
                                         "option", option,
                                         f"{field} 目标 ID={target_id} 属于其他问卷"))
                elif related:
                    before, after = source_group.get("order"), target_group.get("order")
                    if _is_int(before) and _is_int(after) and after <= before:
                        issues.append(_error("RELATED_NOT_FORWARD", "option", option,
                                             f"related 目标 ID={target_id} 不在后续题组"))
                elif target_id == option["id"]:
                    issues.append(_error("SELF_MUTEX", "option", option,
                                         "mutex 不能指向自身"))
    return issues


def check_definitions(
    questionnaires: list[dict], groups: list[dict],
    questions: list[dict], options: list[dict],
) -> list[Issue]:
    """Inspect raw definition rows, retaining orphan nodes; do not mutate input."""
    issues: list[Issue] = []
    qns = _index(questionnaires, "questionnaire", issues)
    gs = _index(groups, "group", issues)
    qs = _index(questions, "question", issues)
    opts = _index(options, "option", issues)
    groups_by_qn: dict[int, list[dict]] = {}
    questions_by_group: dict[int, list[dict]] = {}
    options_by_question: dict[int, list[dict]] = {}
    for children, parents, parent_key, kind, bucket in (
        (gs, qns, "questionnaire_id", "group", groups_by_qn),
        (qs, gs, "group_id", "question", questions_by_group),
        (opts, qs, "question_id", "option", options_by_question),
    ):
        for row in children.values():
            parent_id = row.get(parent_key)
            if parent_id not in parents:
                issues.append(_error(f"ORPHAN_{kind.upper()}", kind, row,
                                     f"父节点 {parent_key}={parent_id} 不存在"))
            bucket.setdefault(parent_id, []).append(row)

    keys: set[str] = set()
    for qn in qns.values():
        key = qn.get("key")
        if not isinstance(key, str) or not key.strip():
            issues.append(_error("INVALID_KEY", "questionnaire", qn,
                                 "问卷 key 不能为空"))
        elif key in keys:
            issues.append(_error("DUPLICATE_KEY", "questionnaire", qn,
                                 "问卷 key 重复"))
        else:
            keys.add(key)
        if qn.get("category") not in ("main", "extra"):
            issues.append(_error("INVALID_CATEGORY", "questionnaire", qn,
                                 "category 必须是 main 或 extra"))
        qn_groups = groups_by_qn.get(qn["id"], [])
        if not qn_groups:
            issues.append(_error("EMPTY_QUESTIONNAIRE", "questionnaire", qn,
                                 "问卷没有题组"))
        seen_orders: set[int] = set()
        for group in qn_groups:
            order = group.get("order")
            if not _is_int(order) or order < 1:
                issues.append(_error("INVALID_GROUP_ORDER", "group", group,
                                     "题组 order 必须是正整数"))
            elif order in seen_orders:
                issues.append(_error("DUPLICATE_GROUP_ORDER", "group", group,
                                     "同一问卷内题组 order 重复"))
            else:
                seen_orders.add(order)
        first = [g for g in qn_groups if g.get("order") == 1]
        if len(first) != 1:
            issues.append(_error("INVALID_FIRST_GROUP", "questionnaire", qn,
                                 "问卷必须有唯一的 order=1 首组"))
        elif (first[0].get("hidden_by_default", False)
              or len(questions_by_group.get(first[0]["id"], [])) != 1):
            issues.append(_error("INVALID_FIRST_GROUP", "group", first[0],
                                 "首组必须默认可见且仅有一道题"))

    if not any(q.get("required") for q in qns.values()):
        issues.append(_error("MISSING_REQUIRED", "questionnaires", {},
                             "整体完成条件缺少必填问卷"))
    if not any(q.get("category") == "extra" and not q.get("required")
               for q in qns.values()):
        issues.append(_error("MISSING_EXTRA", "questionnaires", {},
                             "整体完成条件缺少 extra 非必填问卷"))
    for group in gs.values():
        if not questions_by_group.get(group["id"]):
            issues.append(_error("EMPTY_GROUP", "group", group, "题组没有题目"))
    for question in qs.values():
        kind = question.get("type")
        choices = options_by_question.get(question["id"], [])
        if kind not in ("Single", "Multiple", "Input"):
            issues.append(_error("INVALID_QUESTION_TYPE", "question", question,
                                 "题型必须是 Single、Multiple 或 Input"))
        elif kind == "Input":
            if choices:
                issues.append(_error("INPUT_HAS_OPTIONS", "question", question,
                                     "Input 题不应配置选项"))
            limit = question.get("max_input_len", 1000)
            if not _is_int(limit) or limit < 1:
                issues.append(_error("INVALID_INPUT_LENGTH", "question", question,
                                     "Input 最大长度必须是正整数"))
        elif not choices:
            issues.append(_error("EMPTY_OPTIONS", "question", question,
                                 "选择题必须有选项"))
    for option in opts.values():
        content = option.get("content")
        if not isinstance(content, str) or not content.strip():
            issues.append(_error("EMPTY_OPTION_CONTENT", "option", option,
                                 "选项内容不能为空"))
        group = option.get("option_group")
        if not _is_int(group) or group < 0:
            issues.append(_error("INVALID_OPTION_GROUP", "option", option,
                                 "option_group 必须是非负整数"))
    issues.extend(_check_codes(questions, "question", 5))
    issues.extend(_check_codes(options, "option", 7))
    issues.extend(_check_references(opts, qs, gs))
    return issues


async def load_definitions(
    session: AsyncSession,
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """Read every row, including nodes the normal structure loader filters out."""
    tables = (QuestionnaireDef, QuestionGroupDef, QuestionDef, OptionDef)
    rows = []
    for model in tables:
        result = await session.execute(select(model.__table__).order_by(model.id))
        rows.append([dict(row) for row in result.mappings()])
    return rows[0], rows[1], rows[2], rows[3]


async def _run(database_url: str) -> list[Issue]:
    engine = create_async_engine(database_url, echo=False)
    try:
        async with AsyncSession(engine) as session:
            return check_definitions(*await load_definitions(session))
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="只读检查问卷定义，供手动或发布前调用")
    parser.parse_args(argv)
    try:
        from src.common.config import get_settings
        from src.common.database import normalize_async_database_url

        # Config/Nacos loaders may log raw exceptions before our error handler.
        # Keep CLI output sanitized without changing application loader behavior.
        previous_level = logging.root.manager.disable
        try:
            logging.disable(logging.CRITICAL)
            url = normalize_async_database_url(get_settings().database.build_url())
        finally:
            logging.disable(previous_level)
        issues = asyncio.run(_run(url))
    except Exception as exc:
        # DB exceptions can contain credentials/SQL; never print their text.
        print(f"检查未能执行（{type(exc).__name__}），请检查数据库配置、连接和表结构。",
              file=sys.stderr)
        return 2
    for issue in issues:
        location = issue.kind
        if issue.node_id is not None:
            location += f"={issue.node_id}"
        print(f"[{issue.severity.upper()}] {issue.code} {location}: {issue.message}")
    errors = sum(i.severity == "error" for i in issues)
    warnings = len(issues) - errors
    print(f"检查完成：{errors} 个错误，{warnings} 个警告。")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
