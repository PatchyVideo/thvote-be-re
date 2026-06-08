from sqlalchemy import Column, Integer, String, UniqueConstraint

from .base import Base


class CandidateCharacter(Base):
    __tablename__ = "candidate_character"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vote_year = Column(Integer, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    name_jp = Column(String(255), nullable=False, server_default="")
    origin = Column(String, nullable=False, server_default="")
    type = Column(String(64), nullable=False, server_default="")
    first_appearance = Column(String(16), nullable=True)
    # 规范化合并:非空指向主候选 id;NULL = 自身即规范化主候选
    merged_into = Column(Integer, nullable=True, index=True)

    __table_args__ = (
        UniqueConstraint("vote_year", "name", name="uq_candidate_char_year_name"),
    )


class CandidateMusic(Base):
    __tablename__ = "candidate_music"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vote_year = Column(Integer, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    name_jp = Column(String(255), nullable=False, server_default="")
    type = Column(String(64), nullable=False, server_default="")
    first_appearance = Column(String(16), nullable=True)
    album = Column(String(255), nullable=True)
    # 规范化合并:非空指向主候选 id;NULL = 自身即规范化主候选
    merged_into = Column(Integer, nullable=True, index=True)

    __table_args__ = (
        UniqueConstraint("vote_year", "name", name="uq_candidate_music_year_name"),
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

    __table_args__ = (
        UniqueConstraint(
            "vote_year", "category", "rank", name="uq_final_ranking_year_cat_rank"
        ),
    )
