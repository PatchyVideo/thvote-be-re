"""
PostgreSQL数据库模型定义

定义了用于投票数据保存的数据模型。
"""

from .activity_log import ActivityLog
from .base import Base
from .candidate import CandidateCharacter, CandidateMusic, FinalRanking
from .character import Character
from .cp import Cp
from .dojin_nomination import DojinNomination
from .music import Music
from .questionnaire import Questionnaire
from .questionnaire_def import (
    OptionDef,
    PaperAnswer,
    QuestionDef,
    QuestionGroupDef,
    QuestionnaireDef,
)
from .raw_submit import (
    RawCharacterSubmit,
    RawCPSubmit,
    RawDojinSubmit,
    RawMusicSubmit,
    RawPaperSubmit,
    RawWorkSubmit,
)
from .sync_run_log import SyncRunLog
from .user import User
from .voter_review import VoterReview  # noqa: F401  (registers table for create_all)

__version__ = "1.0.0"
__author__ = "FunnyAWM"
__all__ = [
    "ActivityLog",
    "Base",
    "CandidateCharacter",
    "CandidateMusic",
    "FinalRanking",
    "Character",
    "Cp",
    "DojinNomination",
    "Music",
    "OptionDef",
    "PaperAnswer",
    "Questionnaire",
    "QuestionDef",
    "QuestionGroupDef",
    "QuestionnaireDef",
    "RawCharacterSubmit",
    "RawCPSubmit",
    "RawDojinSubmit",
    "RawMusicSubmit",
    "RawPaperSubmit",
    "RawWorkSubmit",
    "SyncRunLog",
    "User",
    "VoterReview",
]
