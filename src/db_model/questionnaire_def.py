"""Questionnaire structure models (B-039).

Mirrors the frontend ``questionnaireV2`` shape so the structure endpoint can
feed the frontend parser directly. Numeric ids follow the frontend's
structured-encoding convention. related/mutex rules are stored as JSON arrays.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class QuestionnaireDef(Base):
    __tablename__ = "questionnaire_def"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    introduction: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(8), nullable=False, default="main")
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class QuestionGroupDef(Base):
    __tablename__ = "question_group_def"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    questionnaire_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hidden_by_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )


class QuestionDef(Base):
    __tablename__ = "question_def"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(8), nullable=False, default="Single")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    introduction: Mapped[str] = mapped_column(Text, nullable=False, default="")
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_input_len: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1000
    )


class OptionDef(Base):
    __tablename__ = "option_def"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    related_question_ids: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    mutex_option_ids: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    option_group: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class PaperAnswer(Base):
    """Structured questionnaire answers (replaces the opaque papers_json blob)."""

    __tablename__ = "paper_answer"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vote_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    vote_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    questionnaire_id: Mapped[int] = mapped_column(Integer, nullable=False)
    group_id: Mapped[int] = mapped_column(Integer, nullable=False)
    active_question_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    selected_option_ids: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    input_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "vote_id",
            "vote_year",
            "questionnaire_id",
            "group_id",
            name="uq_paper_answer_voter_group",
        ),
    )
