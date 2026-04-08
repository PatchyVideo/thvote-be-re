from sqlalchemy import Column, ForeignKey, String, DateTime, Index
from sqlalchemy.types import JSON

from .base import Base


class Character(Base):
    __tablename__ = 'character'

    # id TEXT PRIMARY KEY REFERENCES user(id)
    id = Column(String, ForeignKey('user.id', ondelete='CASCADE'), primary_key=True)

    # submit_datetime DATETIME NOT NULL
    submit_datetime = Column(DateTime, nullable=False)

    # character_list JSON NOT NULL (list of character ids)
    character_list = Column(JSON, nullable=False)

    # Generic index for cross-database support.
    __table_args__ = (
        Index('idx_character_list', 'character_list'),
    )
