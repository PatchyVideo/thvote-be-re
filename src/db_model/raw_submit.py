from __future__ import annotations

from sqlalchemy import DateTime, Integer, String, Text, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .base import Base


class RawCharacterSubmit(Base):
    __tablename__ = "raw_character"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vote_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    user_ip: Mapped[str] = mapped_column(String(255), nullable=False, default="<unknown>")
    additional_fingreprint: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    payload: Mapped[list] = mapped_column(JSON, nullable=False)


class RawMusicSubmit(Base):
    __tablename__ = "raw_music"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vote_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    user_ip: Mapped[str] = mapped_column(String(255), nullable=False, default="<unknown>")
    additional_fingreprint: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    payload: Mapped[list] = mapped_column(JSON, nullable=False)


class RawCPSubmit(Base):
    __tablename__ = "raw_cp"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vote_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    user_ip: Mapped[str] = mapped_column(String(255), nullable=False, default="<unknown>")
    additional_fingreprint: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    payload: Mapped[list] = mapped_column(JSON, nullable=False)


class RawPaperSubmit(Base):
    __tablename__ = "raw_paper"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vote_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    user_ip: Mapped[str] = mapped_column(String(255), nullable=False, default="<unknown>")
    additional_fingreprint: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    papers_json: Mapped[str] = mapped_column(Text, nullable=False)


class RawDojinSubmit(Base):
    __tablename__ = "raw_dojin"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vote_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    user_ip: Mapped[str] = mapped_column(String(255), nullable=False, default="<unknown>")
    additional_fingreprint: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    payload: Mapped[list] = mapped_column(JSON, nullable=False)


Index("idx_raw_character_vote_created", RawCharacterSubmit.vote_id, RawCharacterSubmit.created_at.desc())
Index("idx_raw_music_vote_created", RawMusicSubmit.vote_id, RawMusicSubmit.created_at.desc())
Index("idx_raw_cp_vote_created", RawCPSubmit.vote_id, RawCPSubmit.created_at.desc())
Index("idx_raw_paper_vote_created", RawPaperSubmit.vote_id, RawPaperSubmit.created_at.desc())
Index("idx_raw_dojin_vote_created", RawDojinSubmit.vote_id, RawDojinSubmit.created_at.desc())

