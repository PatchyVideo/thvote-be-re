from sqlalchemy import Column, ForeignKey, String, DateTime, Index
from sqlalchemy.dialects.postgresql import ARRAY

from base import Base


class Character(Base):
    __tablename__ = 'character'

    # id TEXT PRIMARY KEY REFERENCES user(id)
    id = Column(String, ForeignKey('user.id', ondelete='CASCADE'), primary_key=True)

    # submit_datetime DATETIME NOT NULL
    submit_datetime = Column(DateTime, nullable=False)

    # character_list TEXT[] NOT NULL
    character_list = Column(ARRAY(String), nullable=False)

    # CREATE INDEX idx_character_list_gin ON character(character_list) USING GIN(character_list)
    __table_args__ = (
        Index('idx_character_list_gin', 'character_list', postgresql_using='gin'),
    )
