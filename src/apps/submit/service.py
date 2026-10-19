"""Submit service layer."""

import json
from datetime import datetime, timezone

from src.apps.submit.dao import SubmitDAO
from src.apps.submit.nomination_service import (
    domain_allowed,
    publish_date_eligible,
    within_window,
)
from src.apps.submit.schemas import (
    CharacterSubmitRest,
    CPSubmitRest,
    DojinSubmitRest,
    MusicSubmitRest,
    NominationItemResult,
    NominationSubmitResult,
    PaperSubmitRest,
    SubmitMetadata,
    VotingStatistics,
    VotingStatus,
    scrub_metadata,
)


class QuestionnaireNotCompletedError(Exception):
    """Raised when a user tries to vote before completing the questionnaire."""


class InvalidCandidateError(ValueError):
    """Raised when a submitted character/music/cp id is not a candidate of the year.

    Subclass of ``ValueError`` so the REST routers keep mapping it to 422; the
    GraphQL bridge maps it to ``INVALID_CANDIDATE`` (R-04/D-09: unknown ids used
    to be stored silently and then dropped by the tally, so the user saw
    "vote submitted" while nothing counted).
    """


class NominationClosedError(Exception):
    """Raised when nomination is attempted outside the nomination window."""


class NominationNotConfiguredError(Exception):
    """Raised when the nomination window is not configured."""


