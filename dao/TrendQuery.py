from datetime import datetime
from typing import List, Optional

from .BaseQuery import BaseQuery


class TrendQuery(BaseQuery):
    """
    通用的趋势查询对象。
    Attributes:
        names: 查询的对象名称
    """
    vote_starts_at: Optional[datetime] = None
    names: List[str]
