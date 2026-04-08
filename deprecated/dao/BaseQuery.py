from datetime import datetime

from pydantic import BaseModel


class BaseQuery(BaseModel):
    """
    通用的查询对象。
    Attributes:
        query: 查询关键词
        vote_starts_at: 投票开始时间
        vote_year: 投票开启的年份
    """
    query: str
    vote_starts_at: datetime
    vote_year: int
