from typing import List, Optional

from .RankingEntity import RankingEntity
from .Trends import Trends


class RankingEntityCP(RankingEntity):
    """
    用于CP的排名数据对象。
    Attributes:
        cps: CP列表，下标可以表示A/B/C方
        active_rate: CP主动率统计数据，需要与cps中的下标绑定
        trend: 趋势对象，详情见Trends.py
    """
    cps: List[str]
    active_rate: List[float]
    trend: Trends
    type: Optional[str] = None
    origin: Optional[str] = None
    first_appearance: Optional[str] = None
    album: Optional[str] = None
    name_jp: Optional[str] = None
