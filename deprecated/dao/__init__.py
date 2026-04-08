"""
已废弃的后端 DAO 草稿模型。

这些文件只保留短期参考价值，不再作为正式 schema 层扩展。
"""
from .LoginData import LoginData
from .RegisterData import RegisterData
from .BaseQuery import BaseQuery
from .CompletionRatesQuery import CompletionRatesQuery
from .ContentSubmit import ContentSubmit
from .CovoteQuery import CovoteQuery
from .CPSubmit import CPSubmit
from .GlobalStatsQuery import GlobalStatsQuery
from .QuestionnaireQuery import QuestionnaireQuery
from .QuestionnaireTrendQuery import QuestionnaireTrendQuery
from .RankingCharacterMusic import RankingCharacterMusic
from .RankingEntity import RankingEntity
from .RankingEntityCP import RankingEntityCP
from .RankingGlobal import RankingGlobal
from .RankingQuery import RankingQuery
from .ReasonQuery import ReasonQuery
from .Reasons import Reasons
from .SingleQuery import SingleQuery
from .TrendItem import TrendItem
from .TrendQuery import TrendQuery
from .Trends import Trends
from .VotableBase import VotableBase
from .VotableCharacter import VotableCharacter
from .VotableMusic import VotableMusic
from .VotableWork import VotableWork

__version__ = "1.0.0"
__author__ = "FunnyAWM"
__all__ = [
    "LoginData",
    "RegisterData",
    "BaseQuery",
    "CompletionRatesQuery",
    "ContentSubmit",
    "CovoteQuery",
    "CPSubmit",
    "GlobalStatsQuery",
    "QuestionnaireQuery",
    "QuestionnaireTrendQuery",
    "RankingCharacterMusic",
    "RankingEntity",
    "RankingEntityCP",
    "RankingGlobal",
    "RankingQuery",
    "ReasonQuery",
    "Reasons",
    "SingleQuery",
    "TrendItem",
    "TrendQuery",
    "Trends",
    "VotableBase",
    "VotableCharacter",
    "VotableMusic",
    "VotableWork",
]