class SubmitValidator:
    """Validator for submit data."""

    # papers_json 上限:防滥用存储。前端真实问卷 ≈ 几 KB,256KB 给足余量。
    PAPERS_JSON_MAX_BYTES = 256 * 1024

    # 二创提名(PRD 2.6):共 5 个票位;字段长度按 PRD 上限。
    DOJIN_MAX_ITEMS = 5
    DOJIN_URL_MAX = 2048
    DOJIN_TITLE_MAX = 256
    DOJIN_AUTHOR_MAX = 128
    DOJIN_REASON_MAX = 1024
    DOJIN_IMAGE_URL_MAX = 2048

    # CP 组合(PRD 2.5.4):2~3 人;每人最多 4 个组合。
    CP_MIN_MEMBERS = 2
    CP_MAX_MEMBERS = 3
    CP_MAX_ITEMS = 4

    def validate_character(self, data: CharacterSubmitRest) -> CharacterSubmitRest:
        """Validate character submit data."""
        chset: set[str] = set()
        first_set = False
        if len(data.characters) < 1 or len(data.characters) > 8:
            raise ValueError(f"数量{len(data.characters)}不在范围内[1,8]")
        for c in data.characters:
            if not c.id:
                raise ValueError("角色ID为空")
            if (c.reason is not None) and len(c.reason) > 4096:
                raise ValueError("理由过长")
            if bool(c.first):
                if first_set:
                    raise ValueError("多个本命")
                first_set = True
            if c.id in chset:
                raise ValueError(f"{c.id}已存在")
            chset.add(c.id)
        return data

    def validate_music(self, data: MusicSubmitRest) -> MusicSubmitRest:
        """Validate music submit data."""
        chset: set[str] = set()
        first_set = False
        if len(data.music) < 1 or len(data.music) > 12:
            raise ValueError(f"数量{len(data.music)}不在范围内[1,12]")
        for c in data.music:
            if not c.id:
                raise ValueError("曲目ID为空")
            if (c.reason is not None) and len(c.reason) > 4096:
                raise ValueError("理由过长")
            if bool(c.first):
                if first_set:
                    raise ValueError("多个本命")
                first_set = True
            if c.id in chset:
                raise ValueError(f"{c.id}已存在")
            chset.add(c.id)
        return data

    def validate_cp(self, data: CPSubmitRest) -> CPSubmitRest:
        """Validate CP submit data against PRD 2.5.4 combination rules.

        Rejects (message pinpoints the offending combination, as the PRD asks):
        - fewer than 2 or more than 3 members, or a blank member id;
        - the same member listed twice / three members not pairwise distinct;
        - the same combination twice (order-insensitive — "包含相同角色的组合，
          即使角色顺序不同…也视为同样的组合");
        - an ``active`` member outside the combination.
        """
        first_set = False
        if len(data.cps) < 1 or len(data.cps) > self.CP_MAX_ITEMS:
            raise ValueError(f"数量{len(data.cps)}不在范围内[1,{self.CP_MAX_ITEMS}]")
        seen_keys: set[frozenset[str]] = set()
        for idx, c in enumerate(data.cps, start=1):
            if (c.reason is not None) and len(c.reason) > 4096:
                raise ValueError(f"第{idx}个组合理由过长")
            if bool(c.first):
                if first_set:
                    raise ValueError("多个本命")
                first_set = True

            members = [c.id_a, c.id_b] + ([c.id_c] if c.id_c else [])
            if any(not m for m in members):
                raise ValueError(f"第{idx}个组合存在未填写的角色")
            if not (self.CP_MIN_MEMBERS <= len(members) <= self.CP_MAX_MEMBERS):
                raise ValueError(
                    f"第{idx}个组合人数{len(members)}不在范围内"
                    f"[{self.CP_MIN_MEMBERS},{self.CP_MAX_MEMBERS}]"
                )
            if len(set(members)) != len(members):
                raise ValueError(f"第{idx}个组合存在相同角色")

            key = frozenset(members)
            if key in seen_keys:
                raise ValueError(f"第{idx}个组合与前面的组合重复")
            seen_keys.add(key)

            if c.active is not None and c.active not in members:
                raise ValueError(f"第{idx}个组合的主动方{c.active}不存在")
        return data

    def validate_paper(self, data: PaperSubmitRest) -> PaperSubmitRest:
        """Validate legacy paper submit data.

        papers_json 是不透明业务数据:前端把整棵问卷答案树序列化成一个 JSON
        字符串,结构随问卷内容逐年变化,统计侧也不读这张原始表——所以这里只把
        关「合法 JSON」+「大小上限」+「不能是空/标量载荷」,不校验内部结构
        (对齐旧 Rust 的透传语义,外加大小护栏;详见
        docs/superpowers/specs/2026-06-07-graphql-submit-bridge-design.md §5)。

        「不能是空载荷」是 R-03 的止损:``"{}"`` 这类空 JSON 曾被当作
        「已完成问卷」解锁投票,现在提交期直接拒绝(历史存量行由
        ``SubmitService._require_questionnaire`` 用同一判定兜底)。
        """
        if len(data.papers_json.encode("utf-8")) > self.PAPERS_JSON_MAX_BYTES:
            raise ValueError("问卷数据过大")
        try:
            payload = json.loads(data.papers_json)
        except (json.JSONDecodeError, ValueError):
            raise ValueError("问卷数据不是合法 JSON，请重试")
        if not isinstance(payload, (dict, list)) or not payload:
            raise ValueError("问卷数据为空")
        return data

    @staticmethod
    def is_paper_meaningful(papers_json: str | None) -> bool:
        """True when a stored ``raw_paper`` payload is a non-empty container.

        Shared by ``validate_paper`` (write path) and the vote gate (read path)
        so a row written before this rule existed cannot keep unlocking voting.
        """
        if not papers_json:
            return False
        try:
            payload = json.loads(papers_json)
        except (json.JSONDecodeError, ValueError, TypeError):
            return False
        return isinstance(payload, (dict, list)) and len(payload) > 0

    def validate_dojin(self, data: DojinSubmitRest) -> DojinSubmitRest:
        """Validate dojin submit data (PRD 2.6: 5 nomination slots + lengths)."""
        if len(data.dojins) > self.DOJIN_MAX_ITEMS:
            raise ValueError(
                f"数量{len(data.dojins)}不在范围内[1,{self.DOJIN_MAX_ITEMS}]"
            )
        for idx, item in enumerate(data.dojins, start=1):
            if len(item.author) > self.DOJIN_AUTHOR_MAX:
                raise ValueError(f"第{idx}条作者名过长")
            if len(item.reason) > self.DOJIN_REASON_MAX:
                raise ValueError(f"第{idx}条理由过长")
            if len(item.title) > self.DOJIN_TITLE_MAX:
                raise ValueError(f"第{idx}条作品名过长")
            if len(item.url) > self.DOJIN_URL_MAX:
                raise ValueError(f"第{idx}条URL过长")
            if (
                item.image_url is not None
                and len(item.image_url) > self.DOJIN_IMAGE_URL_MAX
            ):
                raise ValueError(f"第{idx}条图片链接过长")
        return data


