"""Voteable models — cross-year stable voting objects.

These tables hold the canonical identity for voteable items.
candidate_* tables reference these via voteable_id.
"""

from sqlalchemy import JSON, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func

from .base import Base


class VoteableCharacter(Base):
    __tablename__ = "voteable_character"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    name_jp = Column(String(255), nullable=False, server_default="")
    type = Column(String(64), nullable=False, server_default="")
    first_appearance = Column(String(16), nullable=True)
    work_id = Column(Integer, ForeignKey("work.id"), nullable=True)
    aliases = Column(JSON, nullable=False, server_default="[]")
    old_id = Column(String(64), nullable=True)
    # 资源类 URL：立绘/头像（由管理台维护，公共 vote-objects 接口下发）
    image_url = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class VoteableMusic(Base):
    __tablename__ = "voteable_music"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    name_jp = Column(String(255), nullable=False, server_default="")
    type = Column(String(64), nullable=False, server_default="")
    first_appearance = Column(String(16), nullable=True)
    work_id = Column(Integer, ForeignKey("work.id"), nullable=True)
    aliases = Column(JSON, nullable=False, server_default="[]")
    old_id = Column(String(64), nullable=True)
    # 资源类 URL：封面 + 试听；include = 收录专辑（用于专辑筛选/展示）
    image_url = Column(Text, nullable=True)
    music_url = Column(Text, nullable=True)
    include = Column(JSON, nullable=False, server_default="[]")
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
