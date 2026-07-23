"""ComputeDAO — reads raw vote + candidate data from PostgreSQL for computation."""

from __future__ import annotations

import logging
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db_model.candidate import CandidateCharacter, CandidateMusic, FinalRanking
from src.db_model.questionnaire_def import OptionDef, PaperAnswer, QuestionDef
from src.db_model.raw_submit import (
    RawCharacterSubmit,
    RawCPSubmit,
    RawMusicSubmit,
)

logger = logging.getLogger(__name__)


def _normalize_items(raw_list: list) -> list[dict]:
    """Backward-compat: old list[str] → list[dict]."""
    result = []
    for item in raw_list or []:
        if isinstance(item, str):
            result.append({"id": item, "first": False, "reason": None})
        elif isinstance(item, dict):
            result.append(item)
    return result


class ComputeDAO:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _latest_per_vote(rows) -> list[tuple[str, datetime, list[dict]]]:
        """每个 vote_id 取最新一行(created_at desc, attempt desc)。
        若该最新行被作废(invalidated),整个 vote_id 丢弃——作废=删除该账号当前投票,
        而非回退到更旧的提交(legacy 多行选民才可能有多行)。sqlite/PG 通吃,不用 DISTINCT ON。
        """
        ordered = sorted(
            rows, key=lambda r: (r.created_at, r.attempt or 0), reverse=True
        )
        latest: dict[str, object] = {}
        for r in ordered:
            if r.vote_id not in latest:
                latest[r.vote_id] = r  # desc 排序后首次出现 = 最新行
        return [
            (r.vote_id, r.created_at, _normalize_items(r.payload))
            for r in latest.values()
            if not r.invalidated  # 最新行被作废 → 丢弃整个 vote_id
        ]

    async def load_char_votes(self) -> list[tuple[str, datetime, list[dict]]]:
        rows = (await self.session.execute(select(RawCharacterSubmit))).scalars().all()
        return self._latest_per_vote(rows)

    async def load_music_votes(self) -> list[tuple[str, datetime, list[dict]]]:
        rows = (await self.session.execute(select(RawMusicSubmit))).scalars().all()
        return self._latest_per_vote(rows)

    async def load_cp_votes(self) -> list[tuple[str, datetime, list[dict]]]:
        rows = (await self.session.execute(select(RawCPSubmit))).scalars().all()
        return self._latest_per_vote(rows)

    async def load_questionnaire_votes(
        self, vote_year: int
    ) -> list[tuple[str, list[dict]]]:
        """从 paper_answer(B-039 结构化表)读问卷回答,按语义 code 输出。

        注意:paper_answer 没有 invalidated 标志,admin 作废动作触达不到问卷答案。
        题/选项缺 code 的会被跳过(无法按语义码寻址):整行(问题缺 code)或单个
        选项(选项缺 code,该行其余有 code 的选项仍保留)都计入跳过汇总。
        """
        q_codes = dict(
            (await self.session.execute(select(QuestionDef.id, QuestionDef.code))).all()
        )
        o_codes = dict(
            (await self.session.execute(select(OptionDef.id, OptionDef.code))).all()
        )
        rows = (
            await self.session.execute(
                select(PaperAnswer).where(PaperAnswer.vote_year == vote_year)
            )
        ).scalars().all()

        grouped: dict[str, list[dict]] = {}
        skipped_questions = 0
        skipped_options = 0
        for r in rows:
            if r.active_question_id is None:
                continue
            qcode = q_codes.get(r.active_question_id)
            if not qcode:
                skipped_questions += 1
                continue
            answers = []
            for oid in r.selected_option_ids or []:
                ocode = o_codes.get(oid)
                if ocode:
                    answers.append(ocode)
                else:
                    skipped_options += 1
            grouped.setdefault(r.vote_id, []).append(
                {"id": qcode, "answer": answers, "answer_str": r.input_text}
            )
        if skipped_questions or skipped_options:
            logger.debug(
                "questionnaire feed: skipped %d rows (question without code), "
                "%d options without code",
                skipped_questions,
                skipped_options,
            )
        return list(grouped.items())

    async def upsert_candidates(
        self, vote_year: int, category: str, items: list[dict]
    ) -> int:
        """Bulk upsert candidate rows. Returns number of rows upserted.

        After voteable refactor, items contain voteable_id as the unique key.
        """
        Model = CandidateCharacter if category == "character" else CandidateMusic
        model_columns = {
            c.key for c in Model.__table__.columns if c.key not in ("id", "vote_year")
        }
        count = 0
        for item in items:
            filtered = {k: v for k, v in item.items() if k in model_columns}
            vid = int(filtered.get("voteable_id", 0))
            if not vid:
                continue
            existing = (
                await self.session.execute(
                    select(Model).where(
                        Model.vote_year == vote_year,
                        Model.voteable_id == vid,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                for k, v in filtered.items():
                    if k != "voteable_id" and hasattr(existing, k):
                        setattr(existing, k, v)
            else:
                row = Model(vote_year=vote_year, **filtered)
                self.session.add(row)
            count += 1
        await self.session.commit()
        return count

    async def save_final_ranking(
        self, vote_year: int, category: str, entries: list[dict]
    ) -> int:
        """Archive final ranking for historical comparison."""
        count = 0
        for entry in entries:
            rank_list = entry.get("rank", [{}])
            rank = entry.get("display_rank") or (
                rank_list[0].get("rank", 0) if rank_list else 0
            )
            vc = rank_list[0].get("vote_count", 0) if rank_list else 0
            fc = rank_list[0].get("favorite_vote_count", 0) if rank_list else 0
            existing = (
                await self.session.execute(
                    select(FinalRanking).where(
                        FinalRanking.vote_year == vote_year,
                        FinalRanking.category == category,
                        FinalRanking.name == entry["name"],
                    )
                )
            ).scalar_one_or_none()
            if existing:
                existing.rank = rank  # update rank if character moved
                existing.vote_count = vc
                existing.first_vote_count = fc
            else:
                self.session.add(
                    FinalRanking(
                        vote_year=vote_year,
                        category=category,
                        rank=rank,
                        name=entry["name"],
                        vote_count=vc,
                        first_vote_count=fc,
                    )
                )
            count += 1
        await self.session.commit()
        return count

    async def list_candidates(
        self,
        category: str,
        vote_year: int,
        q: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list, int]:
        from sqlalchemy import func as sqlfunc
        from src.db_model.candidate import CandidateCharacter, CandidateMusic
        from src.db_model.voteable import VoteableCharacter, VoteableMusic
        from src.db_model.work import Work

        if category == "character":
            model = CandidateCharacter
            vmodel = VoteableCharacter
        else:
            model = CandidateMusic
            vmodel = VoteableMusic

        base = (
            select(
                model.id, model.vote_year, model.voteable_id,
                vmodel.name, vmodel.name_jp, vmodel.type,
                vmodel.first_appearance,
                Work.id, Work.name, Work.type,
            )
            .outerjoin(vmodel, model.voteable_id == vmodel.id)
            .outerjoin(Work, vmodel.work_id == Work.id)
            .where(model.vote_year == vote_year)
        )
        if q:
            base = base.where(vmodel.name.ilike(f"%{q}%"))

        total = (await self.session.execute(
            select(sqlfunc.count()).select_from(base.subquery())
        )).scalar_one()
        rows = (await self.session.execute(
            base.order_by(vmodel.name)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )).all()
        # Return as list of dicts with joined data
        items = [
            {
                "id": r[0], "vote_year": r[1], "voteable_id": r[2],
                "name": r[3], "name_jp": r[4] or "",
                "type": r[5] or "", "first_appearance": r[6],
                "work_id": r[7], "work_name": r[8] or "",
                "work_type": r[9] or "",
            }
            for r in rows
        ]
        return items, total

    async def delete_candidate(self, candidate_id: int, category: str) -> bool:
        from sqlalchemy import delete
        from src.db_model.candidate import CandidateCharacter, CandidateMusic

        model = CandidateCharacter if category == "character" else CandidateMusic
        result = await self.session.execute(
            delete(model).where(model.id == candidate_id)
        )
        await self.session.commit()
        return result.rowcount > 0

    async def update_candidate(
        self, candidate_id: int, category: str, fields: dict
    ) -> str:
        """Update one candidate row. Returns 'ok' / 'not_found' / 'conflict'.

        After voteable refactor, only voteable_id is writable.
        Conflict: another candidate in same vote_year already has target voteable_id.
        """
        model = CandidateCharacter if category == "character" else CandidateMusic
        valid_cols = {
            c.key for c in model.__table__.columns if c.key not in ("id", "vote_year")
        }
        row = (await self.session.execute(
            select(model).where(model.id == candidate_id)
        )).scalar_one_or_none()
        if row is None:
            return "not_found"

        new_voteable_id = fields.get("voteable_id")
        if new_voteable_id is not None:
            new_vid = int(new_voteable_id)
            if new_vid != row.voteable_id:
                dup = (await self.session.execute(
                    select(model).where(
                        model.vote_year == row.vote_year,
                        model.voteable_id == new_vid,
                        model.id != candidate_id,
                    )
                )).scalar_one_or_none()
                if dup is not None:
                    return "conflict"

        for k, v in fields.items():
            if k in valid_cols:
                setattr(row, k, v)
        await self.session.commit()
        return "ok"

    # ── merge / dedup (B-040) ────────────────────────────────────────────────

    @staticmethod
    def _candidate_model(category: str):
        from src.db_model.candidate import CandidateCharacter, CandidateMusic
        return CandidateCharacter if category == "character" else CandidateMusic

    async def set_merged_into(
        self, candidate_id: int, category: str, target_id: int | None
    ) -> str:
        """Point a candidate at a canonical one (or clear it). Returns status."""
        model = self._candidate_model(category)
        row = (await self.session.execute(
            select(model).where(model.id == candidate_id)
        )).scalar_one_or_none()
        if row is None:
            return "not_found"
        if target_id is not None:
            target = (await self.session.execute(
                select(model).where(model.id == target_id)
            )).scalar_one_or_none()
            if target is None:
                return "target_not_found"
            if target_id == candidate_id:
                return "self"
        if hasattr(row, "merged_into"):
            row.merged_into = target_id
        await self.session.commit()
        return "ok"

    async def list_merges(self, category: str, vote_year: int) -> list[dict]:
        """After voteable refactor: merge_into column removed. Returns empty."""
        return []

    async def auto_merge(self, category: str, vote_year: int) -> int:
        """Detect + apply name-based merges for a year. Returns merges applied.

        Note: candidate tables have UNIQUE(vote_year, name), so exact-name
        duplicates cannot coexist — this is a no-op under the current schema,
        wired for cross-source dedup / future constraint relaxation.
        """
        from src.apps.admin.candidate_merge import detect_merges

        model = self._candidate_model(category)
        rows = (await self.session.execute(
            select(model).where(model.vote_year == vote_year)
        )).scalars().all()
        # After voteable refactor, name/album columns no longer exist on candidate.
        # Use getattr to avoid AttributeError; auto-merge is a no-op.
        dicts = [
            {
                "id": r.id, "vote_year": r.vote_year,
                "name": getattr(r, "name", ""),
                "album": getattr(r, "album", None),
            }
            for r in rows
        ]
        merges = detect_merges(category, dicts)
        # merged_into column removed after voteable refactor — skip assignment
        by_id = {r.id: r for r in rows}
        for dup_id, canonical_id in merges:
            if dup_id in by_id and hasattr(by_id[dup_id], "merged_into"):
                by_id[dup_id].merged_into = canonical_id
        if merges:
            await self.session.commit()
        return len(merges)
