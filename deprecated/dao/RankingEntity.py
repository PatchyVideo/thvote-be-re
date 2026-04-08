from typing import List

from pydantic import BaseModel


class RankingEntityData(BaseModel):
    """
    用于RankingEntity的名次数据存储。
    Attributes:
        rank: 排名
        vote_count: 票数
        favorite_vote_count: 本命票数
        favorite_percentage: 本命率
        vote_percentage: 票数占比
    """
    rank: int
    vote_count: int
    favorite_vote_count: int
    favorite_percentage: int
    vote_percentage: float


class VoteCountData(BaseModel):
    """
    用于RankingEntity中基于性别的投票数据统计。
    Attributes:
        vote_count: 票数
        percentage_per_char: 性别比例P({male, female}|voted)
        percentage_per_total: 性别占总体比例P(voted|{male, female})
    """
    vote_count: int
    percentage_per_char: float
    percentage_per_total: float


class RankingEntity(BaseModel):
    """
    通用的排名数据对象。\n
    注意：由于CP有主动方，该对象不适用。请使用CPRankingEntity。
    Attributes:
        rank: 排名（可以插入任意长度数据）
        display_rank: 显示名次
        name: 角色名称
        favorite_vote_count_weighted: 本命加权
        type: 所属作品类型
        origin: 所属作品
        first_appearance: 初次登场时间
        album: 专辑
        name_jp: 日文名称
        favorite_percentage: 本命占比
        male_vote_count: 男性投票数据
        female_vote_count: 女性投票数据
    """
    rank: List[RankingEntityData]
    display_rank: int
    name: str
    favorite_vote_count_weighted: int
    type: str
    origin: str
    first_appearance: str
    album: str
    name_jp: str
    favorite_percentage: float
    male_vote_count: VoteCountData
    female_vote_count: VoteCountData
    reasons: List[str]
    reasons_count: int
