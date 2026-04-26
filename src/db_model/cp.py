from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.types import JSON

from .base import Base


class Cp(Base):
    __tablename__ = "cp"

    # id TEXT PRIMARY KEY REFERENCES user(id)
    id = Column(String, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True)

    # submit_datetime DATETIME NOT NULL
    submit_datetime = Column(DateTime, nullable=False)

    # cp_list JSON NOT NULL (list of cp ids)
    cp_list = Column(JSON, nullable=False)
