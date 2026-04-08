from sqlalchemy import Column, ForeignKey, String, DateTime, Index
from sqlalchemy.types import JSON

from .base import Base


class Questionnaire(Base):
    __tablename__ = "questionnaire"

    # id TEXT PRIMARY KEY REFERENCES user(id)
    id = Column(String, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True)

    # submit_datetime DATETIME NOT NULL
    submit_datetime = Column(DateTime, nullable=False)

    # questionnaire_list JSON NOT NULL
    questionnaire_list = Column(JSON, nullable=False)

    # Generic index for cross-database support.
    __table_args__ = (Index("idx_questionnaire_list", "questionnaire_list"),)
