from sqlalchemy import Column, ForeignKey, String, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base


class Questionnaire(Base):
    __tablename__ = 'questionnaire'

    # id TEXT PRIMARY KEY REFERENCES user(id)
    id = Column(String, ForeignKey('user.id', ondelete='CASCADE'), primary_key=True)

    # submit_datetime DATETIME NOT NULL
    submit_datetime = Column(DateTime, nullable=False)

    # questionnaire_list JSONB NOT NULL
    questionnaire_list = Column(JSONB, nullable=False)

    # CREATE INDEX idx_questionnaire_list_gin ON questionnaire(questionnaire_list) USING GIN(questionnaire_list)
    __table_args__ = (
        Index('idx_questionnaire_list_gin', 'questionnaire_list', postgresql_using='gin'),
    )
