from __future__ import annotations

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .base import Base


class RawCharacterSubmit(Base):
    __tablename__ = "raw_character"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vote_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    user_ip: Mapped[str] = mapped_column(
        String(255), nullable=False, default="<unknown>"
    )
    additional_fingreprint: Mapped[str | None] = mapped_column(
        String(1024), nullable=True
    )
    # 首次提交的填写活跃耗时(毫秒);改票时服务端保留不覆盖,防机器人靠重提洗掉
    # 首投的"太快"取证信号。反刷票取证,仅记录不拦截(B-045)。
    fill_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 客户端环境指纹 {ua(服务端从请求头取), tz, screen, lang};反刷票取证,
    # 仅记录不拦截。JSON 便于以后加信号不改表(B-046)。
    client_env: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    payload: Mapped[list] = mapped_column(JSON, nullable=False)
    legacy_mongo_id: Mapped[str | None] = mapped_column(
        String(24), nullable=True, unique=True
    )


class RawMusicSubmit(Base):
    __tablename__ = "raw_music"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vote_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    user_ip: Mapped[str] = mapped_column(
        String(255), nullable=False, default="<unknown>"
    )
    additional_fingreprint: Mapped[str | None] = mapped_column(
        String(1024), nullable=True
    )
    # 首次提交的填写活跃耗时(毫秒);改票时服务端保留不覆盖,防机器人靠重提洗掉
    # 首投的"太快"取证信号。反刷票取证,仅记录不拦截(B-045)。
    fill_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 客户端环境指纹 {ua(服务端从请求头取), tz, screen, lang};反刷票取证,
    # 仅记录不拦截。JSON 便于以后加信号不改表(B-046)。
    client_env: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    payload: Mapped[list] = mapped_column(JSON, nullable=False)
    legacy_mongo_id: Mapped[str | None] = mapped_column(
        String(24), nullable=True, unique=True
    )


class RawCPSubmit(Base):
    __tablename__ = "raw_cp"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vote_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    user_ip: Mapped[str] = mapped_column(
        String(255), nullable=False, default="<unknown>"
    )
    additional_fingreprint: Mapped[str | None] = mapped_column(
        String(1024), nullable=True
    )
    # 首次提交的填写活跃耗时(毫秒);改票时服务端保留不覆盖,防机器人靠重提洗掉
    # 首投的"太快"取证信号。反刷票取证,仅记录不拦截(B-045)。
    fill_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 客户端环境指纹 {ua(服务端从请求头取), tz, screen, lang};反刷票取证,
    # 仅记录不拦截。JSON 便于以后加信号不改表(B-046)。
    client_env: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    payload: Mapped[list] = mapped_column(JSON, nullable=False)
    legacy_mongo_id: Mapped[str | None] = mapped_column(
        String(24), nullable=True, unique=True
    )


class RawPaperSubmit(Base):
    __tablename__ = "raw_paper"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vote_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    user_ip: Mapped[str] = mapped_column(
        String(255), nullable=False, default="<unknown>"
    )
    additional_fingreprint: Mapped[str | None] = mapped_column(
        String(1024), nullable=True
    )
    # 首次提交的填写活跃耗时(毫秒);改票时服务端保留不覆盖,防机器人靠重提洗掉
    # 首投的"太快"取证信号。反刷票取证,仅记录不拦截(B-045)。
    fill_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 客户端环境指纹 {ua(服务端从请求头取), tz, screen, lang};反刷票取证,
    # 仅记录不拦截。JSON 便于以后加信号不改表(B-046)。
    client_env: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    papers_json: Mapped[str] = mapped_column(Text, nullable=False)
    legacy_mongo_id: Mapped[str | None] = mapped_column(
        String(24), nullable=True, unique=True
    )


class RawDojinSubmit(Base):
    __tablename__ = "raw_dojin"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vote_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    user_ip: Mapped[str] = mapped_column(
        String(255), nullable=False, default="<unknown>"
    )
    additional_fingreprint: Mapped[str | None] = mapped_column(
        String(1024), nullable=True
    )
    # 首次提交的填写活跃耗时(毫秒);改票时服务端保留不覆盖,防机器人靠重提洗掉
    # 首投的"太快"取证信号。反刷票取证,仅记录不拦截(B-045)。
    fill_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 客户端环境指纹 {ua(服务端从请求头取), tz, screen, lang};反刷票取证,
    # 仅记录不拦截。JSON 便于以后加信号不改表(B-046)。
    client_env: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    payload: Mapped[list] = mapped_column(JSON, nullable=False)
    legacy_mongo_id: Mapped[str | None] = mapped_column(
        String(24), nullable=True, unique=True
    )


Index(
    "idx_raw_character_vote_created",
    RawCharacterSubmit.vote_id,
    RawCharacterSubmit.created_at.desc(),
)
Index(
    "idx_raw_music_vote_created",
    RawMusicSubmit.vote_id,
    RawMusicSubmit.created_at.desc(),
)
Index("idx_raw_cp_vote_created", RawCPSubmit.vote_id, RawCPSubmit.created_at.desc())
Index(
    "idx_raw_paper_vote_created",
    RawPaperSubmit.vote_id,
    RawPaperSubmit.created_at.desc(),
)
Index(
    "idx_raw_dojin_vote_created",
    RawDojinSubmit.vote_id,
    RawDojinSubmit.created_at.desc(),
)


class RawWorkSubmit(Base):
    __tablename__ = "raw_work"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vote_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    user_ip: Mapped[str] = mapped_column(
        String(255), nullable=False, default="<unknown>"
    )
    additional_fingreprint: Mapped[str | None] = mapped_column(
        String(1024), nullable=True
    )
    # 首次提交的填写活跃耗时(毫秒);改票时服务端保留不覆盖,防机器人靠重提洗掉
    # 首投的"太快"取证信号。反刷票取证,仅记录不拦截(B-045)。
    fill_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 客户端环境指纹 {ua(服务端从请求头取), tz, screen, lang};反刷票取证,
    # 仅记录不拦截。JSON 便于以后加信号不改表(B-046)。
    client_env: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    payload: Mapped[list] = mapped_column(JSON, nullable=False)
    legacy_mongo_id: Mapped[str | None] = mapped_column(
        String(24), nullable=True, unique=True
    )


Index(
    "idx_raw_work_vote_created",
    RawWorkSubmit.vote_id,
    RawWorkSubmit.created_at.desc(),
)
