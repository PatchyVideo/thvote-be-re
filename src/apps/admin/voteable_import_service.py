"""VoteableImportService — 统一导入通道，唯一数据入口。

覆盖快照回填、未来 THBWiki 导入、管理员手工 CSV 三条来源，全部走同一套
upsert 语义：一行里**提供了**的字段才写，行里没给的键保持 DB 原值不动。

设计依据：docs/superpowers/specs/2026-07-23-tally-db-truth-source-design.md
§五（统一导入通道）。匹配优先级、冲突判定规则见该文档 §5.2/§5.3。
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db_model.candidate import CandidateCharacter, CandidateMusic
from src.db_model.voteable import VoteableCharacter, VoteableMusic
from src.db_model.work import Work

# 行里可以直接写到 voteable_* 表的字段（work/work_type/sort_order/voteable_id
# 走各自的专属处理，不在这份列表里）。
_VOTEABLE_FIELDS = ("name", "name_jp", "type", "first_appearance", "aliases", "old_id")
_INT_FIELDS = ("voteable_id", "sort_order")


def _normalize_aliases(value: Any) -> list[str]:
    """aliases 列：JSON 数组字符串或 ';' 分隔字符串 → list[str]；已是 list 原样返回。"""
    if isinstance(value, list):
        return [str(v) for v in value]
    if not isinstance(value, str) or not value.strip():
        return []
    text = value.strip()
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(v) for v in parsed]
    return [part.strip() for part in text.split(";") if part.strip()]


def _drop_blank(row: dict) -> dict:
    """insertSelective 风格空列过滤：丢弃 None / 纯空白字符串；保留 0、False 等假值。"""
    return {
        k: v for k, v in row.items()
        if v is not None and not (isinstance(v, str) and v.strip() == "")
    }


def _parse(fmt: str, content: str) -> list[dict] | str:
    """解析导入内容。成功返回 list[dict]；失败返回错误说明字符串(parse_error)。"""
    text = (content or "").strip()
    if not text:
        return "内容为空"

    if fmt == "json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            return f"JSON 解析失败: {e}"
        if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
            return "JSON 必须是对象数组"
        rows = [dict(r) for r in data]
    elif fmt == "csv":
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            return "CSV 无表头"
        rows = [dict(r) for r in reader]
    else:
        return f"不支持的 format: {fmt}"

    parsed_rows: list[dict] = []
    for idx, raw in enumerate(rows):
        row = _drop_blank(raw)
        if "aliases" in row:
            row["aliases"] = _normalize_aliases(row["aliases"])
        for field in _INT_FIELDS:
            if field not in row:
                continue
            try:
                row[field] = int(row[field])
            except (TypeError, ValueError):
                return f"第 {idx + 1} 行 {field} 不是合法整数: {row[field]!r}"
        parsed_rows.append(row)
    return parsed_rows


@dataclass
class _Plan:
    """一行的执行计划：写哪个已有行(target=None 即新建) + 关联哪个 work。"""

    row: dict
    target: Any
    work_name: Optional[str]


class VoteableImportService:
    """把一批行 upsert 进 voteable_*（+ 可选 candidate_*），dry-run 与执行同构。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def run(
        self,
        category: str,
        vote_year: int | None,
        format: str,
        content: str,
        dry_run: bool,
    ) -> dict:
        rows = _parse(format, content)
        if isinstance(rows, str):
            return {"parse_error": rows}

        v_model = VoteableCharacter if category == "character" else VoteableMusic
        c_model = CandidateCharacter if category == "character" else CandidateMusic

        by_id, by_old_id, by_name = await self._load_voteable_index(v_model)
        work_by_name = await self._load_work_index()

        report, plans, pending_works, candidate_upserts = self._build_plan(
            rows, by_id, by_old_id, by_name, work_by_name, vote_year
        )

        if report["conflicts"] and not dry_run:
            # 整批拒绝：冲突未清零前不写任何行（先修数据再导）。
            raise ValueError("IMPORT_CONFLICTS")

        if not dry_run:
            await self._execute(
                plans, pending_works, work_by_name, v_model, c_model, vote_year
            )
            await self.session.commit()

        return {
            "create": report["create"],
            "update": report["update"],
            "work_created": report["work_created"],
            "candidate_upserts": candidate_upserts,
            "conflicts": report["conflicts"],
            "totals": report["totals"],
        }

    # ── 索引预载 ─────────────────────────────────────────────────────────────

    async def _load_voteable_index(self, v_model):
        rows = (await self.session.execute(select(v_model))).scalars().all()
        by_id = {r.id: r for r in rows}
        by_old_id = {r.old_id: r for r in rows if r.old_id}
        by_name = {r.name: r for r in rows}
        return by_id, by_old_id, by_name

    async def _load_work_index(self) -> dict[str, int]:
        rows = (await self.session.execute(select(Work))).scalars().all()
        return {w.name: w.id for w in rows}

    # ── 分类 + 报告构建（dry-run 与执行前半段共用，不写库） ───────────────────

    def _build_plan(
        self, rows, by_id, by_old_id, by_name, work_by_name, vote_year
    ):
        create_report: list[dict] = []
        update_report: list[dict] = []
        work_created: list[dict] = []
        conflicts: list[dict] = []
        pending_works: dict[str, str] = {}
        seen_names: set[str] = set()
        seen_old_ids: set[str] = set()
        plans: list[_Plan] = []
        candidate_upserts = 0
        totals = {
            "rows": len(rows),
            "matched_by_id": 0,
            "matched_by_old_id": 0,
            "matched_by_name": 0,
            "created": 0,
        }

        for idx, row in enumerate(rows):
            name = row.get("name")
            old_id = row.get("old_id") or None
            voteable_id = row.get("voteable_id")

            if name is not None and name in seen_names:
                conflicts.append(self._conflict(idx, row, "DUPLICATE_NAME_IN_BATCH"))
                continue
            if old_id is not None and old_id in seen_old_ids:
                conflicts.append(self._conflict(idx, row, "DUPLICATE_OLD_ID_IN_BATCH"))
                continue

            target, matched_by, reason = self._match_row(
                voteable_id, old_id, name, by_id, by_old_id, by_name
            )
            if reason is not None:
                conflicts.append(self._conflict(idx, row, reason))
                continue

            if name is not None:
                seen_names.add(name)
            if old_id is not None:
                seen_old_ids.add(old_id)

            work_name = row.get("work") or None
            if (
                work_name
                and work_name not in work_by_name
                and work_name not in pending_works
            ):
                wtype = row.get("work_type") or "others"
                pending_works[work_name] = wtype
                work_created.append({"name": work_name, "type": wtype})

            plans.append(_Plan(row=row, target=target, work_name=work_name))

            if target is None:
                totals["created"] += 1
                create_report.append(self._create_preview(row, work_name))
            else:
                totals[f"matched_by_{matched_by}"] += 1
                diff = self._diff(target, row, work_name, work_by_name)
                if diff:
                    update_report.append({"voteable_id": target.id, "diff": diff})

            if vote_year is not None:
                candidate_upserts += 1

        report = {
            "create": create_report,
            "update": update_report,
            "work_created": work_created,
            "conflicts": conflicts,
            "totals": totals,
        }
        return report, plans, pending_works, candidate_upserts

    @staticmethod
    def _match_row(voteable_id, old_id, name, by_id, by_old_id, by_name):
        """按 §5.2 优先级匹配：voteable_id → old_id → name → 都未命中(新建)。

        返回 (target|None, matched_by|None, conflict_reason|None)。
        """
        if voteable_id is not None:
            target = by_id.get(voteable_id)
            if target is None:
                return None, None, "VOTEABLE_ID_NOT_FOUND"
            # 同给 old_id 但指向另一行：数据自相矛盾，不猜，进 conflicts（§5.3）。
            if old_id and by_old_id.get(old_id) not in (None, target):
                return None, None, "OLD_ID_VOTEABLE_ID_MISMATCH"
            return target, "id", None

        if old_id and old_id in by_old_id:
            return by_old_id[old_id], "old_id", None

        if name is not None and name in by_name:
            target = by_name[name]
            # name 命中的行已有非空 old_id，且本行也给了不同的非空 old_id。
            if target.old_id and old_id and target.old_id != old_id:
                return None, None, "OLD_ID_MISMATCH"
            return target, "name", None

        return None, None, None

    @staticmethod
    def _conflict(idx: int, row: dict, reason: str) -> dict:
        return {"row": idx, "reason": reason, **row}

    @staticmethod
    def _create_preview(row: dict, work_name: Optional[str]) -> dict:
        preview = {k: row[k] for k in _VOTEABLE_FIELDS if k in row}
        if work_name:
            preview["work"] = work_name
        return preview

    @staticmethod
    def _diff(target, row: dict, work_name: Optional[str], work_by_name: dict) -> dict:
        diff: dict[str, Any] = {}
        for field in _VOTEABLE_FIELDS:
            if field not in row:
                continue
            if getattr(target, field) != row[field]:
                diff[field] = row[field]
        if work_name:
            resolved_id = work_by_name.get(work_name)
            if resolved_id != target.work_id:
                diff["work"] = work_name
        return diff

    # ── 执行(仅 dry_run=False 且无冲突时调用) ─────────────────────────────────

    async def _execute(
        self, plans, pending_works, work_by_name, v_model, c_model, vote_year
    ):
        for name, wtype in pending_works.items():
            work = Work(name=name, type=wtype)
            self.session.add(work)
            await self.session.flush()
            work_by_name[name] = work.id

        for plan in plans:
            obj = plan.target
            if obj is None:
                obj = v_model()
                self.session.add(obj)
            self._apply_fields(obj, plan.row, plan.work_name, work_by_name)
            await self.session.flush()
            if vote_year is not None:
                await self._upsert_candidate(c_model, vote_year, obj.id, plan.row)

    @staticmethod
    def _apply_fields(
        obj, row: dict, work_name: Optional[str], work_by_name: dict
    ) -> None:
        for field in _VOTEABLE_FIELDS:
            if field in row:
                setattr(obj, field, row[field])
        if work_name:
            obj.work_id = work_by_name.get(work_name)

    async def _upsert_candidate(self, c_model, vote_year, voteable_id, row) -> None:
        existing = (
            await self.session.execute(
                select(c_model).where(
                    c_model.vote_year == vote_year,
                    c_model.voteable_id == voteable_id,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = c_model(vote_year=vote_year, voteable_id=voteable_id)
            self.session.add(existing)
        if "sort_order" in row:
            existing.sort_order = row["sort_order"]
