from sqlalchemy import Column, String, ForeignKey, DateTime, Index
from sqlalchemy.dialects.postgresql import ARRAY

from base import Base


class Music(Base):
    __tablename__ = 'music'

    # id TEXT PRIMARY KEY REFERENCES user(id)
    id = Column(String, ForeignKey('user.id', ondelete='CASCADE'), primary_key=True)

    # submit_datetime DATETIME NOT NULL
    submit_datetime = Column(DateTime, nullable=False)

    # music_list TEXT[] NOT NULL
    music_list = Column(ARRAY(String), nullable=False)

    # CREATE INDEX idx_music_list_gin ON music(music_list) USING GIN(music_list)
    __table_args__ = (
        Index('idx_music_list_gin', 'music_list', postgresql_using='gin'),
    )
