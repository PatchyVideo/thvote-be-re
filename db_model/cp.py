from sqlalchemy import Column, ForeignKey, String, DateTime, Index
from sqlalchemy.dialects.postgresql import ARRAY

from base import Base


class Cp(Base):
    __tablename__ = 'cp'

    # id TEXT PRIMARY KEY REFERENCES user(id)
    id = Column(String, ForeignKey('user.id', ondelete='CASCADE'), primary_key=True)

    # submit_datetime DATETIME NOT NULL
    submit_datetime = Column(DateTime, nullable=False)

    # cp_list TEXT[] NOT NULL
    cp_list = Column(ARRAY(String), nullable=False)

    # CREATE INDEX idx_cp_list_gin ON cp(cp_list) USING GIN(cp_list)
    __table_args__ = (
        Index('idx_cp_list_gin', 'cp_list', postgresql_using='gin'),
    )
