"""Voteable models — cross-year stable voting objects.

These tables hold the canonical identity for voteable items.
candidate_* tables reference these via voteable_id.
"""

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from .base import Base


class VoteableCharacter(Base):
    __tablename__ = "voteable_character"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    name_jp = Column(String(255), nullable=False, server_default="")
    origin = Column(String(255), nullable=False, server_default="")
    type = Column(String(64), nullable=False, server_default="")
    first_appearance = Column(String(16), nullable=True)
    aliases = Column(JSONB, nullable=False, server_default="[]")
    old_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class VoteableMusic(Base):
    __tablename__ = "voteable_music"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    name_jp = Column(String(255), nullable=False, server_default="")
    type = Column(String(64), nullable=False, server_default="")
    first_appearance = Column(String(16), nullable=True)
    album = Column(String(255), nullable=True)
    aliases = Column(JSONB, nullable=False, server_default="[]")
    old_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
