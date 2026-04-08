from sqlalchemy import Column, DateTime, ForeignKey, Index, String
from sqlalchemy.types import JSON

from .base import Base


class Music(Base):
    __tablename__ = "music"

    # id TEXT PRIMARY KEY REFERENCES user(id)
    id = Column(String, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True)

    # submit_datetime DATETIME NOT NULL
    submit_datetime = Column(DateTime, nullable=False)

    # music_list JSON NOT NULL (list of music ids)
    music_list = Column(JSON, nullable=False)

    # Generic index for cross-database support.
    __table_args__ = (Index("idx_music_list", "music_list"),)
