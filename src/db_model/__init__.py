"""
PostgreSQL数据库模型定义

定义了用于投票数据保存的数据模型。
"""

from .base import Base
from .character import Character
from .cp import Cp
from .music import Music
from .questionnaire import Questionnaire
from .raw_submit import (
    RawCharacterSubmit,
    RawCPSubmit,
    RawDojinSubmit,
    RawMusicSubmit,
    RawPaperSubmit,
)
from .user import User

__version__ = "1.0.0"
__author__ = "FunnyAWM"
__all__ = [
    "User",
    "Character",
    "Base",
    "Cp",
    "Questionnaire",
    "Music",
    "RawCharacterSubmit",
    "RawMusicSubmit",
    "RawCPSubmit",
    "RawPaperSubmit",
    "RawDojinSubmit",
]
