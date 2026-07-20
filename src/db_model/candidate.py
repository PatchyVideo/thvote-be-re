"""Candidate junction models — which voteables participate in which vote_year.

After the voteable refactor, these tables are thin junction tables:
  candidate_character: (vote_year, voteable_id) with UNIQUE
  candidate_music:     (vote_year, voteable_id) with UNIQUE

Metadata (name, type, origin, album, ...) lives on the voteable_* tables.
"""

from sqlalchemy import Column, Integer, String, UniqueConstraint

from .base import Base


class CandidateCharacter(Base):
    __tablename__ = "candidate_character"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vote_year = Column(Integer, nullable=False, index=True)
    voteable_id = Column(Integer, nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint(
            "vote_year", "voteable_id",
            name="uq_candidate_char_year_voteable",
        ),
    )


class CandidateMusic(Base):
    __tablename__ = "candidate_music"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vote_year = Column(Integer, nullable=False, index=True)
    voteable_id = Column(Integer, nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint(
            "vote_year", "voteable_id",
            name="uq_candidate_music_year_voteable",
        ),
    )


class FinalRanking(Base):
    __tablename__ = "final_ranking"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vote_year = Column(Integer, nullable=False, index=True)
    category = Column(String(16), nullable=False)
    rank = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)
    vote_count = Column(Integer, nullable=False)
    first_vote_count = Column(Integer, nullable=False)
    voteable_id = Column(Integer, nullable=True, index=True)

    __table_args__ = (
        UniqueConstraint(
            "vote_year", "category", "rank", name="uq_final_ranking_year_cat_rank"
        ),
    )
