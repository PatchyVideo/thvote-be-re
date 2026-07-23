"""Work model — cross-cutting catalog of Touhou works/albums."""

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from .base import Base


class Work(Base):
    __tablename__ = "work"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    type = Column(String(16), nullable=False)  # old | new | CD | book | others
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
