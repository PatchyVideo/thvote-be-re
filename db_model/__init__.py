from .character import Character
from .base import Base
from .user import User
from .cp import Cp
from .questionnaire import Questionnaire
from .music import Music

"""
PostgreSQL数据库模型定义

定义了用于投票数据保存的数据模型。
"""
__version__ = "1.0.0"
__author__ = "FunnyAWM"
__all__ = [
    "User",
    "Character",
    "Base",
    "Cp",
    "Questionnaire",
    "Music"
]
