from pydantic import BaseModel

from .RankingEntity import RankingEntity
from .RankingGlobal import RankingGlobal


class RankingCharacterMusic(BaseModel):
    """
    用于角色和音乐的排名数据对象。
    Attributes:
        entries: 数据对象
        ranking_global: 投票总数据
    """
    entries: RankingEntity
    ranking_global: RankingGlobal