class SubmitService:
    """Service for submit operations."""

    def __init__(self, submit_dao: SubmitDAO):
        self.submit_dao = submit_dao
        self.validator = SubmitValidator()

    async def _require_questionnaire(self, vote_id: str) -> None:
        """Vote gate: the user must have completed the questionnaire.

        Transition-safe:
        - a legacy raw_paper submission counts as complete **only when it carries
          real content** (R-03: ``"{}"`` and voided rows used to unlock voting);
        - otherwise structured answers must exist AND satisfy completion
          against the configured questionnaire structure (Block 3).
        """
        legacy = await self.submit_dao.latest_paper_json(vote_id)
        if self.validator.is_paper_meaningful(legacy):
            return
        from src.apps.questionnaire.dao import QuestionnaireDAO
        from src.apps.questionnaire.service import QuestionnaireService
        from src.common.config import get_settings

        year = get_settings().vote_year
        qsvc = QuestionnaireService(QuestionnaireDAO(self.submit_dao.session))
        answers = await qsvc.get_answers(vote_id, year)
        if not answers or not await qsvc.is_complete(vote_id, year):
            raise QuestionnaireNotCompletedError(vote_id)

    async def _require_candidates(self, category: str, tokens: list[str]) -> None:
        """Reject ids that are not candidates of the current vote year (R-04).

        The tally drops unknown ids (``compute.dropped``) while the submit is
        stored, so callers saw "submitted" for a ballot that counted nothing.
        Tokens are matched exactly like the tally does (canonical ``candidate_id``
        or the legacy 8-hex ``old_id``).

        Fail-open only when the year has **no** candidates imported at all —
        there is no whitelist to check against, and such a deployment cannot
        tally anything anyway.  A partially imported year still validates.
        """
        from src.apps.result.whitelist import load_whitelist_db
        from src.common.config import get_settings

        whitelist = await load_whitelist_db(
            self.submit_dao.session, category, get_settings().vote_year
        )
        if not whitelist.entries:
            return
        unknown = sorted({token for token in tokens if token and token not in whitelist})
        if unknown:
            raise InvalidCandidateError(f"候选{unknown[0]}不存在")

    async def submit_character(self, data: CharacterSubmitRest) -> int:
        """Submit character votes."""
        await self._require_questionnaire(data.meta.vote_id)
        validated = self.validator.validate_character(data)
        await self._require_candidates(
            "character", [c.id for c in validated.characters]
        )
        row_data = {
            "vote_id": validated.meta.vote_id,
            "attempt": validated.meta.attempt,
            "created_at": validated.meta.created_at,
            "user_ip": validated.meta.user_ip,
            "additional_fingreprint": validated.meta.additional_fingreprint,
            "fill_duration_ms": validated.meta.fill_duration_ms,
            "client_env": validated.meta.client_env,
            "payload": [x.model_dump() for x in validated.characters],
        }
        return await self.submit_dao.create_character_submit(row_data)

    async def get_character_submit(self, vote_id: str) -> CharacterSubmitRest:
        """Get character submit for a vote ID."""
        row = await self.submit_dao.get_character_submit(vote_id)
        if row is None:
            return CharacterSubmitRest(characters=[], meta=SubmitMetadata())
        return CharacterSubmitRest(
            characters=row["payload"],
            meta=scrub_metadata(
                SubmitMetadata(
                    vote_id=row["vote_id"],
                    attempt=row["attempt"],
                    created_at=row["created_at"],
                    user_ip=row["user_ip"],
                    additional_fingreprint=row["additional_fingreprint"],
                )
            ),
        )

    async def submit_music(self, data: MusicSubmitRest) -> int:
        """Submit music votes."""
        await self._require_questionnaire(data.meta.vote_id)
        validated = self.validator.validate_music(data)
        await self._require_candidates("music", [c.id for c in validated.music])
        row_data = {
            "vote_id": validated.meta.vote_id,
            "attempt": validated.meta.attempt,
            "created_at": validated.meta.created_at,
            "user_ip": validated.meta.user_ip,
            "additional_fingreprint": validated.meta.additional_fingreprint,
            "fill_duration_ms": validated.meta.fill_duration_ms,
            "client_env": validated.meta.client_env,
            "payload": [x.model_dump() for x in validated.music],
        }
        return await self.submit_dao.create_music_submit(row_data)

    async def get_music_submit(self, vote_id: str) -> MusicSubmitRest:
        """Get music submit for a vote ID."""
        row = await self.submit_dao.get_music_submit(vote_id)
        if row is None:
            return MusicSubmitRest(music=[], meta=SubmitMetadata())
        return MusicSubmitRest(
            music=row["payload"],
            meta=scrub_metadata(
                SubmitMetadata(
                    vote_id=row["vote_id"],
                    attempt=row["attempt"],
                    created_at=row["created_at"],
                    user_ip=row["user_ip"],
                    additional_fingreprint=row["additional_fingreprint"],
                )
            ),
        )

    async def submit_cp(self, data: CPSubmitRest) -> int:
        """Submit CP votes."""
        await self._require_questionnaire(data.meta.vote_id)
        validated = self.validator.validate_cp(data)
        await self._require_candidates(
            "character",
            [
                member
                for cp in validated.cps
                for member in (cp.id_a, cp.id_b, cp.id_c)
                if member
            ],
        )
        row_data = {
            "vote_id": validated.meta.vote_id,
            "attempt": validated.meta.attempt,
            "created_at": validated.meta.created_at,
            "user_ip": validated.meta.user_ip,
            "additional_fingreprint": validated.meta.additional_fingreprint,
            "fill_duration_ms": validated.meta.fill_duration_ms,
            "client_env": validated.meta.client_env,
            "payload": [x.model_dump() for x in validated.cps],
        }
        return await self.submit_dao.create_cp_submit(row_data)

    async def get_cp_submit(self, vote_id: str) -> CPSubmitRest:
        """Get CP submit for a vote ID."""
        row = await self.submit_dao.get_cp_submit(vote_id)
        if row is None:
            return CPSubmitRest(cps=[], meta=SubmitMetadata())
        return CPSubmitRest(
            cps=row["payload"],
            meta=scrub_metadata(
                SubmitMetadata(
                    vote_id=row["vote_id"],
                    attempt=row["attempt"],
                    created_at=row["created_at"],
                    user_ip=row["user_ip"],
                    additional_fingreprint=row["additional_fingreprint"],
                )
            ),
        )

    async def submit_paper(self, data: PaperSubmitRest) -> int:
        """Submit paper votes."""
        validated = self.validator.validate_paper(data)
        row_data = {
            "vote_id": validated.meta.vote_id,
            "attempt": validated.meta.attempt,
            "created_at": validated.meta.created_at,
            "user_ip": validated.meta.user_ip,
            "additional_fingreprint": validated.meta.additional_fingreprint,
            "fill_duration_ms": validated.meta.fill_duration_ms,
            "client_env": validated.meta.client_env,
            "papers_json": validated.papers_json,
        }
        return await self.submit_dao.create_paper_submit(row_data)

    async def get_paper_submit(self, vote_id: str) -> PaperSubmitRest:
        """Get paper submit for a vote ID."""
        row = await self.submit_dao.get_paper_submit(vote_id)
        if row is None:
            return PaperSubmitRest(papers_json="{}", meta=SubmitMetadata())
        return PaperSubmitRest(
            papers_json=row["papers_json"],
            meta=scrub_metadata(
                SubmitMetadata(
                    vote_id=row["vote_id"],
                    attempt=row["attempt"],
                    created_at=row["created_at"],
                    user_ip=row["user_ip"],
                    additional_fingreprint=row["additional_fingreprint"],
                )
            ),
        )

    async def submit_dojin(self, data: DojinSubmitRest) -> int:
        """Submit dojin votes (raw archival store, no review)."""
        validated = self.validator.validate_dojin(data)
        row_data = {
            "vote_id": validated.meta.vote_id,
            "attempt": validated.meta.attempt,
            "created_at": validated.meta.created_at,
            "user_ip": validated.meta.user_ip,
            "additional_fingreprint": validated.meta.additional_fingreprint,
            "fill_duration_ms": validated.meta.fill_duration_ms,
            "client_env": validated.meta.client_env,
            "payload": [x.model_dump() for x in validated.dojins],
        }
        return await self.submit_dao.create_dojin_submit(row_data)

    async def submit_dojin_nominations(
        self,
        data: DojinSubmitRest,
        settings,
        scraper,
        now: datetime | None = None,
    ) -> NominationSubmitResult:
        """Validate + store dojin nominations for review.

        Per-item flow: domain allowlist → scraper (udid + publish date) →
        publish-time eligibility → dedup by (vote_id, udid) → store pending.
        Also writes a raw_dojin archival record (existing behaviour).

        ``validate_dojin`` runs first: the GraphQL path used to skip it, so a
        single mutation could store unlimited nominations with arbitrarily long
        fields (R-06).  The per-item scraper calls stay serial in this batch —
        making them concurrent is a separate performance change.
        """
        now = now or datetime.now(timezone.utc)
        self.validator.validate_dojin(data)

        if not settings.nomination_start_iso and not settings.nomination_end_iso:
            raise NominationNotConfiguredError()
        if not within_window(
            now, settings.nomination_start_iso, settings.nomination_end_iso
        ):
            raise NominationClosedError()

        # archival raw store (best-effort, mirrors old behaviour)
        await self.submit_dao.create_dojin_submit({
            "vote_id": data.meta.vote_id,
            "attempt": data.meta.attempt,
            "created_at": data.meta.created_at,
            "user_ip": data.meta.user_ip,
            "additional_fingreprint": data.meta.additional_fingreprint,
            "payload": [x.model_dump() for x in data.dojins],
        })

        result = NominationSubmitResult()
        allow = settings.dojin_domain_allowlist
        for idx, item in enumerate(data.dojins):
            if not domain_allowed(item.url, allow):
                result.rejected.append(
                    NominationItemResult(index=idx, reason="域名不允许")
                )
                continue

            udid, publish_date = await self._scrape_meta(scraper, item.url)

            if not publish_date_eligible(
                publish_date,
                settings.work_eligible_start_iso,
                settings.work_eligible_end_iso,
            ):
                result.rejected.append(
                    NominationItemResult(index=idx, reason="作品发布时间不符")
                )
                continue

            if udid and await self.submit_dao.nomination_exists(
                data.meta.vote_id, udid
            ):
                result.skipped.append(
                    NominationItemResult(index=idx, reason="重复提名")
                )
                continue

            await self.submit_dao.create_nomination({
                "vote_id": data.meta.vote_id,
                "udid": udid,
                "url": item.url,
                "title": item.title,
                "author": item.author,
                "dojin_type": item.dojin_type,
                "image_url": item.image_url,
                "reason": item.reason,
                "publish_date": publish_date,
                "status": "pending",
            })
            result.accepted += 1
        return result

    @staticmethod
    async def _scrape_meta(scraper, url: str):
        """Return (udid, publish_date) from scraper; (None, None) on failure."""
        import asyncio

        try:
            resp = await asyncio.wait_for(scraper.scrape_url(url), timeout=5)
        except Exception:
            return None, None
        data = getattr(resp, "data", None)
        if data is None:
            return None, None
        udid = getattr(data, "udid", None)
        ptime = getattr(data, "ptime", None)
        publish_date = None
        if ptime:
            try:
                publish_date = datetime.fromisoformat(
                    str(ptime).replace("Z", "+00:00")
                )
                if publish_date.tzinfo is None:
                    publish_date = publish_date.replace(tzinfo=timezone.utc)
            except ValueError:
                publish_date = None
        return udid, publish_date

    async def get_dojin_submit(self, vote_id: str) -> DojinSubmitRest:
        """Get dojin submit for a vote ID."""
        row = await self.submit_dao.get_dojin_submit(vote_id)
        if row is None:
            return DojinSubmitRest(dojins=[], meta=SubmitMetadata())
        return DojinSubmitRest(
            dojins=row["payload"],
            meta=scrub_metadata(
                SubmitMetadata(
                    vote_id=row["vote_id"],
                    attempt=row["attempt"],
                    created_at=row["created_at"],
                    user_ip=row["user_ip"],
                    additional_fingreprint=row["additional_fingreprint"],
                )
            ),
        )

    async def get_voting_status(self, vote_id: str) -> VotingStatus:
        """Get voting status for a vote ID."""
        status = await self.submit_dao.has_submit(vote_id)
        return VotingStatus(**status)

    async def get_voting_statistics(self) -> VotingStatistics:
        """Get voting statistics."""
        stats = await self.submit_dao.get_statistics()
        return VotingStatistics(**stats)
