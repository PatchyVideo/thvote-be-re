"""Pure branch, visibility and exclusion rules for questionnaire answers."""
from __future__ import annotations

from dataclasses import dataclass, field

from src.apps.questionnaire.structure_index import StructureIndex


@dataclass(frozen=True)
class AnswerIssue:
    code: str
    questionnaire_id: int | None
    group_id: int | None
    question_id: int | None
    message: str


@dataclass
class RuleEvaluation:
    visible_group_ids: set[int] = field(default_factory=set)
    allowed_question_ids: dict[int, frozenset[int]] = field(default_factory=dict)
    answered_group_ids: set[int] = field(default_factory=set)
    supplied_groups: set[tuple[int, int]] = field(default_factory=set)
    invalid_questionnaire_ids: set[int] = field(default_factory=set)
    first_issue: AnswerIssue | None = None
    configuration_issue: AnswerIssue | None = None
    iterations: int = 0

    def reject(self, issue: AnswerIssue) -> None:
        if issue.questionnaire_id is not None:
            self.invalid_questionnaire_ids.add(issue.questionnaire_id)
        if self.first_issue is None:
            self.first_issue = issue
        if issue.code == "QUESTIONNAIRE_CONFIGURATION_ERROR":
            self.configuration_issue = issue


def _default_question(group: dict) -> int | None:
    questions = group.get("questions") or []
    if not questions or (group.get("order") != 1 and group.get("hiddenByDefault")):
        return None
    return questions[0]["id"]


def is_done_row(index: StructureIndex, row: dict) -> bool:
    """Content predicate; callers validate references and rule consistency first."""
    qid = row.get("active_question_id")
    if isinstance(qid, bool) or not isinstance(qid, int):
        return False
    question = index.questions.get(qid)
    if question is None or index.question_group[qid] != row.get("group_id"):
        return False
    if question.get("type") == "Input":
        text = row.get("input_text")
        return isinstance(text, str) and bool(text.strip())
    options = row.get("selected_option_ids")
    return isinstance(options, list) and any(
        isinstance(oid, int) and not isinstance(oid, bool)
        and oid in index.question_options[qid] for oid in options
    )


def _resolve_branches(
    index: StructureIndex, groups: list[dict], rows: dict[int, dict],
) -> tuple[dict[int, int | None], dict[int, frozenset[int]], int, bool]:
    """Start from defaults: hidden answers cannot supply their own reachability."""
    defaults = {g["id"]: _default_question(g) for g in groups}
    active = dict(defaults)
    group_ids = set(defaults)
    allowed: dict[int, frozenset[int]] = {}
    for iteration in range(max(1, len(groups) * 4)):
        triggered: dict[int, list[int]] = {}
        for group in groups:
            gid = group["id"]
            row = rows.get(gid)
            qid = active[gid]
            if qid is None or row is None or row["active_question_id"] != qid:
                continue
            for oid in row["selected_option_ids"]:
                option = index.question_options[qid][oid]
                for target in option.get("relatedQuestionIds") or []:
                    target_group = index.question_group.get(target)
                    if target_group in group_ids:
                        triggered.setdefault(target_group, []).append(target)
        next_active: dict[int, int | None] = {}
        for group in groups:
            gid = group["id"]
            targets = triggered.get(gid, [])
            if group.get("order") == 1 or not targets:
                qid = defaults[gid]
                allowed[gid] = frozenset(() if qid is None else (qid,))
            else:
                submitted = rows.get(gid, {}).get("active_question_id")
                qid = submitted if submitted in targets else targets[0]
                allowed[gid] = frozenset(targets)
            next_active[gid] = qid
        if next_active == active:
            return active, allowed, iteration + 1, True
        active = next_active
    return active, allowed, iteration + 1, False


def evaluate_rules(
    index: StructureIndex, rows_by_group: dict[tuple[int, int], dict],
) -> RuleEvaluation:
    """Evaluate structurally and locally validated rows without mutating them."""
    result = RuleEvaluation(supplied_groups=set(rows_by_group))
    for questionnaire in index.questionnaires:
        qn_id = questionnaire["id"]
        groups = index.questionnaire_groups[qn_id]
        rows = {g["id"]: rows_by_group[(qn_id, g["id"])] for g in groups
                if (qn_id, g["id"]) in rows_by_group}
        active, allowed, iterations, stable = _resolve_branches(index, groups, rows)
        result.iterations = max(result.iterations, iterations)
        if not stable:
            result.reject(AnswerIssue(
                "QUESTIONNAIRE_CONFIGURATION_ERROR", qn_id, None, None,
                f"问卷{qn_id}的关联规则无法确定，请联系管理员",
            ))
            continue
        result.allowed_question_ids.update(allowed)
        selected: dict[int, tuple[int, int]] = {}
        for group in groups:
            gid = group["id"]
            expected = active[gid]
            if expected is not None:
                result.visible_group_ids.add(gid)
            row = rows.get(gid)
            if row is None or row["active_question_id"] is None:
                continue
            qid = row["active_question_id"]
            if qid != expected:
                result.reject(AnswerIssue(
                    "INVALID_BRANCH", qn_id, gid, qid,
                    f"问卷{qn_id}题组{gid}的题目{qid}不属于当前可见分支",
                ))
                continue
            if is_done_row(index, row):
                result.answered_group_ids.add(gid)
            selected.update({oid: (gid, qid) for oid in row["selected_option_ids"]})
        for oid, (gid, qid) in selected.items():
            targets = index.question_options[qid][oid].get("mutexOptionIds") or []
            if any(target in selected for target in targets):
                result.reject(AnswerIssue(
                    "MUTEX_CONFLICT", qn_id, gid, qid,
                    f"问卷{qn_id}题组{gid}同时选择了互斥选项",
                ))
    return result
