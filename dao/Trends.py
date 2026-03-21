from pydantic import BaseModel

from .TrendItem import TrendItem


class Trends(BaseModel):
    """
    通用趋势和本命趋势的聚合对象。
    Attributes:
        trend: 通用趋势
        trend_favorite: 本命趋势
    """
    trend: TrendItem
    trend_favorite: TrendItem
